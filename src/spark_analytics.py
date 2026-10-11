import os
import sys
from pathlib import Path
from datetime import date


os.environ["PYSPARK_PYTHON"] = sys.executable
os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable

from pyspark.ml.feature import VectorAssembler
from pyspark.ml.stat import Correlation
from pyspark.sql import SparkSession, functions as F

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "processed" / "manga_cleaned.csv"
OUT_DIR = ROOT / "analysis" / "outputs" / "spark"


BAYES_M = 50
MIN_RATED_GROUP = 30
MIN_RATED_CREATOR = 10
MIN_VOTES_RANKING = 1000
MIN_YEAR, MAX_YEAR = 1900, date.today().year
LIST_SEPARATOR = r"\|"
ADULT_GENRES = ["Hentai", "Erotica"]

CORE_COLS = ["score", "scored_by", "members", "favorites"]
NUMERIC_COLS = ["score", "scored_by", "members", "favorites", "chapters", "volumes"]


def save(df, name):
    pdf = df.toPandas()
    path = OUT_DIR / f"{name}.csv"
    pdf.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"Saved {path} ({len(pdf):,} rows)")
    return pdf


def metric_aggs():
    """Standard aggregate block used by every summary table."""
    return [
        F.count("*").alias("title_count"),
        F.count("score").alias("rated_count"),
        F.round(F.avg("score"), 3).alias("mean_score"),
        F.round(F.expr("percentile_approx(score, 0.5)"), 2).alias("median_score"),
        F.round(F.stddev("score"), 3).alias("sd_score"),
        F.round(F.avg("weighted_score"), 3).alias("mean_weighted_score"),
        F.round(F.avg("members"), 1).alias("mean_members"),
        F.expr("percentile_approx(members, 0.5)").alias("median_members"),
        F.expr("percentile_approx(members, 0.9)").alias("p90_members"),
        F.round(F.avg("favorites"), 1).alias("mean_favorites"),
        F.expr("percentile_approx(favorites, 0.5)").alias("median_favorites"),
        F.sum("favorites").alias("total_favorites"),
    ]


def add_pct_rated(df):
    return df.withColumn(
        "pct_rated", F.round(F.col("rated_count") / F.col("title_count") * 100, 1)
    )


