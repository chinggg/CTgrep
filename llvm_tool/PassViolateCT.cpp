#include "llvm/Pass.h"
#include "llvm/ADT/Any.h"
#include "llvm/ADT/DenseMap.h"
#include "llvm/ADT/SmallVector.h"
#include "llvm/ADT/StringRef.h"
#include "llvm/CodeGen/MachineFunction.h"
#include "llvm/CodeGen/MachineModuleInfo.h"
#include "llvm/IR/Function.h"
#include "llvm/IR/Instruction.h"
#include "llvm/IR/Module.h"
#include "llvm/IR/PassInstrumentation.h"
#include "llvm/IR/PassManager.h"
#include "llvm/IR/PrintPasses.h"
#include "llvm/Passes/PassBuilder.h"
#include "llvm/Passes/PassPlugin.h"
#include "llvm/Support/raw_ostream.h"
#include <cassert>
#include <fstream>
#include <sstream>
#include <iomanip>
#include <string>

using namespace llvm;

namespace myutils {
// Reuse utility functions from MachineFunctionPass.cpp

// This is a cache for file lines to avoid reading the same file multiple times
static StringMap<SmallVector<std::string>> FileCache;

static SmallVector<std::string>& getFileLines(StringRef FileName) {
  auto it = FileCache.find(FileName);
  if (it != FileCache.end()) {
    return it->second;
  }

  std::string Line;
  std::ifstream File(FileName.str());
  SmallVector<std::string>& Lines = FileCache[FileName];
  while (std::getline(File, Line)) {
    Lines.push_back(Line);
  }
  return Lines;
}

template <typename T>
std::string join(const SmallVectorImpl<T> &vec, const std::string &sep = ", ") {
  std::ostringstream sss;
  for (size_t i = 0; i < vec.size(); ++i) {
    std::string str;
    raw_string_ostream ss(str);
    if constexpr (std::is_pointer<T>::value) {
      ss << *vec[i];
    } else {
      ss << vec[i];
    }
    str.erase(std::remove(str.begin(), str.end(), '\n'), str.end());
    if constexpr (std::is_integral<T>::value) {
      sss << str;
    } else {  // wrap each element with ""
      sss << std::quoted(str);
    }
    if (i != vec.size() - 1) {
      sss << sep;
    }
  }
  return sss.str();
}

// Explicit template instantiations
template std::string join(const SmallVectorImpl<std::string> &vec, const std::string &sep);
template std::string join(const SmallVectorImpl<const Instruction*> &vec, const std::string &sep);
template std::string join(const SmallVectorImpl<unsigned> &vec, const std::string &sep);
template std::string join(const SmallVectorImpl<char> &vec, const std::string &sep);

std::string getLineSrc(const DebugLoc &DL) {
  if (!DL) {
    return "[getDebugLoc returns null]";
  }
  StringRef FileName = DL->getScope()->getFilename();
  unsigned Line = DL.getLine();
  
  const auto& Lines = getFileLines(FileName);
  if (Line == 0 || Line > Lines.size()) {
    return "";
  }
  
  // Normalize the line only when it's actually needed
  std::string SourceLine = Lines[Line - 1];
  std::replace(SourceLine.begin(), SourceLine.end(), '\t', ' ');
  // trim \n and \r from SourceLine
  SourceLine.erase(std::remove(SourceLine.begin(), SourceLine.end(), '\n'), SourceLine.end());
  SourceLine.erase(std::remove(SourceLine.begin(), SourceLine.end(), '\r'), SourceLine.end());
  return SourceLine;
}

unsigned getLineNumber(const DebugLoc &DL) {
  if (DL) {
    return DL.getLine();
  }
  return 0;
}

unsigned getLineCol(const DebugLoc &DL) {
  if (DL) {
    return DL.getCol();
  }
  return 0;
}

std::string getCharSrc(const DebugLoc &DL) {
  if (!DL) {
    return "[getDebugLoc returns null]";
  }
  std::string LineSrc = getLineSrc(DL);
  unsigned Col = getLineCol(DL);
  if (Col > 0 && Col <= LineSrc.size()) {
    return std::string{LineSrc[Col - 1]};  // Column is 1-based, convert char to string
  }
  return std::string("");  // Invalid column, use empty character
}

// Helper function to convert instruction to string
std::string getInstStr(const Instruction &I) {
  std::string instStr;
  raw_string_ostream ss(instStr);
  ss << I;
  return instStr;
}

// Helper function to find differences between before and after instruction sets
template<typename T>
void findInstructionDifferences(const SmallVectorImpl<T>& beforeInsts,
                                const SmallVectorImpl<unsigned>& beforeLines,
                                const SmallVectorImpl<unsigned>& beforeCols,
                                const SmallVectorImpl<std::string>& beforeSrcs,
                                const SmallVectorImpl<std::string>& beforeChars,
                                const SmallVectorImpl<T>& afterInsts,
                                const SmallVectorImpl<unsigned>& afterLines,
                                const SmallVectorImpl<unsigned>& afterCols,
                                const SmallVectorImpl<std::string>& afterSrcs,
                                const SmallVectorImpl<std::string>& afterChars,
                                SmallVectorImpl<unsigned>& addedLines,
                                SmallVectorImpl<T>& addedInsts,
                                SmallVectorImpl<std::string>& addedSrcs,
                                SmallVectorImpl<unsigned>& addedCols,
                                SmallVectorImpl<std::string>& addedChars,
                                SmallVectorImpl<unsigned>& removedLines,
                                SmallVectorImpl<T>& removedInsts,
                                SmallVectorImpl<std::string>& removedSrcs,
                                SmallVectorImpl<unsigned>& removedCols,
                                SmallVectorImpl<std::string>& removedChars) {
  // Find added instructions - use line+col combination for precise matching
  for (size_t i = 0; i < afterLines.size(); ++i) {
    bool found = false;
    for (size_t j = 0; j < beforeLines.size(); ++j) {
      if (afterLines[i] == beforeLines[j] && afterCols[i] == beforeCols[j]) {
        found = true;
        break;
      }
    }
    if (!found) {
      addedLines.push_back(afterLines[i]);
      // addedInsts.push_back(afterInsts[i]);
      addedSrcs.push_back(afterSrcs[i]);
      addedCols.push_back(afterCols[i]);
      addedChars.push_back(afterChars[i]);
    }
  }

  // Find removed instructions - use line+col combination for precise matching
  for (size_t i = 0; i < beforeLines.size(); ++i) {
    bool found = false;
    for (size_t j = 0; j < afterLines.size(); ++j) {
      if (beforeLines[i] == afterLines[j] && beforeCols[i] == afterCols[j]) {
        found = true;
        break;
      }
    }
    if (!found) {
      removedLines.push_back(beforeLines[i]);
      // removedInsts.push_back(beforeInsts[i]);
      removedSrcs.push_back(beforeSrcs[i]);
      removedCols.push_back(beforeCols[i]);
      removedChars.push_back(beforeChars[i]);
    }
  }
}

} // namespace myutils

