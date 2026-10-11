import re
import sqlite3
from itertools import combinations
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "processed" / "manga_cleaned.csv"
OUT_DIR = ROOT / "analysis" / "outputs"
REPORT_DIR = ROOT / "reports"

MIN_PAIR_COUNT = 30
MIN_RATED_GROUP = 30
MIN_YEAR, MAX_YEAR = 1900, pd.Timestamp.today().year


def require_columns(df, columns):
    missing = [c for c in columns if c not in df.columns]
    if missing:
        print(f"Note: some optional analysis columns are absent: {missing}")


def to_unique_list(value, clean=None):
    if not isinstance(value, str):
        return []
    out, seen = [], set()
    for item in value.split("|"):
        item = clean(item) if clean else item.strip()
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def clean_creator(name):
    name = re.sub(r"\s*\([^)]*\)", "", name)
    return re.sub(r"\s+", " ", name).strip()


def main():
    if not DATA_FILE.exists():
        raise FileNotFoundError(
            f"Cleaned dataset not found: {DATA_FILE}\nRun preprocessing script first.")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(DATA_FILE, low_memory=False)
    df.columns = df.columns.str.strip().str.lower()
    print(f"Loaded {len(df):,} rows and {len(df.columns)} columns.")
    require_columns(df, ["title", "score", "genres", "authors", "start_date",
                         "members", "favorites", "content_format"])

    for col in ["score", "scored_by", "members", "favorites", "chapters", "volumes"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "start_date" in df.columns:
        df["start_date"] = pd.to_datetime(df["start_date"], errors="coerce")
        df["pub_year"] = df["start_date"].dt.year
        df.loc[~df["pub_year"].between(MIN_YEAR, MAX_YEAR), "pub_year"] = pd.NA
    if "genres" in df.columns:
        df["genre_list"] = df["genres"].apply(to_unique_list)
        df["n_genres"] = df["genre_list"].apply(len)

    results = {}

    sql_df = df.drop(columns=["genre_list"], errors="ignore").copy()
    for col in ["genres", "authors", "themes", "demographics", "serializations"]:
        if col in sql_df.columns:
            sql_df[col] = sql_df[col].fillna("").astype(str)
    sql_df["start_date"] = sql_df["start_date"].astype(str) if "start_date" in sql_df.columns else None

    with sqlite3.connect(":memory:") as conn:
        sql_df.to_sql("titles", conn, index=False, if_exists="replace")
        queries = {
            "format_summary": """
                SELECT COALESCE(content_format, 'Unknown') AS content_format,
                       COUNT(*) AS title_count,
                       COUNT(score) AS rated_count,
                       ROUND(AVG(score), 3) AS average_score,
                       ROUND(AVG(members), 1) AS average_members
                FROM titles GROUP BY COALESCE(content_format, 'Unknown')
                ORDER BY title_count DESC
            """,
            "rating_summary": """
                SELECT COUNT(score) AS rated_titles,
                       ROUND(AVG(score), 3) AS mean_score,
                       ROUND(MIN(score), 3) AS minimum_score,
                       ROUND(MAX(score), 3) AS maximum_score
                FROM titles
            """,
            "publication_year": """
                SELECT CAST(substr(start_date, 1, 4) AS INTEGER) AS year,
                       COUNT(*) AS title_count,
                       ROUND(AVG(score), 3) AS average_score
                FROM titles
                WHERE substr(start_date, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
                GROUP BY year ORDER BY year
            """,
            "popularity_summary": """
                SELECT title, score, members, favorites, scored_by
                FROM titles WHERE members IS NOT NULL
                ORDER BY members DESC LIMIT 50
            """,
        }
        for name, query in queries.items():
            try:
                results[name] = pd.read_sql_query(query, conn)
            except Exception as exc:
                print(f"Query '{name}' skipped: {exc}")

    if "genre_list" in df.columns:
        metric_cols = [c for c in ["score", "members", "favorites"] if c in df.columns]
        gdf = df[["genre_list"] + metric_cols].explode("genre_list").dropna(subset=["genre_list"])
        gdf = gdf.rename(columns={"genre_list": "genre"})
        agg = {"title_count": ("genre", "size")}
        if "score" in gdf:
            agg["rated_count"] = ("score", "count")
            agg["average_score"] = ("score", "mean")
        if "members" in gdf:
            agg["median_members"] = ("members", "median")
        if "favorites" in gdf:
            agg["total_favorites"] = ("favorites", "sum")
        results["genre_summary"] = (gdf.groupby("genre").agg(**agg).reset_index()
                                    .sort_values("title_count", ascending=False))

        n_with_genre = int((df["n_genres"] >= 1).sum())
        single = gdf.groupby("genre").size().to_dict()
        rows = []
        for genres, score, members in zip(df["genre_list"],
                                          df.get("score", pd.Series(dtype=float)),
                                          df.get("members", pd.Series(dtype=float))):
            for a, b in combinations(sorted(genres), 2):
                rows.append((a, b, score, members))
        if rows:
            pairs = pd.DataFrame(rows, columns=["genre_a", "genre_b", "score", "members"])
            pt = (pairs.groupby(["genre_a", "genre_b"])
                  .agg(pair_count=("score", "size"), rated_count=("score", "count"),
                       mean_score=("score", "mean"), median_members=("members", "median"))
                  .reset_index())
            pt["count_a"] = pt["genre_a"].map(single)
            pt["count_b"] = pt["genre_b"].map(single)
            pt["lift"] = pt["pair_count"] * n_with_genre / (pt["count_a"] * pt["count_b"])
            pt["reliable"] = pt["rated_count"] >= MIN_RATED_GROUP
            pt = pt[pt["pair_count"] >= MIN_PAIR_COUNT].round(3)
            results["genre_pairs"] = pt.sort_values("pair_count", ascending=False)

    if "authors" in df.columns:
        cdf = df.assign(creator=df["authors"].apply(lambda v: to_unique_list(v, clean_creator)))
        cdf = cdf.explode("creator").dropna(subset=["creator"])
        results["creator_summary"] = (
            cdf.groupby("creator")
            .agg(title_count=("creator", "size"), rated_count=("score", "count"),
                 average_score=("score", "mean"), total_members=("members", "sum"))
            .query("title_count >= 2").round(3)
            .sort_values("title_count", ascending=False).head(50).reset_index())

    numeric = [c for c in ["score", "scored_by", "members", "favorites", "chapters",
                           "volumes", "pub_year", "n_genres"] if c in df.columns]
    if len(numeric) >= 2:
        results["numeric_correlations"] = (
            df[numeric].astype(float).corr(method="spearman").round(3)
            .reset_index(names="feature"))

    for name, table in results.items():
        table.to_csv(OUT_DIR / f"{name}.csv", index=False, encoding="utf-8-sig")
        print(f"Saved {name}.csv ({len(table)} rows)")

    report_path = REPORT_DIR / "analytics_summary.txt"
    with report_path.open("w", encoding="utf-8") as f:
        f.write("EMBER - ANALYTICS SUMMARY (pandas)\n")
        f.write(f"Input: {DATA_FILE.relative_to(ROOT)}\n")
        f.write(f"Rows: {len(df):,}\nColumns: {len(df.columns)}\n\n")
        f.write("Available columns:\n" + ", ".join(df.columns) + "\n\n")
        f.write("Generated output tables:\n")
        for name, table in results.items():
            f.write(f"- {name}.csv: {len(table)} rows\n")
        f.write("\nInterpretation notes:\n")
        f.write("- Averages exclude missing numeric values.\n")
        f.write("- Correlations here are Spearman (matches the Spark script).\n")
        f.write("- Popularity uses members/favorites as proxies, not actual sales.\n")
        f.write("- lift > 1 means a genre pair co-occurs more than chance.\n")
        f.write("- Correlation does not establish causation.\n")
        f.write("- Findings describe this source dataset only.\n")
    print(f"\nSummary report: {report_path}\nCSV outputs: {OUT_DIR}")


if __name__ == "__main__":
    main()