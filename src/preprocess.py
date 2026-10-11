import ast
from pathlib import Path

import pandas as pd


# --------------------------------------------------
# 1. Project paths
# --------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent

RAW_FILE = ROOT / "data" / "raw" / "manga.csv"
OUTPUT_DIR = ROOT / "data" / "processed"
REPORT_DIR = ROOT / "reports"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------
# 2. Standard content-format labels
# --------------------------------------------------
FORMAT_MAP = {
    "manga": "Manga",
    "manhwa": "Manhwa",
    "manhua": "Manhua",
    "light_novel": "Light Novel",
    "novel": "Novel",
    "one_shot": "One-shot",
    "doujinshi": "Doujinshi",
    "oel": "OEL",
}


# --------------------------------------------------
# 3. Normalize list-like metadata
# --------------------------------------------------
def clean_list_column(value):
    """
    Convert list-like metadata into readable pipe-separated text.

    Handles:
    - Lists of strings
    - Lists of dictionaries with a 'name' field
    - Author dictionaries with 'first_name' and 'last_name'
    - Plain text values
    - Missing and empty values
    """
    # Handle missing scalar values safely.
    if value is None or value is pd.NA:
        return pd.NA

    if isinstance(value, float) and pd.isna(value):
        return pd.NA

    if isinstance(value, str):
        value = value.strip()

        if not value:
            return pd.NA

        try:
            parsed = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            # Keep ordinary text if it is not a Python list/dictionary.
            return value

        value = parsed

    if isinstance(value, dict):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        # If parsing resulted in a scalar string/number, retain it.
        text = str(value).strip()
        return text if text else pd.NA

    cleaned = []

    for item in items:
        if isinstance(item, dict):
            # MyAnimeList author objects use first_name and last_name.
            first_name = str(item.get("first_name") or "").strip()
            last_name = str(item.get("last_name") or "").strip()
            author_name = " ".join(
                part for part in (first_name, last_name) if part
            )

            # Other metadata dictionaries commonly use a 'name' field.
            if not author_name:
                author_name = str(item.get("name") or "").strip()

            # A few source records may use a title field instead.
            if not author_name:
                author_name = str(item.get("title") or "").strip()

            if author_name:
                cleaned.append(author_name)

        elif item is not None:
            item_text = str(item).strip()
            if item_text:
                cleaned.append(item_text)

    # Remove duplicate entries while preserving their original order.
    cleaned = list(dict.fromkeys(cleaned))

    return "|".join(cleaned) if cleaned else pd.NA


def missing_count(series):
    """Count both true missing values and empty strings."""
    empty_strings = series.map(
        lambda value: isinstance(value, str) and not value.strip()
    )

    return int((series.isna() | empty_strings).sum())