using namespace myutils;

namespace {

// Return true when this is a pass for which changes should be ignored
bool isIgnoredPass(StringRef PassID) {
  return isSpecialPass(PassID,
                       {"PassManager", "PassAdaptor", "AnalysisManagerProxy",
                        "DevirtSCCRepeatedPass", "ModuleInlinerWrapperPass",
                        "VerifierPass", "PrintModulePass"});
}

bool isIgnoredFunction(const Function &F) {
  if (F.isDeclaration() || F.isIntrinsic())
    return true;
  return false;
}

bool isDivisionInstruction(const Instruction &I) {
  if (isa<BinaryOperator>(I)) {
    auto *BO = cast<BinaryOperator>(&I);
    unsigned Opcode = BO->getOpcode();
    switch (Opcode) {
      case Instruction::SDiv:
      case Instruction::UDiv:
      case Instruction::FDiv:
      case Instruction::SRem:
      case Instruction::URem:
      case Instruction::FRem:
        return true;
    }
  }
  return false;
}

template <typename IRUnitT> static const IRUnitT *unwrapIR(Any IR) {
  const IRUnitT **IRPtr = llvm::any_cast<const IRUnitT *>(&IR);
  return IRPtr ? *IRPtr : nullptr;
}

// This will collect instruction information and store it for later comparison
static SmallVector<std::string, 16> BeforeCondInsts;
static SmallVector<std::string, 16> BeforeCondSrcs;
static SmallVector<unsigned, 16> BeforeCondLines;
static SmallVector<unsigned, 16> BeforeCondCols;
static SmallVector<std::string, 16> BeforeCondChars;
static SmallVector<std::string, 16> BeforeSelectInsts;
static SmallVector<std::string, 16> BeforeSelectSrcs;
static SmallVector<unsigned, 16> BeforeSelectLines;
static SmallVector<unsigned, 16> BeforeSelectCols;
static SmallVector<std::string, 16> BeforeSelectChars;
static SmallVector<std::string, 16> BeforeDivInsts;
static SmallVector<std::string, 16> BeforeDivSrcs;
static SmallVector<unsigned, 16> BeforeDivLines;
static SmallVector<unsigned, 16> BeforeDivCols;
static SmallVector<std::string, 16> BeforeDivChars;
static SmallVector<std::string, 16> BeforeMemInsts;
static SmallVector<std::string, 16> BeforeMemSrcs;
static SmallVector<unsigned, 16> BeforeMemLines;
static SmallVector<unsigned, 16> BeforeMemCols;
static SmallVector<std::string, 16> BeforeMemChars;
static std::string BeforeFunction;
static std::string BeforeFileName;
static std::string BeforeFilePath;
static std::string BeforeContext;
const Function* CurrentF;

bool saveInsts(const Function &F, StringRef Context) {
  // Skip if function is not in print list
  if (isIgnoredFunction(F) || !isFunctionInPrintList(F.getName()))
    return false;

  auto *SP = F.getSubprogram();
  if (!SP) return false;  // no debug info available if not compiled with -g
  auto FileName = SP->getFilename();
  auto FileDir = SP->getDirectory();
  CurrentF = &F;

  // Clear previous state and collect current state
  BeforeFunction = F.getName().str();
  BeforeFileName = FileName.str();
  BeforeFilePath = (FileDir + "/" + FileName).str();
  BeforeContext = Context.str();
  BeforeCondInsts.clear();
  BeforeCondSrcs.clear();
  BeforeCondLines.clear();
  BeforeCondCols.clear();
  BeforeCondChars.clear();
  BeforeSelectInsts.clear();
  BeforeSelectSrcs.clear();
  BeforeSelectLines.clear();
  BeforeSelectCols.clear();
  BeforeSelectChars.clear();
  BeforeDivInsts.clear();
  BeforeDivSrcs.clear();
  BeforeDivLines.clear();
  BeforeDivCols.clear();
  BeforeDivChars.clear();
  BeforeMemInsts.clear();
  BeforeMemSrcs.clear();
  BeforeMemLines.clear();
  BeforeMemCols.clear();
  BeforeMemChars.clear();

  // Collect all conditional instructions, divisions, and memory operations
  for (const BasicBlock &BB : F) {
    for (const Instruction &I : BB) {
      if (isa<BranchInst>(&I) && cast<BranchInst>(&I)->isConditional()) {
        // BeforeCondInsts.push_back(getInstStr(I));
        BeforeCondSrcs.push_back(getLineSrc(I.getDebugLoc()));
        BeforeCondLines.push_back(getLineNumber(I.getDebugLoc()));
        BeforeCondCols.push_back(getLineCol(I.getDebugLoc()));
        BeforeCondChars.push_back(getCharSrc(I.getDebugLoc()));
      }
      // Check for select instructions
      if (isa<SelectInst>(&I)) {
        // BeforeSelectInsts.push_back(getInstStr(I));
        BeforeSelectSrcs.push_back(getLineSrc(I.getDebugLoc()));
        BeforeSelectLines.push_back(getLineNumber(I.getDebugLoc()));
        BeforeSelectCols.push_back(getLineCol(I.getDebugLoc()));
        BeforeSelectChars.push_back(getCharSrc(I.getDebugLoc()));
      }
      // Check for division instructions
      if (isDivisionInstruction(I)) {
        // BeforeDivInsts.push_back(getInstStr(I));
        BeforeDivSrcs.push_back(getLineSrc(I.getDebugLoc()));
        BeforeDivLines.push_back(getLineNumber(I.getDebugLoc()));
        BeforeDivCols.push_back(getLineCol(I.getDebugLoc()));
        BeforeDivChars.push_back(getCharSrc(I.getDebugLoc()));
      }
      // Check for memory operations
      if (isa<LoadInst>(&I) || isa<StoreInst>(&I)) {
        // BeforeMemInsts.push_back(getInstStr(I));
        BeforeMemSrcs.push_back(getLineSrc(I.getDebugLoc()));
        BeforeMemLines.push_back(getLineNumber(I.getDebugLoc()));
        BeforeMemCols.push_back(getLineCol(I.getDebugLoc()));
        BeforeMemChars.push_back(getCharSrc(I.getDebugLoc()));
      }
    }
  }
  return true;
}

bool compareAndDumpInsts(const Function &F, StringRef Context) {
  // Skip if function is not in print list
  if (isIgnoredFunction(F) || !isFunctionInPrintList(F.getName()))
    return false;

  auto *SP = F.getSubprogram();
  if (!SP) return false;  // no debug info available if not compiled with -g

  // Collect current state after pass execution
  SmallVector<std::string, 16> AfterCondInsts;
  SmallVector<std::string, 16> AfterCondSrcs;
  SmallVector<unsigned, 16> AfterCondLines;
  SmallVector<unsigned, 16> AfterCondCols;
  SmallVector<std::string, 16> AfterCondChars;
  SmallVector<std::string, 16> AfterSelectInsts;
  SmallVector<std::string, 16> AfterSelectSrcs;
  SmallVector<unsigned, 16> AfterSelectLines;
  SmallVector<unsigned, 16> AfterSelectCols;
  SmallVector<std::string, 16> AfterSelectChars;
  SmallVector<std::string, 16> AfterDivInsts;
  SmallVector<std::string, 16> AfterDivSrcs;
  SmallVector<unsigned, 16> AfterDivLines;
  SmallVector<unsigned, 16> AfterDivCols;
  SmallVector<std::string, 16> AfterDivChars;
  SmallVector<std::string, 16> AfterMemInsts;
  SmallVector<std::string, 16> AfterMemSrcs;
  SmallVector<unsigned, 16> AfterMemLines;
  SmallVector<unsigned, 16> AfterMemCols;
  SmallVector<std::string, 16> AfterMemChars;

  for (const BasicBlock &BB : F) {
    for (const Instruction &I : BB) {
      if (isa<BranchInst>(&I) && cast<BranchInst>(&I)->isConditional()) {
        // AfterCondInsts.push_back(getInstStr(I));
        AfterCondSrcs.push_back(getLineSrc(I.getDebugLoc()));
        AfterCondLines.push_back(getLineNumber(I.getDebugLoc()));
        AfterCondCols.push_back(getLineCol(I.getDebugLoc()));
        AfterCondChars.push_back(getCharSrc(I.getDebugLoc()));
      }
      if (isa<SelectInst>(&I)) {
        // AfterSelectInsts.push_back(getInstStr(I));
        AfterSelectSrcs.push_back(getLineSrc(I.getDebugLoc()));
        AfterSelectLines.push_back(getLineNumber(I.getDebugLoc()));
        AfterSelectCols.push_back(getLineCol(I.getDebugLoc()));
        AfterSelectChars.push_back(getCharSrc(I.getDebugLoc()));
      }
      if (isDivisionInstruction(I)) {
        // AfterDivInsts.push_back(getInstStr(I));
        AfterDivSrcs.push_back(getLineSrc(I.getDebugLoc()));
        AfterDivLines.push_back(getLineNumber(I.getDebugLoc()));
        AfterDivCols.push_back(getLineCol(I.getDebugLoc()));
        AfterDivChars.push_back(getCharSrc(I.getDebugLoc()));
      }
      if (isa<LoadInst>(&I) || isa<StoreInst>(&I)) {
        // AfterMemInsts.push_back(getInstStr(I));
        AfterMemSrcs.push_back(getLineSrc(I.getDebugLoc()));
        AfterMemLines.push_back(getLineNumber(I.getDebugLoc()));
        AfterMemCols.push_back(getLineCol(I.getDebugLoc()));
        AfterMemChars.push_back(getCharSrc(I.getDebugLoc()));
      }
    }
  }

  // Find added and removed instructions using helper function
  SmallVector<std::string, 16> AddedCondInsts, RemovedCondInsts;
  SmallVector<unsigned, 16> AddedCondLines, RemovedCondLines;
  SmallVector<unsigned, 16> AddedCondCols, RemovedCondCols;
  SmallVector<std::string, 16> AddedCondSrcs, RemovedCondSrcs;
  SmallVector<std::string, 16> AddedCondChars, RemovedCondChars;

  SmallVector<std::string, 16> AddedSelectInsts, RemovedSelectInsts;
  SmallVector<unsigned, 16> AddedSelectLines, RemovedSelectLines;
  SmallVector<unsigned, 16> AddedSelectCols, RemovedSelectCols;
  SmallVector<std::string, 16> AddedSelectSrcs, RemovedSelectSrcs;
  SmallVector<std::string, 16> AddedSelectChars, RemovedSelectChars;

  SmallVector<std::string, 16> AddedDivInsts, RemovedDivInsts;
  SmallVector<unsigned, 16> AddedDivLines, RemovedDivLines;
  SmallVector<unsigned, 16> AddedDivCols, RemovedDivCols;
  SmallVector<std::string, 16> AddedDivSrcs, RemovedDivSrcs;
  SmallVector<std::string, 16> AddedDivChars, RemovedDivChars;

  SmallVector<std::string, 16> AddedMemInsts, RemovedMemInsts;
  SmallVector<unsigned, 16> AddedMemLines, RemovedMemLines;
  SmallVector<unsigned, 16> AddedMemCols, RemovedMemCols;
  SmallVector<std::string, 16> AddedMemSrcs, RemovedMemSrcs;
  SmallVector<std::string, 16> AddedMemChars, RemovedMemChars;

  // Find added/removed conditional instructions
  findInstructionDifferences(BeforeCondInsts, BeforeCondLines, BeforeCondCols, BeforeCondSrcs, BeforeCondChars,
                            AfterCondInsts, AfterCondLines, AfterCondCols, AfterCondSrcs, AfterCondChars,
                            AddedCondLines, AddedCondInsts, AddedCondSrcs, AddedCondCols, AddedCondChars,
                            RemovedCondLines, RemovedCondInsts, RemovedCondSrcs, RemovedCondCols, RemovedCondChars);

  // Find added/removed select instructions
  findInstructionDifferences(BeforeSelectInsts, BeforeSelectLines, BeforeSelectCols, BeforeSelectSrcs, BeforeSelectChars,
                            AfterSelectInsts, AfterSelectLines, AfterSelectCols, AfterSelectSrcs, AfterSelectChars,
                            AddedSelectLines, AddedSelectInsts, AddedSelectSrcs, AddedSelectCols, AddedSelectChars,
                            RemovedSelectLines, RemovedSelectInsts, RemovedSelectSrcs, RemovedSelectCols, RemovedSelectChars);

  // Find added/removed divisions
  findInstructionDifferences(BeforeDivInsts, BeforeDivLines, BeforeDivCols, BeforeDivSrcs, BeforeDivChars,
                            AfterDivInsts, AfterDivLines, AfterDivCols, AfterDivSrcs, AfterDivChars,
                            AddedDivLines, AddedDivInsts, AddedDivSrcs, AddedDivCols, AddedDivChars,
                            RemovedDivLines, RemovedDivInsts, RemovedDivSrcs, RemovedDivCols, RemovedDivChars);

  // Find added/removed memory operations
  findInstructionDifferences(BeforeMemInsts, BeforeMemLines, BeforeMemCols, BeforeMemSrcs, BeforeMemChars,
                            AfterMemInsts, AfterMemLines, AfterMemCols, AfterMemSrcs, AfterMemChars,
                            AddedMemLines, AddedMemInsts, AddedMemSrcs, AddedMemCols, AddedMemChars,
                            RemovedMemLines, RemovedMemInsts, RemovedMemSrcs, RemovedMemCols, RemovedMemChars);

  // Only print if there were changes
  if (!AddedCondLines.empty() || !RemovedCondLines.empty() || 
      !AddedSelectLines.empty() || !RemovedSelectLines.empty() ||
      !AddedDivLines.empty() || !RemovedDivLines.empty() ||
      !AddedMemLines.empty() || !RemovedMemLines.empty()) {
    // Build the complete JSON string in memory before outputting
    std::string JsonOutput;
    raw_string_ostream JsonStream(JsonOutput);
    
    JsonStream << "{"
      << "\"function\": \"" << BeforeFunction << "\","
      << "\"file\": \"" << BeforeFileName << "\","
      << "\"path\": \"" << BeforeFilePath << "\","
      << "\"context\": \"" << BeforeContext << "\","
      // Conditional instruction stats 
      << "\"cond_count_before\": " << BeforeCondInsts.size() << ","
      << "\"cond_count_after\": " << AfterCondInsts.size() << ","
      << "\"removed_cond_count\": " << RemovedCondLines.size() << ","
      << "\"added_cond_count\": " << AddedCondLines.size();
    // Removed conditional instructions
    if (!RemovedCondLines.empty()) {
      JsonStream << ",\"removed_cond_lines\": [" << join(RemovedCondLines) << "]"
      << ",\"removed_cond_cols\": [" << join(RemovedCondCols) << "]"
      << ",\"removed_cond_insts\": [" << join(RemovedCondInsts) << "]"
      << ",\"removed_cond_srcs\": [" << join(RemovedCondSrcs) << "]"
      << ",\"removed_cond_chars\": [" << join(RemovedCondChars) << "]";
    }
    // Added conditional instructions  
    if (!AddedCondLines.empty()) {
      JsonStream << ",\"added_cond_lines\": [" << join(AddedCondLines) << "]"
      << ",\"added_cond_cols\": [" << join(AddedCondCols) << "]"
      << ",\"added_cond_insts\": [" << join(AddedCondInsts) << "]"
      << ",\"added_cond_srcs\": [" << join(AddedCondSrcs) << "]"
      << ",\"added_cond_chars\": [" << join(AddedCondChars) << "]";
    }
    // Select instruction stats
    JsonStream << ",\"select_count_before\": " << BeforeSelectInsts.size() << ","
      << "\"select_count_after\": " << AfterSelectInsts.size() << ","
      << "\"removed_select_count\": " << RemovedSelectLines.size() << ","
      << "\"added_select_count\": " << AddedSelectLines.size();
    // Removed select instructions
    if (!RemovedSelectLines.empty()) {
      JsonStream << ",\"removed_select_lines\": [" << join(RemovedSelectLines) << "]"
      << ",\"removed_select_cols\": [" << join(RemovedSelectCols) << "]"
      << ",\"removed_select_insts\": [" << join(RemovedSelectInsts) << "]"
      << ",\"removed_select_srcs\": [" << join(RemovedSelectSrcs) << "]"
      << ",\"removed_select_chars\": [" << join(RemovedSelectChars) << "]";
    }
    // Added select instructions 
    if (!AddedSelectLines.empty()) {
      JsonStream << ",\"added_select_lines\": [" << join(AddedSelectLines) << "]"
      << ",\"added_select_cols\": [" << join(AddedSelectCols) << "]"
      << ",\"added_select_insts\": [" << join(AddedSelectInsts) << "]"
      << ",\"added_select_srcs\": [" << join(AddedSelectSrcs) << "]"
      << ",\"added_select_chars\": [" << join(AddedSelectChars) << "]";
    }
    // Division instruction stats
    JsonStream << ",\"div_count_before\": " << BeforeDivInsts.size() << ","
      << "\"div_count_after\": " << AfterDivInsts.size() << ","
      << "\"removed_div_count\": " << RemovedDivLines.size() << ","
      << "\"added_div_count\": " << AddedDivLines.size();
    // Removed division instructions
    if (!RemovedDivLines.empty()) {
      JsonStream << ",\"removed_div_lines\": [" << join(RemovedDivLines) << "]"
      << ",\"removed_div_cols\": [" << join(RemovedDivCols) << "]"
      << ",\"removed_div_insts\": [" << join(RemovedDivInsts) << "]"
      << ",\"removed_div_srcs\": [" << join(RemovedDivSrcs) << "]"
      << ",\"removed_div_chars\": [" << join(RemovedDivChars) << "]";
    }
    // Added division instructions 
    if (!AddedDivLines.empty()) {
      JsonStream << ",\"added_div_lines\": [" << join(AddedDivLines) << "]"
      << ",\"added_div_cols\": [" << join(AddedDivCols) << "]"
      << ",\"added_div_insts\": [" << join(AddedDivInsts) << "]"
      << ",\"added_div_srcs\": [" << join(AddedDivSrcs) << "]"
      << ",\"added_div_chars\": [" << join(AddedDivChars) << "]";
    }
    // Memory operation stats
    JsonStream << ",\"mem_count_before\": " << BeforeMemInsts.size() << ","
      << "\"mem_count_after\": " << AfterMemInsts.size() << ","
      << "\"removed_mem_count\": " << RemovedMemLines.size() << ","
      << "\"added_mem_count\": " << AddedMemLines.size();
    // Removed memory operations
    if (!RemovedMemLines.empty()) {
      JsonStream << ",\"removed_mem_lines\": [" << join(RemovedMemLines) << "]"
      << ",\"removed_mem_cols\": [" << join(RemovedMemCols) << "]"
      << ",\"removed_mem_insts\": [" << join(RemovedMemInsts) << "]"
      << ",\"removed_mem_srcs\": [" << join(RemovedMemSrcs) << "]"
      << ",\"removed_mem_chars\": [" << join(RemovedMemChars) << "]";
    }
    // Added memory operations
    if (!AddedMemLines.empty()) {
      JsonStream << ",\"added_mem_lines\": [" << join(AddedMemLines) << "]"
      << ",\"added_mem_cols\": [" << join(AddedMemCols) << "]"
      << ",\"added_mem_insts\": [" << join(AddedMemInsts) << "]"
      << ",\"added_mem_srcs\": [" << join(AddedMemSrcs) << "]"
      << ",\"added_mem_chars\": [" << join(AddedMemChars) << "]";
    }
    JsonStream << "}\n";
    
    // Output the complete JSON string
    errs() << JsonOutput;
    
    return true;
  }
  
  // No changes to conditional instructions, select instructions, divisions, or memory operations
  return false;
}

class PassViolateCT {
protected:
  StringRef PassName;

