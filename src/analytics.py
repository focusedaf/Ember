from pathlib import Path
import sqlite3
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "processed" / "manga_cleaned.csv"
OUT_DIR = ROOT / "analysis" / "outputs"
REPORT_DIR = ROOT / "reports"

def require_columns(df, columns):
    missing = [c for c in columns if c not in df.columns]
    if missing:
        print(f"Note: some optional analysis columns are absent: {missing}")

def main():
    if not DATA_FILE.exists():
        raise FileNotFoundError(
            f"Cleaned dataset not found: {DATA_FILE}\n"
            "Run preprocessing script first."
        )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(DATA_FILE, low_memory=False)
    df.columns = df.columns.str.strip().str.lower()
    print(f"Loaded {len(df):,} rows and {len(df.columns)} columns.")
    require_columns(df, ["title", "score", "genres", "authors", "start_date",
                         "members", "favorites", "content_format"])

   
    for col in ["score", "scored_by", "members", "favorites", "chapters",
                "volumes", "start_date"]:
        if col in df.columns:
            if col == "start_date":
                df[col] = pd.to_datetime(df[col], errors="coerce")
            else:
                df[col] = pd.to_numeric(df[col], errors="coerce")

 
    sql_df = df.copy()
    for col in ["genres", "authors", "themes", "demographics", "serializations"]:
        if col in sql_df.columns:
            sql_df[col] = sql_df[col].fillna("").astype(str)
    with sqlite3.connect(":memory:") as conn:
        sql_df.to_sql("titles", conn, index=False, if_exists="replace")

        queries = {
            "format_summary": """
                SELECT COALESCE(content_format, 'Unknown') AS content_format,
                       COUNT(*) AS title_count,
                       ROUND(AVG(score), 3) AS average_score,
                       ROUND(AVG(members), 1) AS average_members
                FROM titles GROUP BY content_format ORDER BY title_count DESC
            """,
            "rating_summary": """
                SELECT COUNT(score) AS rated_titles,
                       ROUND(AVG(score), 3) AS mean_score,
                       ROUND(MIN(score), 3) AS minimum_score,
                       ROUND(MAX(score), 3) AS maximum_score
                FROM titles
            """,
            "creator_summary": """
                SELECT TRIM(value) AS creator, COUNT(*) AS title_count,
                       ROUND(AVG(score), 3) AS average_score,
                       SUM(COALESCE(members, 0)) AS total_members
                FROM titles, json_each(
                    '["' || REPLACE(REPLACE(authors, '"', '\\"'), '|', '","') || '"]'
                )
                WHERE TRIM(value) <> ''
                GROUP BY TRIM(value)
                HAVING COUNT(*) >= 2
                ORDER BY title_count DESC LIMIT 30
            """,
            "publication_year": """
                SELECT CAST(substr(start_date, 1, 4) AS INTEGER) AS year,
                       COUNT(*) AS title_count,
                       ROUND(AVG(score), 3) AS average_score
                FROM titles
                WHERE start_date IS NOT NULL
                  AND substr(start_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
                GROUP BY year ORDER BY year
            """,
            "popularity_summary": """
                SELECT title, score, members, favorites, scored_by
                FROM titles WHERE members IS NOT NULL
                ORDER BY members DESC LIMIT 50
            """,
        }
        results = {}
        for name, query in queries.items():
            try:
                results[name] = pd.read_sql_query(query, conn)
            except Exception as exc:
                print(f"Query '{name}' skipped: {exc}")

        
        if "genres" in df.columns:
            genre_df = df[["genres"] + [c for c in ["score", "members", "favorites"] if c in df.columns]].copy()
            genre_df["genres"] = genre_df["genres"].fillna("").astype(str).str.split("|")
            genre_df = genre_df.explode("genres")
            genre_df["genres"] = genre_df["genres"].str.strip()
            genre_df = genre_df[genre_df["genres"].ne("")]
            if not genre_df.empty:
                agg = {"title_count": ("genres", "size")}
                if "score" in genre_df.columns:
                    agg["average_score"] = ("score", "mean")
                if "members" in genre_df.columns:
                    agg["average_members"] = ("members", "mean")
                if "favorites" in genre_df.columns:
                    agg["total_favorites"] = ("favorites", "sum")
                results["genre_summary"] = genre_df.groupby("genres").agg(**agg).reset_index()
                results["genre_summary"] = results["genre_summary"].sort_values("title_count", ascending=False)

        
        numeric = [c for c in ["score", "scored_by", "members", "favorites", "chapters", "volumes"]
                   if c in df.columns]
        if len(numeric) >= 2:
            results["numeric_correlations"] = df[numeric].corr(numeric_only=True).round(3).reset_index(names="feature")

        for name, table in results.items():
            table.to_csv(OUT_DIR / f"{name}.csv", index=False, encoding="utf-8-sig")
            print(f"Saved {name}.csv ({len(table)} rows)")

    report_path = REPORT_DIR / "analytics_summary.txt"
    with report_path.open("w", encoding="utf-8") as f:
        f.write("EMBER — ANALYTICS SUMMARY\n")
        f.write(f"Input: {DATA_FILE.relative_to(ROOT)}\n")
        f.write(f"Rows: {len(df):,}\nColumns: {len(df.columns)}\n\n")
        f.write("Available columns:\n" + ", ".join(df.columns) + "\n\n")
        f.write("Generated output tables:\n")
        for name, table in results.items():
            f.write(f"- {name}.csv: {len(table)} rows\n")
        f.write("\nInterpretation notes:\n")
        f.write("- Averages exclude missing numeric values.\n")
        f.write("- Popularity uses the dataset's members/favorites fields as proxies, not actual sales.\n")
        f.write("- Correlation does not establish causation.\n")
        f.write("- Findings describe this source dataset only; do not generalize to formats not represented.\n")
    print(f"\nSummary report: {report_path}")
    print(f"CSV outputs: {OUT_DIR}")

if __name__ == "__main__":
    main()