# --------------------------------------------------
# 4. Load source dataset
# --------------------------------------------------
def main():
    if not RAW_FILE.exists():
        raise FileNotFoundError(
            f"Cannot find {RAW_FILE}. "
            "Place manga.csv in data/raw/."
        )

    print("Loading raw dataset...")

    df = pd.read_csv(RAW_FILE, low_memory=False)

    original_rows = len(df)
    original_columns = len(df.columns)

    # Standardize column names.
    df.columns = (
        df.columns.str.strip()
        .str.lower()
        .str.replace(" ", "_", regex=False)
    )

    # --------------------------------------------------
    # 5. Remove duplicate rows and IDs
    # --------------------------------------------------
    duplicate_rows = int(df.duplicated().sum())
    df = df.drop_duplicates()

    duplicate_ids = 0

    if "manga_id" in df.columns:
        duplicate_ids = int(df["manga_id"].duplicated().sum())

        df = df.drop_duplicates(
            subset=["manga_id"],
            keep="first"
        )

    # --------------------------------------------------
    # 6. Clean text columns
    # --------------------------------------------------
    text_columns = [
        "title",
        "title_english",
        "title_japanese",
        "type",
        "status",
        "synopsis",
        "background",
    ]

    for column in text_columns:
        if column in df.columns:
            df[column] = df[column].map(
                lambda value: (
                    value.strip() if isinstance(value, str) else value
                )
            )
            df[column] = df[column].replace("", pd.NA)

    # --------------------------------------------------
    # 7. Standardize type and content-format labels
    # --------------------------------------------------
    # Normalize source types first:
    # "one_shot" -> "one_shot"
    # "light_novel" -> "light_novel"
    # "MANGA" -> "manga"
    df["type"] = df["type"].map(
        lambda value: (
            value.strip().casefold().replace(" ", "_")
            if isinstance(value, str)
            else value
        )
    )

    # Convert normalized source types to readable labels.
    df["content_format"] = (
        df["type"]
        .map(FORMAT_MAP)
        .fillna("Other")
    )

    # --------------------------------------------------
    # 8. Convert numeric columns
    # --------------------------------------------------
    numeric_columns = [
        "score",
        "scored_by",
        "volumes",
        "chapters",
        "members",
        "favorites",
    ]

    for column in numeric_columns:
        if column in df.columns:
            df[column] = pd.to_numeric(
                df[column],
                errors="coerce"
            )

    # Ratings should be within the 1–10 range.
    # Missing ratings remain missing, not zero.
    invalid_scores = 0

    if "score" in df.columns:
        bad_score = (
            df["score"].notna()
            & ~df["score"].between(1, 10)
        )

        invalid_scores = int(bad_score.sum())
        df.loc[bad_score, "score"] = float("nan")

    # Counts cannot be negative.
    invalid_counts = {}

    count_columns = [
        "scored_by",
        "volumes",
        "chapters",
        "members",
        "favorites",
    ]

    for column in count_columns:
        if column in df.columns:
            bad_count = (
                df[column].notna()
                & (df[column] < 0)
            )

            invalid_counts[column] = int(bad_count.sum())
            df.loc[bad_count, column] = float("nan")

    # --------------------------------------------------
    # 9. Parse publication dates
    # --------------------------------------------------
    date_columns = [
        "start_date",
        "end_date",
        "real_start_date",
        "real_end_date",
    ]

    invalid_dates = {}

    for column in date_columns:
        if column in df.columns:
            original_values = df[column].copy()

            was_present = (
                original_values.notna()
                & original_values.astype("string")
                .str.strip()
                .ne("")
            )

            df[column] = pd.to_datetime(
                df[column],
                errors="coerce",
                format="mixed"
            )

            invalid_dates[column] = int(
                (was_present & df[column].isna()).sum()
            )

    # Detect publication end dates before start dates.
    invalid_date_ranges = 0

    if {"start_date", "end_date"}.issubset(df.columns):
        bad_range = (
            df["start_date"].notna()
            & df["end_date"].notna()
            & (df["end_date"] < df["start_date"])
        )

        invalid_date_ranges = int(bad_range.sum())

        # Preserve the start date and clear the inconsistent end date.
        df.loc[bad_range, "end_date"] = pd.NaT

    # --------------------------------------------------
    # 10. Normalize list-like metadata
    # --------------------------------------------------
    list_columns = [
        "genres",
        "themes",
        "demographics",
        "authors",
        "serializations",
        "title_synonyms",
    ]

    for column in list_columns:
        if column in df.columns:
            df[column] = df[column].map(clean_list_column)

    # --------------------------------------------------
    # 11. Save cleaned dataset
    # --------------------------------------------------
    output_file = OUTPUT_DIR / "manga_cleaned.csv"

    df.to_csv(
        output_file,
        index=False,
        encoding="utf-8-sig"
    )

    # --------------------------------------------------
    # 12. Generate data-quality report
    # --------------------------------------------------
    report_file = REPORT_DIR / "data_quality_report.txt"

    with open(report_file, "w", encoding="utf-8") as report:
        report.write("EMBER - DATA QUALITY REPORT\n")
        report.write("=" * 50 + "\n\n")

        report.write(f"Source file: {RAW_FILE.name}\n")
        report.write(f"Original rows: {original_rows}\n")
        report.write(f"Original columns: {original_columns}\n")
        report.write(f"Cleaned rows: {len(df)}\n")
        report.write(f"Cleaned columns: {len(df.columns)}\n")
        report.write(f"Exact duplicate rows found: {duplicate_rows}\n")
        report.write(f"Duplicate IDs found: {duplicate_ids}\n")
        report.write(
            f"Invalid ratings changed to missing: {invalid_scores}\n"
        )
        report.write(
            f"Invalid date ranges corrected: {invalid_date_ranges}\n"
        )

        report.write("\nInvalid negative counts changed to missing:\n")
        for column, count in invalid_counts.items():
            report.write(f"{column}: {count}\n")

        report.write("\nUnparseable non-empty dates:\n")
        for column, count in invalid_dates.items():
            report.write(f"{column}: {count}\n")

        report.write("\nCONTENT FORMAT DISTRIBUTION\n")
        report.write("-" * 30 + "\n")
        report.write(
            df["content_format"]
            .value_counts(dropna=False)
            .to_string()
        )

        report.write("\n\nMISSING VALUES AFTER CLEANING\n")
        report.write("-" * 30 + "\n")

        for column in df.columns:
            count = missing_count(df[column])
            percentage = count / len(df) * 100 if len(df) else 0

            report.write(
                f"{column}: {count} ({percentage:.2f}%)\n"
            )

        report.write("\nCLEANING DECISIONS\n")
        report.write("-" * 30 + "\n")
        report.write("- Preserved the original raw dataset.\n")
        report.write(
            "- Removed exact duplicate rows and duplicate IDs.\n"
        )
        report.write(
            "- Standardized column names and content-format labels.\n"
        )
        report.write(
            "- Normalized type values using lowercase and underscores.\n"
        )
        report.write(
            "- Converted numeric columns and publication dates.\n"
        )
        report.write(
            "- Invalid ratings and negative counts were set to missing.\n"
        )
        report.write(
            "- Missing ratings, dates, chapters and volumes were retained.\n"
        )
        report.write(
            "- List-like metadata was normalized using | separators.\n"
        )
        report.write(
            "- Author names were extracted from first_name and last_name "
            "fields where available.\n"
        )
        report.write(
            "- End dates earlier than start dates were cleared.\n"
        )
        report.write(
            "- This report covers the current MyAnimeList source only.\n"
        )

    # --------------------------------------------------
    # 13. Print summary
    # --------------------------------------------------
    print("\nPREPROCESSING COMPLETED")
    print("-" * 35)

    print(f"Original rows: {original_rows}")
    print(f"Cleaned rows: {len(df)}")
    print(f"Cleaned columns: {len(df.columns)}")
    print(f"Exact duplicate rows found: {duplicate_rows}")
    print(f"Duplicate IDs found: {duplicate_ids}")
    print(f"Invalid ratings: {invalid_scores}")
    print(f"Invalid date ranges: {invalid_date_ranges}")

    print("\nContent format distribution:")
    print(df["content_format"].value_counts(dropna=False).to_string())

    if "authors" in df.columns:
        print(f"\nMissing authors: {missing_count(df['authors'])}")

    print(f"\nCleaned dataset: {output_file}")
    print(f"Quality report: {report_file}")


if __name__ == "__main__":
    main()