  // save info from instructions since IR will not be valid after the pass
  bool saveIRbeforePass(StringRef PassID, Any IR) {
    if (isIgnoredPass(PassID))
      return false;
    if (const auto *L = unwrapIR<Loop>(IR)) {
      const Function *F = L->getHeader()->getParent();
      saveInsts(*F, PassID);
    }
    if (const auto *F = unwrapIR<Function>(IR)) {
      saveInsts(*F, PassID);
    }
    if (const auto *M = unwrapIR<Module>(IR)) {
      for (const Function &F : *M) {
        saveInsts(F, PassID);
      }
    }
    if (const auto *MF = unwrapIR<MachineFunction>(IR)) {
      errs() << "Before Pass " << PassID << " on MachineFunction: " << MF->getName() << "\n";
    }
    PassName = PassID;
    return true;
  }

  // Overloaded versions for direct Function/Module pointers (for legacy PM)
  bool saveIRbeforePass(StringRef PassID, const Function* F) {
    if (isIgnoredPass(PassID) || !F)
      return false;
    saveInsts(*F, PassID);
    PassName = PassID;
    return true;
  }

  bool saveIRbeforePass(StringRef PassID, const Module* M) {
    if (isIgnoredPass(PassID) || !M)
      return false;
    for (const Function &F : *M) {
      saveInsts(F, PassID);
    }
    PassName = PassID;
    return true;
  }

