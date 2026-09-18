import os
import csv

import pandas as pd


def read_all_files(directory, pattern=None):
    """Walk `directory` and return every file path (optionally filtered by `pattern in name`)."""
    all_files = []
    for root, dirs, files in os.walk(directory):
        dirs.sort()
        files.sort()
        for file in files:
            if pattern is None or pattern in file:
                all_files.append(os.path.join(root, file))
    return sorted(all_files)


def read_file(file_path):
    """Read one CSV. Derives lib/opt/arch tags from the filename's underscore-split parts."""
    file_name = os.path.basename(file_path)
    df = pd.read_csv(file_path, sep='\t', header=0, on_bad_lines='warn', quoting=csv.QUOTE_NONE)
    df["lib"] = file_name.split("_")[0]
    df["opt"] = file_name.split("_")[1]
    df["arch"] = file_name.split("_")[2]
    return df


def read_files_and_create_df(folder_name, clangversion):
    """Load every `*_unique.csv` under `folder_name`, tag each row with `clangversion`."""
    files = read_all_files(folder_name, "_unique.csv")
    print(len(files))
    final_df = pd.concat([read_file(f) for f in files])
    final_df["clangversion"] = clangversion
    print(f"Total number of rows: {len(final_df)}")
    return final_df