def main():
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Cleaned dataset not found: {DATA_FILE}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    spark = (SparkSession.builder
             .appName("EMBER-Decay-Analytics")
             .master("local[*]")
             .config("spark.sql.shuffle.partitions", "4")
             .getOrCreate())
    spark.sparkContext.setLogLevel("WARN")
    try:

        df = (spark.read.option("header", True)
              .option("inferSchema", True)
              .option("multiLine", True)
              .option("escape", '"')
              .csv(str(DATA_FILE)))
        df = df.toDF(*[c.strip().lower() for c in df.columns])

        missing = [c for c in CORE_COLS if c not in df.columns]
        if missing:
            raise ValueError(f"Required columns missing from dataset: {missing}")

        for c in NUMERIC_COLS:
            if c in df.columns:
                df = df.withColumn(c, F.col(c).cast("double"))


        df = df.cache()
        total_rows = df.count()
        print(f"Spark loaded {total_rows:,} rows across {len(df.columns)} columns.")
        df.printSchema()


        null_audit = df.select(
            [F.round(F.mean(F.col(c).isNull().cast("int")) * 100, 2).alias(c)
             for c in df.columns]
        )
        audit_pdf = null_audit.toPandas().T.reset_index()
        audit_pdf.columns = ["column", "pct_null"]
        audit_pdf = audit_pdf.sort_values("pct_null", ascending=False)
        audit_pdf.to_csv(OUT_DIR / "spark_null_audit.csv", index=False, encoding="utf-8-sig")
        print("Null audit (% null per column):")
        print(audit_pdf.to_string(index=False))


        global_mean = df.agg(F.avg("score")).first()[0]
        print(f"Global mean score C = {global_mean:.4f}; Bayesian m = {BAYES_M}")
        df = df.withColumn(
            "weighted_score",
            F.when(
                F.col("score").isNotNull() & F.col("scored_by").isNotNull(),
                (F.col("scored_by") / (F.col("scored_by") + F.lit(BAYES_M))) * F.col("score")
                + (F.lit(BAYES_M) / (F.col("scored_by") + F.lit(BAYES_M))) * F.lit(global_mean),
            ),
        )


        year_expr = None
        for date_col in ["start_date", "real_start_date"]:
            if date_col in df.columns:
                parsed = F.regexp_extract(F.col(date_col).cast("string"), r"^(\d{4})", 1)
                parsed = F.when(parsed != "", parsed.cast("int"))
                year_expr = parsed if year_expr is None else F.coalesce(year_expr, parsed)
        if year_expr is not None:
            df = df.withColumn("pub_year", year_expr)
            df = df.withColumn(
                "pub_year",
                F.when(F.col("pub_year").between(MIN_YEAR, MAX_YEAR), F.col("pub_year")),
            )
            unparsed = df.filter(F.col("pub_year").isNull()).count()
            print(f"Titles without a usable publication year: {unparsed:,} "
                  f"({unparsed / total_rows * 100:.1f}%)")


        if "genres" in df.columns:
            adult_regex = "|".join(ADULT_GENRES)
            df = df.withColumn(
                "is_adult_genre",
                F.coalesce(F.col("genres"), F.lit("")).rlike(adult_regex),
            )
        else:
            df = df.withColumn("is_adult_genre", F.lit(False))

        df = df.cache()
        df.createOrReplaceTempView("titles")


        rating = df.agg(
            F.count("*").alias("title_count"),
            F.count("score").alias("rated_titles"),
            F.round(F.count("score") / F.count("*") * 100, 1).alias("pct_rated"),
            F.round(F.avg("score"), 3).alias("mean_score"),
            F.round(F.expr("percentile_approx(score, 0.5)"), 2).alias("median_score"),
            F.round(F.stddev("score"), 3).alias("sd_score"),
            F.min("score").alias("minimum_score"),
            F.expr("percentile_approx(score, 0.25)").alias("p25_score"),
            F.expr("percentile_approx(score, 0.75)").alias("p75_score"),
            F.max("score").alias("maximum_score"),
            F.round(F.avg("weighted_score"), 3).alias("mean_weighted_score"),
        )
        rating.show(truncate=False)
        save(rating, "spark_rating_summary")


        adult_split = (df.groupBy("is_adult_genre").agg(*metric_aggs()))
        adult_split = add_pct_rated(adult_split).orderBy("is_adult_genre")
        adult_split.show(truncate=False)
        save(adult_split, "spark_adult_vs_nonadult_summary")


        if "content_format" in df.columns:
            fmt = (df.groupBy(F.coalesce("content_format", F.lit("Unknown")).alias("content_format"))
                   .agg(*metric_aggs()))
            fmt = add_pct_rated(fmt).orderBy(F.desc("title_count"))
            fmt.show(20, truncate=False)
            save(fmt, "spark_format_summary")


            fmt_sfw = (df.filter(~F.col("is_adult_genre"))
                       .groupBy(F.coalesce("content_format", F.lit("Unknown")).alias("content_format"))
                       .agg(*metric_aggs()))
            fmt_sfw = add_pct_rated(fmt_sfw).orderBy(F.desc("title_count"))
            save(fmt_sfw, "spark_format_summary_excl_adult")


        if "pub_year" in df.columns:
            year = (df.filter(F.col("pub_year").isNotNull())
                    .groupBy("pub_year").agg(*metric_aggs())
                    .withColumnRenamed("pub_year", "year"))
            year = add_pct_rated(year).withColumn(
                "reliable", F.col("rated_count") >= MIN_RATED_GROUP
            ).orderBy("year")
            save(year, "spark_publication_year")
            save(year.filter("reliable"), "spark_publication_year_reliable")

            decade = (df.filter(F.col("pub_year").isNotNull())
                      .withColumn("decade", (F.floor(F.col("pub_year") / 10) * 10).cast("int"))
                      .groupBy("decade").agg(*metric_aggs()))
            decade = add_pct_rated(decade).orderBy("decade")
            save(decade, "spark_publication_decade")


        for list_col, out_name, label in [
            ("genres", "spark_genre_summary", "genre"),
            ("themes", "spark_theme_summary", "theme"),
            ("demographics", "spark_demographic_summary", "demographic"),
        ]:
            if list_col not in df.columns:
                continue
            exploded = (df.select(
                            F.explode(F.split(F.coalesce(F.col(list_col), F.lit("")),
                                              LIST_SEPARATOR)).alias(label),
                            "score", "scored_by", "members", "favorites", "weighted_score")
                        .withColumn(label, F.trim(F.col(label)))
                        .filter(F.col(label) != ""))
            summary = exploded.groupBy(label).agg(*metric_aggs())

            summary = (summary
                       .withColumn("pct_of_all_titles",
                                   F.round(F.col("title_count") / F.lit(total_rows) * 100, 2))
                       .withColumn("reliable", F.col("rated_count") >= MIN_RATED_GROUP))
            summary = add_pct_rated(summary).orderBy(F.desc("title_count"))
            summary.show(30, truncate=False)
            save(summary, out_name)


        if "authors" in df.columns:
            creators = (df.select(
                            F.explode(F.split(F.coalesce(F.col("authors"), F.lit("")),
                                              LIST_SEPARATOR)).alias("creator"),
                            "score", "scored_by", "members", "favorites", "weighted_score")

                        .withColumn("creator", F.regexp_replace("creator", r"\s*\([^)]*\)", ""))
                        .withColumn("creator", F.trim(F.regexp_replace("creator", r"\s+", " ")))
                        .filter(F.col("creator") != ""))
            cr = creators.groupBy("creator").agg(*metric_aggs())
            cr = add_pct_rated(cr)

            cr_members = creators.groupBy("creator").agg(F.sum("members").alias("total_members"))
            cr = cr.join(cr_members, "creator")
            cr_by_volume = cr.orderBy(F.desc("title_count")).limit(50)
            save(cr_by_volume, "spark_creator_summary_by_output")
            cr_by_quality = (cr.filter(F.col("rated_count") >= MIN_RATED_CREATOR)
                             .orderBy(F.desc("mean_weighted_score")).limit(50))
            save(cr_by_quality, "spark_creator_summary_by_weighted_score")


        base_cols = [c for c in ["title", "content_format", "score", "scored_by",
                                 "weighted_score", "members", "favorites"] if c in df.columns]
        top_pop = (df.filter(F.col("members").isNotNull())
                   .select(*base_cols)
                   .withColumn("weighted_score", F.round("weighted_score", 3))
                   .orderBy(F.desc("members")).limit(50))
        save(top_pop, "spark_popularity_summary")

        top_rated = (df.filter(F.col("scored_by") >= MIN_VOTES_RANKING)
                     .select(*base_cols)
                     .withColumn("weighted_score", F.round("weighted_score", 3))
                     .orderBy(F.desc("weighted_score")).limit(50))
        save(top_rated, "spark_top_rated_titles")


        corr_cols = [c for c in NUMERIC_COLS if c in df.columns]
        corr_rows = []
        for i, a in enumerate(corr_cols):
            for b in corr_cols[i + 1:]:
                pair = df.select(a, b).dropna()
                n = pair.count()
                if n < 3:
                    corr_rows.append((a, b, n, None))
                    continue
                vec = (VectorAssembler(inputCols=[a, b], outputCol="f")
                       .transform(pair).select("f"))
                rho = Correlation.corr(vec, "f", "spearman").head()[0].toArray()[0][1]
                corr_rows.append((a, b, n, round(float(rho), 3)))


        import pandas as pd
        corr_pdf = pd.DataFrame(corr_rows, columns=["feature_a", "feature_b", "n_pairs", "spearman"])
        corr_pdf = corr_pdf.reindex(corr_pdf["spearman"].abs().sort_values(ascending=False).index)
        print(corr_pdf.to_string(index=False))
        corr_path = OUT_DIR / "spark_numeric_correlations.csv"
        corr_pdf.to_csv(corr_path, index=False, encoding="utf-8-sig")
        print(f"Saved {corr_path} ({len(corr_pdf):,} rows)")


        notes = [
            "EMBER SPARK ANALYTICS - INTERPRETATION NOTES",
            f"Rows: {total_rows:,}",
            "- score averages use rated titles only; see rated_count / pct_rated in every table.",
            f"- weighted_score = Bayesian average with m={BAYES_M}, C={global_mean:.3f}.",
            "- members/favorites are engagement proxies, not sales; they are heavily skewed,"
            " so prefer median_* columns over mean_*.",
            "- Genre/theme/demographic rows overlap (one title can appear in several).",
            f"- Groups with rated_count < {MIN_RATED_GROUP} are flagged reliable=False.",
            "- Correlations are Spearman, computed pairwise on rows with both values (see n_pairs).",
            "- Correlation does not establish causation; large series are survivorship-biased.",
            "- Recent years may be incomplete or unrated due to the snapshot date.",
            "- Findings describe this catalogue snapshot only.",
        ]
        (OUT_DIR / "spark_analytics_notes.txt").write_text("\n".join(notes), encoding="utf-8")
        print("\n".join(notes))
    finally:
        spark.stop()


if __name__ == "__main__":
    main()