  void handleAfterPass(StringRef PassID, Any IR) {
    if (isIgnoredPass(PassID))
      return;
    assert(PassName == PassID && "Pass order mismatch");
    if (const auto *L = unwrapIR<Loop>(IR)) {
      const Function *F = L->getHeader()->getParent();
      compareAndDumpInsts(*F, PassID);
    }
    if (const auto *M = unwrapIR<Module>(IR)) {
      for (const Function &F : *M) {
        compareAndDumpInsts(F, PassID);
      }
    }
    if (const auto *F = unwrapIR<Function>(IR)) {
      compareAndDumpInsts(*F, PassID);
    }
    if (const auto *MF = unwrapIR<MachineFunction>(IR)) {
      errs() << "After Pass " << PassID << " on MachineFunction: " << MF->getName() << "\n";
    }
    return;
  }

  // Overloaded versions for direct Function/Module pointers (for legacy PM)
  void handleAfterPass(StringRef PassID, const Function* F) {
    if (isIgnoredPass(PassID) || !F)
      return;
    // Note: For legacy PM, we don't assert on PassName match since
    // different pass invocations might interleave
    compareAndDumpInsts(*F, PassID);
  }

  void handleAfterPass(StringRef PassID, const Module* M) {
    if (isIgnoredPass(PassID) || !M)
      return;
    // Note: For legacy PM, we don't assert on PassName match since
    // different pass invocations might interleave
    for (const Function &F : *M) {
      compareAndDumpInsts(F, PassID);
    }
  }

public:
  // Public interface for legacy pass manager hooks
  void legacyBeforeFunctionPass(const Function* F, StringRef PassName) {
    saveIRbeforePass(PassName, F);
  }

