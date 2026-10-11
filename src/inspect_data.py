
import pandas as pd
from pathlib import Path

# Locate the project directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = PROJECT_ROOT / "data" / "raw" / "manga.csv"

# Load the raw dataset
df = pd.read_csv(DATA_FILE, low_memory=False)

print("=" * 50)
print("EMBER - DATASET INSPECTION")
print("=" * 50)

# Basic dataset information
print(f"\nTotal rows: {len(df)}")
print(f"Total columns: {len(df.columns)}")

print("\nColumn names:")
print(df.columns.tolist())

# Missing values
print("\nMissing values in important columns:")
important_columns = [
    "title", "type", "score", "genres",
    "authors", "start_date", "end_date",
    "chapters", "volumes"
]

for column in important_columns:
    if column in df.columns:
        missing = df[column].isna().sum()
        percentage = missing / len(df) * 100
        print(f"{column}: {missing} ({percentage:.2f}%)")

# Duplicate checks
print("\nDuplicate checks:")
print("Duplicate rows:", df.duplicated().sum())

if "manga_id" in df.columns:
    print("Duplicate manga IDs:", df["manga_id"].duplicated().sum())

# Rating overview
if "score" in df.columns:
    print("\nRating summary:")
    print(df["score"].describe())

# Save a preliminary report
report_dir = PROJECT_ROOT / "reports"
report_dir.mkdir(parents=True, exist_ok=True)

with open(report_dir / "initial_data_inspection.txt", "w",
          encoding="utf-8") as file:
    file.write(f"Rows: {len(df)}\n")
    file.write(f"Columns: {len(df.columns)}\n")
    file.write(f"Duplicate rows: {df.duplicated().sum()}\n")
    file.write("\nMissing values:\n")
    file.write(df[important_columns].isna().sum().to_string())

print("\nInspection report saved to reports/initial_data_inspection.txt")