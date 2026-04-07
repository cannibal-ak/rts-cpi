import csv
import os

DATA_PATH = "apps/api/data"

def inspect(folder):
    path = os.path.join(DATA_PATH, folder)
    if not os.path.exists(path): return
    files = [f for f in os.listdir(path) if f.endswith(".csv")]
    if not files: return
    file_path = os.path.join(path, files[0])
    print(f"--- File: {file_path} ---")
    with open(file_path, 'r') as f:
        reader = csv.reader(f)
        header = next(reader)
        row = next(reader)
        print(f"Header: {header}")
        print(f"Row 1 : {row}")
        print(f"Counts: Header={len(header)}, Row={len(row)}")

inspect("JY")
inspect("PW")
inspect("FJL")