  void legacyAfterFunctionPass(const Function* F, StringRef PassName) {
    handleAfterPass(PassName, F);
  }

  void legacyBeforeModulePass(const Module* M, StringRef PassName) {
    saveIRbeforePass(PassName, M);
  }

  void legacyAfterModulePass(const Module* M, StringRef PassName) {
    handleAfterPass(PassName, M);
  }

  void registerCallbacks(PassInstrumentationCallbacks& PIC) {
    PIC.registerBeforeNonSkippedPassCallback(
      [this](StringRef PassID, Any IR) { this->saveIRbeforePass(PassID, IR); }
    );
    PIC.registerAfterPassCallback(
      [this](StringRef PassID, Any IR, const PreservedAnalyses &) { this->handleAfterPass(PassID, IR); }
    );
    PIC.registerAfterPassInvalidatedCallback(
      // NOTE: LLVM API does not allow passing IR here, try with stored function pointer
      // see https://github.com/llvm/llvm-project/blob/release/18.x/llvm/include/llvm/IR/PassInstrumentation.h#L74-L77
      [this](StringRef PassID, const PreservedAnalyses &) {
        errs() << "After Invalidated Pass " << PassID;
        if (!CurrentF) { errs() << " , but no current function stored.\n"; return; }
        if (CurrentF->getName().str() != BeforeFunction) {
          errs() << ", but got function name " << CurrentF->getName() << " != " << BeforeFunction << "\n"; return;
        }
        errs() << " , got function " << CurrentF->getName() << "\n";
        this->handleAfterPass(PassID, CurrentF);
      }
    );
  }
};
} // end anonymous namespace

