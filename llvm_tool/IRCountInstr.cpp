#include "llvm/IR/InstrTypes.h"
#include "llvm/IR/Instruction.h"
#include "llvm/IR/Instructions.h"
#include "llvm/Pass.h"
#include "llvm/IR/Value.h"
#include "llvm/IR/PassManager.h"
#include "llvm/IR/PassInstrumentation.h"
#include "llvm/IR/PrintPasses.h"
#include "llvm/Passes/PassBuilder.h"
#include "llvm/Passes/PassPlugin.h"
#include "llvm/Support/raw_ostream.h"
#include "llvm/Support/FileSystem.h"

#include <string>
#include <iomanip>
#include <fstream>

using namespace llvm;

namespace myutils {

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

// Explicit template instantiation to avoid undefined reference linker errors
// see https://isocpp.org/wiki/faq/templates#separate-template-fn-defn-from-decl
template
std::string join(const SmallVectorImpl<std::string> &vec, const std::string &sep);

template
std::string join(const SmallVectorImpl<const Instruction*> &vec, const std::string &sep);

template
std::string join(const SmallVectorImpl<unsigned> &vec, const std::string &sep);

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

bool isNameTrivial(const StringRef &Name) {
  const std::string TrivialKeywords[] = {".h", "include/", "third_party", "third-party", "fuzz", "test", "helper"};
  for (const auto &Keyword : TrivialKeywords) {
    if (Name.lower().find(Keyword) != std::string::npos) {
      return true;
    }
  }
  return false;
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

struct MyPass : public PassInfoMixin<MyPass> {
  std::string Context; // To differentiate behavior

  MyPass(std::string Context) : Context(Context) {}

  int check_select(Instruction &I, StringRef File_name, StringRef Function_name);
  int check_function(Instruction &I);
  
  PreservedAnalyses run(Function &F, FunctionAnalysisManager &FAM) {
    if (isIgnoredFunction(F) || !isFunctionInPrintList(F.getName()))
      return PreservedAnalyses::all();
    if (isNameTrivial(F.getName()))
      return PreservedAnalyses::all();

    // Get the source file name
    auto *SP = F.getFunction().getSubprogram();
    if (!SP) return PreservedAnalyses::all();  // no debug info available if not compiled with -g
    auto FileName = SP->getFilename();
    if (isNameTrivial(FileName))
      return PreservedAnalyses::all();

    // Instruction counters and line numbers
    SmallVector<const Instruction*, 16> CondInsts;
    SmallVector<const Instruction*, 16> SelectInsts;  // Add SelectInst tracking
    SmallVector<const Instruction*, 16> MemInsts;  // IR memory operations
    SmallVector<const Instruction*, 16> DivInsts; 
    SmallVector<std::string, 16> CondSrcs;
    SmallVector<std::string, 16> SelectSrcs;  // Add SelectInst sources
    SmallVector<std::string, 16> MemSrcs;
    SmallVector<std::string, 16> DivSrcs;
    SmallVector<unsigned, 16> CondLines;
    SmallVector<unsigned, 16> SelectLines;  // Add SelectInst lines
    SmallVector<unsigned, 16> MemLines;
    SmallVector<unsigned, 16> DivLines;
    SmallVector<unsigned, 16> CondCols;
    SmallVector<unsigned, 16> SelectCols;  // Add SelectInst columns
    SmallVector<unsigned, 16> MemCols;
    SmallVector<unsigned, 16> DivCols;
    SmallVector<std::string, 16> CondChars;
    SmallVector<std::string, 16> SelectChars;  // Add SelectInst characters
    SmallVector<std::string, 16> MemChars;
    SmallVector<std::string, 16> DivChars;

    // Iterate through the LLVM IR instructions to count conditional branch and divisions
    for (const BasicBlock &BB : F) {
      for (const Instruction &I : BB) {
        if (!I.getDebugLoc()) continue;
        if (isa<BranchInst>(I) && cast<BranchInst>(I).isConditional()) {
          CondInsts.push_back(&I);
          CondLines.push_back(getLineNumber(I.getDebugLoc()));
          CondSrcs.push_back(getLineSrc(I.getDebugLoc()));
          CondCols.push_back(getLineCol(I.getDebugLoc()));
          CondChars.push_back(getCharSrc(I.getDebugLoc()));
        } else if (isa<SelectInst>(I)) {
          SelectInsts.push_back(&I);
          SelectLines.push_back(getLineNumber(I.getDebugLoc()));
          SelectSrcs.push_back(getLineSrc(I.getDebugLoc()));
          SelectCols.push_back(getLineCol(I.getDebugLoc()));
          SelectChars.push_back(getCharSrc(I.getDebugLoc()));
        } else if (isDivisionInstruction(I)) {
          DivInsts.push_back(&I);
          DivLines.push_back(getLineNumber(I.getDebugLoc()));
          DivSrcs.push_back(getLineSrc(I.getDebugLoc()));
          DivCols.push_back(getLineCol(I.getDebugLoc()));
          DivChars.push_back(getCharSrc(I.getDebugLoc()));
        // } else if (isa<LoadInst>(I) || isa<StoreInst>(I)) {
          // MemInsts.push_back(&I);
          // MemLines.push_back(getLineNumber(I.getDebugLoc()));
          // MemSrcs.push_back(getLineSrc(I.getDebugLoc()));
          // MemCols.push_back(getLineCol(I.getDebugLoc()));
          // MemChars.push_back(getCharSrc(I.getDebugLoc()));
        }
      }
    }

    // Build the complete JSON string in memory before outputting
    std::string JsonOutput;
    raw_string_ostream JsonStream(JsonOutput);
    JsonStream << "{"
            << "\"function\": \"" << F.getName() << "\", "
            << "\"file\": \"" << FileName << "\", "
            << "\"context\": \"" << Context << "\", "
            << "\"cond_count\": " << CondInsts.size() << ", "
            << "\"cond_lines\": [" << join(CondLines) << "], "
            << "\"cond_cols\": [" << join(CondCols) << "], "
            << "\"cond_insts\": [" << join(CondInsts) << "], "
            << "\"cond_srcs\": [" << join(CondSrcs) << "], "
            << "\"cond_chars\": [" << join(CondChars) << "], "
            << "\"select_count\": " << SelectInsts.size() << ", "
            << "\"select_lines\": [" << join(SelectLines) << "], "
            << "\"select_cols\": [" << join(SelectCols) << "], "
            << "\"select_insts\": [" << join(SelectInsts) << "], "
            << "\"select_srcs\": [" << join(SelectSrcs) << "], "
            << "\"select_chars\": [" << join(SelectChars) << "], "
            << "\"div_count\": " << DivInsts.size() << ", "
            << "\"div_lines\": [" << join(DivLines) << "], "
            << "\"div_cols\": [" << join(DivCols) << "], "
            << "\"div_insts\": [" << join(DivInsts) << "], "
            << "\"div_srcs\": [" << join(DivSrcs) << "], "
            << "\"div_chars\": [" << join(DivChars) << "]"
            // << "\"mem_count\": " << MemInsts.size() << ", "
            // << "\"mem_lines\": [" << join(MemLines) << "], "
            // << "\"mem_cols\": [" << join(MemCols) << "], "
            // << "\"mem_insts\": [" << join(MemInsts) << "], "
            // << "\"mem_srcs\": [" << join(MemSrcs) << "], "
            // << "\"mem_chars\": [" << join(MemChars) << "]"
            << "}\n";
    
    errs() << JsonOutput;
    return PreservedAnalyses::all();
  }
};
} 

extern "C" ::llvm::PassPluginLibraryInfo LLVM_ATTRIBUTE_WEAK
llvmGetPassPluginInfo() {
  return {
    LLVM_PLUGIN_API_VERSION, "IRCountInstrPlugin", "v0.1",
    [](PassBuilder &PB) {
      // PipelineStartCallback is before any optimization
      PB.registerPipelineStartEPCallback(
          [&](ModulePassManager &MPM, OptimizationLevel Level) {
            MPM.addPass(createModuleToFunctionPassAdaptor(MyPass("IRCountInstr")));
            return true;
          });
    }
  };
}