static PassViolateCT ViolateCT;

// Global functions for Legacy Pass Manager instrumentation hooks
// These will be called from LegacyPassManager.cpp

extern "C" LLVM_ATTRIBUTE_WEAK void LegacyBeforeFunctionPass(const Function* F, StringRef PassName) {
  if (F) ViolateCT.legacyBeforeFunctionPass(F, PassName);
}

extern "C" LLVM_ATTRIBUTE_WEAK void LegacyAfterFunctionPass(const Function* F, StringRef PassName) {
  if (F) ViolateCT.legacyAfterFunctionPass(F, PassName);
}

extern "C" LLVM_ATTRIBUTE_WEAK void LegacyBeforeModulePass(const Module* M, StringRef PassName) {
  if (M) ViolateCT.legacyBeforeModulePass(M, PassName);
}

extern "C" LLVM_ATTRIBUTE_WEAK void LegacyAfterModulePass(const Module* M, StringRef PassName) {
  if (M) ViolateCT.legacyAfterModulePass(M, PassName);
}

extern "C" ::llvm::PassPluginLibraryInfo LLVM_ATTRIBUTE_WEAK
llvmGetPassPluginInfo() {
  return {
    LLVM_PLUGIN_API_VERSION, "PassViolateConstantTimeInstrumentPlugin", "v0.1",
    [](PassBuilder& PB) {
      auto& PIC = *PB.getPassInstrumentationCallbacks();
      ViolateCT.registerCallbacks(PIC);
    }
  };
}