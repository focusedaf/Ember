import contextlib
import io
import os
import sys
import time
from collections import defaultdict
from datetime import date
from itertools import combinations
from pathlib import Path

os.environ["PYSPARK_PYTHON"] = sys.executable
os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable

import pandas as pd
from pyspark.ml.feature import VectorAssembler
from pyspark.ml.stat import Correlation
from pyspark.sql import SparkSession, functions as F

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "processed" / "manga_cleaned.csv"
SQL_FILE = ROOT / "analysis" / "queries.sql"
OUT_DIR = ROOT / "analysis" / "outputs" / "spark"
SQL_OUT_DIR = OUT_DIR / "sql"

BAYES_M = 50
MIN_RATED_GROUP = 30
MIN_RATED_CREATOR = 10
MIN_PAIR_COUNT = 30
MIN_VOTES_RANKING = 1000
MIN_YEAR, MAX_YEAR = 1900, date.today().year
LIST_SEPARATOR = r"\|"
ADULT_GENRES = ["Hentai", "Erotica"]

CORE_COLS = ["score", "scored_by", "members", "favorites"]
NUMERIC_COLS = ["score", "scored_by", "members", "favorites", "chapters", "volumes"]
CORR_EXTRA = ["pub_year", "n_genres", "weighted_score"]
INPUT_PARTITIONS = 8
SQL_QUERY_NAMES = [
    "format_comparison", "format_comparison_excl_adult", "most_popular_titles",
    "best_rated_titles", "publication_trend_by_year", "rating_summary",
    "genre_summary", "genre_pair_combinations", "creator_summary",
    "creator_quality_ranking",
]


def save(df, name, out_dir=None):
    out_dir = out_dir or OUT_DIR
    pdf = df.toPandas()
    path = out_dir / f"{name}.csv"
    pdf.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"Saved {path} ({len(pdf):,} rows)")
    return pdf


def metric_aggs():
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


def list_array(col_name, clean=None):
    clean = clean or (lambda x: F.trim(x))
    arr = F.transform(
        F.split(F.coalesce(F.col(col_name), F.lit("")), LIST_SEPARATOR), clean
    )
    return F.array_distinct(F.filter(arr, lambda x: x != ""))


def creator_clean(x):
    no_role = F.regexp_replace(x, r"\s*\([^)]*\)", "")
    return F.trim(F.regexp_replace(no_role, r"\s+", " "))


def load_data(spark):
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
    return df.repartition(INPUT_PARTITIONS).cache()


def add_features(df, global_mean):
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

    if "genres" in df.columns:
        df = df.withColumn("is_adult_genre",
                           F.coalesce(F.col("genres"), F.lit("")).rlike("|".join(ADULT_GENRES)))
        df = df.withColumn("genre_list", list_array("genres"))
        df = df.withColumn("n_genres", F.size("genre_list").cast("double"))
    else:
        df = df.withColumn("is_adult_genre", F.lit(False))

    return df.cache()


def null_audit(df):
    audit = df.select([F.round(F.mean(F.col(c).isNull().cast("int")) * 100, 2).alias(c)
                       for c in df.columns if c != "genre_list"])
    pdf = audit.toPandas().T.reset_index()
    pdf.columns = ["column", "pct_null"]
    pdf = pdf.sort_values("pct_null", ascending=False)
    pdf.to_csv(OUT_DIR / "spark_null_audit.csv", index=False, encoding="utf-8-sig")
    print("Null audit (% null per column):")
    print(pdf.to_string(index=False))


def basic_summaries(df):
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

    adult = add_pct_rated(df.groupBy("is_adult_genre").agg(*metric_aggs())).orderBy("is_adult_genre")
    adult.show(truncate=False)
    save(adult, "spark_adult_vs_nonadult_summary")

    if "content_format" in df.columns:
        key = F.coalesce("content_format", F.lit("Unknown")).alias("content_format")
        fmt = add_pct_rated(df.groupBy(key).agg(*metric_aggs())).orderBy(F.desc("title_count"))
        fmt.show(20, truncate=False)
        save(fmt, "spark_format_summary")

        fmt_sfw = add_pct_rated(
            df.filter(~F.col("is_adult_genre")).groupBy(key).agg(*metric_aggs())
        ).orderBy(F.desc("title_count"))
        save(fmt_sfw, "spark_format_summary_excl_adult")


def publication_trends(df, total_rows):
    if "pub_year" not in df.columns:
        return
    unparsed = df.filter(F.col("pub_year").isNull()).count()
    print(f"Titles without a usable publication year: {unparsed:,} "
          f"({unparsed / total_rows * 100:.1f}%)")

    year = (df.filter(F.col("pub_year").isNotNull())
            .groupBy("pub_year").agg(*metric_aggs())
            .withColumnRenamed("pub_year", "year"))
    year = add_pct_rated(year).withColumn(
        "reliable", F.col("rated_count") >= MIN_RATED_GROUP).orderBy("year")
    save(year, "spark_publication_year")
    save(year.filter("reliable"), "spark_publication_year_reliable")

    decade = (df.filter(F.col("pub_year").isNotNull())
              .withColumn("decade", (F.floor(F.col("pub_year") / 10) * 10).cast("int"))
              .groupBy("decade").agg(*metric_aggs()))
    save(add_pct_rated(decade).orderBy("decade"), "spark_publication_decade")


def list_column_summaries(df, total_rows):
    for list_col, out_name, label in [
        ("genres", "spark_genre_summary", "genre"),
        ("themes", "spark_theme_summary", "theme"),
        ("demographics", "spark_demographic_summary", "demographic"),
    ]:
        if list_col not in df.columns:
            continue
        exploded = df.select(
            F.explode(list_array(list_col)).alias(label),
            "score", "scored_by", "members", "favorites", "weighted_score")
        summary = (exploded.groupBy(label).agg(*metric_aggs())
                   .withColumn("pct_of_all_titles",
                               F.round(F.col("title_count") / F.lit(total_rows) * 100, 2))
                   .withColumn("reliable", F.col("rated_count") >= MIN_RATED_GROUP))
        summary = add_pct_rated(summary).orderBy(F.desc("title_count"))
        summary.show(30, truncate=False)
        save(summary, out_name)


def creator_summaries(df):
    if "authors" not in df.columns:
        return
    creators = df.select(
        F.explode(list_array("authors", creator_clean)).alias("creator"),
        "score", "scored_by", "members", "favorites", "weighted_score")
    cr = add_pct_rated(creators.groupBy("creator").agg(*metric_aggs()))
    cr_members = creators.groupBy("creator").agg(F.sum("members").alias("total_members"))
    cr = cr.join(cr_members, "creator")

    save(cr.orderBy(F.desc("title_count")).limit(50), "spark_creator_summary_by_output")
    save(cr.filter(F.col("rated_count") >= MIN_RATED_CREATOR)
         .orderBy(F.desc("mean_weighted_score")).limit(50),
         "spark_creator_summary_by_weighted_score")


def popularity_tables(df):
    base_cols = [c for c in ["title", "content_format", "score", "scored_by",
                             "weighted_score", "members", "favorites"] if c in df.columns]
    top_pop = (df.filter(F.col("members").isNotNull()).select(*base_cols)
               .withColumn("weighted_score", F.round("weighted_score", 3))
               .orderBy(F.desc("members")).limit(50))
    save(top_pop, "spark_popularity_summary")

    top_rated = (df.filter(F.col("scored_by") >= MIN_VOTES_RANKING).select(*base_cols)
                 .withColumn("weighted_score", F.round("weighted_score", 3))
                 .orderBy(F.desc("weighted_score")).limit(50))
    save(top_rated, "spark_top_rated_titles")


def build_pair_source(g):
    return (g.select("score", "members", "weighted_score", "genre_list",
                     F.explode("genre_list").alias("genre_a"))
             .select("score", "members", "weighted_score", "genre_a",
                     F.explode("genre_list").alias("genre_b"))
             .filter(F.col("genre_a") < F.col("genre_b")))


def genre_pair_analysis(g):
    n_with_genre = g.count()
    singles = (g.select(F.explode("genre_list").alias("genre"))
               .groupBy("genre").agg(F.count("*").alias("genre_count")))

    pairs = (build_pair_source(g)
             .groupBy("genre_a", "genre_b")
             .agg(F.count("*").alias("pair_count"),
                  F.count("score").alias("rated_count"),
                  F.round(F.avg("score"), 3).alias("mean_score"),
                  F.round(F.avg("weighted_score"), 3).alias("mean_weighted_score"),
                  F.expr("percentile_approx(members, 0.5)").alias("median_members")))

    sa = singles.select(F.col("genre").alias("genre_a"), F.col("genre_count").alias("count_a"))
    sb = singles.select(F.col("genre").alias("genre_b"), F.col("genre_count").alias("count_b"))
    pairs = (pairs.join(F.broadcast(sa), "genre_a").join(F.broadcast(sb), "genre_b")
             .withColumn("pct_of_a", F.round(F.col("pair_count") / F.col("count_a") * 100, 1))
             .withColumn("pct_of_b", F.round(F.col("pair_count") / F.col("count_b") * 100, 1))

             .withColumn("lift", F.round(
                 F.col("pair_count") * F.lit(float(n_with_genre))
                 / (F.col("count_a") * F.col("count_b")), 3))
             .withColumn("reliable", F.col("rated_count") >= MIN_RATED_GROUP)
             .filter(F.col("pair_count") >= MIN_PAIR_COUNT)
             .select("genre_a", "genre_b", "pair_count", "count_a", "count_b",
                     "pct_of_a", "pct_of_b", "lift", "rated_count", "mean_score",
                     "mean_weighted_score", "median_members", "reliable")
             .cache())

    pairs.orderBy(F.desc("pair_count")).show(20, truncate=False)
    save(pairs.orderBy(F.desc("pair_count")), "spark_genre_pairs")
    save(pairs.orderBy(F.desc("pair_count")).limit(50), "spark_genre_pairs_top_by_count")
    save(pairs.filter("reliable").orderBy(F.desc("mean_weighted_score")).limit(50),
         "spark_genre_pairs_top_by_weighted_score")
    save(pairs.filter("reliable").orderBy(F.desc("lift")).limit(50),
         "spark_genre_pairs_top_by_lift")
    return pairs


def pandas_pair_count(pdf):
    cnt, ssum, scnt = defaultdict(int), defaultdict(float), defaultdict(int)
    for genres, score in zip(pdf["genres"], pdf["score"]):
        items = sorted({x.strip() for x in str(genres).split("|") if x.strip()}) \
            if isinstance(genres, str) else []
        for a, b in combinations(items, 2):
            cnt[(a, b)] += 1
            if pd.notna(score):
                ssum[(a, b)] += score
                scnt[(a, b)] += 1
    return len(cnt)


def distributed_demo(spark, df, g):
    lines = ["DISTRIBUTED-STYLE PROCESSING DEMO (genre-pair job)", "=" * 56]
    lines.append(f"Spark master                  : {spark.sparkContext.master}")
    lines.append(f"Default parallelism           : {spark.sparkContext.defaultParallelism}")
    lines.append(f"Input DataFrame partitions    : {df.rdd.getNumPartitions()}")
    lines.append(f"spark.sql.shuffle.partitions  : {spark.conf.get('spark.sql.shuffle.partitions')}")

    dist = (df.groupBy(F.spark_partition_id().alias("partition"))
            .count().orderBy("partition").toPandas())
    lines.append("\nRows per input partition:")
    lines.append(dist.to_string(index=False))

    agg = (build_pair_source(g).groupBy("genre_a", "genre_b")
           .agg(F.count("*").alias("pair_count"), F.avg("score").alias("mean_score")))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        agg.explain()
    lines.append("\nPhysical plan (look for 'Exchange hashpartitioning' = the shuffle):")
    plan = []
    for line in buf.getvalue().splitlines():
        plan.append(line[:150])
        if "InMemoryTableScan" in line:
            plan.append("   ... (cached input scan omitted)")
            break
    lines.append("\n".join(plan))

    agg.count()
    t0 = time.perf_counter()
    n_spark = agg.count()
    t_spark = time.perf_counter() - t0

    pdf = df.select("genres", "score").toPandas()
    t0 = time.perf_counter()
    n_pandas = pandas_pair_count(pdf)
    t_pandas = time.perf_counter() - t0

    lines.append("Timing (same aggregation, warm Spark run):")
    lines.append(f"  Spark  : {t_spark:8.2f} s  ({n_spark:,} distinct pairs)")
    lines.append(f"  Pandas : {t_pandas:8.2f} s  ({n_pandas:,} distinct pairs)")
    lines.append("  Note: on one laptop Spark can be slower than pandas; the point is the")
    lines.append("  explode -> shuffle -> aggregate pattern, which scales by adding executors.")

    text = "\n".join(lines)
    (OUT_DIR / "spark_distributed_demo.txt").write_text(text, encoding="utf-8")
    print(text)


def run_sql_file(spark, sql_path, out_dir):
    if not sql_path.exists():
        print(f"SQL file not found, skipping: {sql_path}")
        return
    out_dir.mkdir(parents=True, exist_ok=True)

    names = iter(SQL_QUERY_NAMES)
    ok, failed = [], []
    for i, chunk in enumerate(sql_path.read_text(encoding="utf-8").split(";"), 1):
        stmt = chunk.strip()
        if not stmt:
            continue
        is_ddl = stmt.upper().startswith(("CREATE", "DROP", "SET"))
        name = f"statement_{i}" if is_ddl else next(names, f"query_{i}")
        try:
            res = spark.sql(stmt)
            if is_ddl:
                continue
            pdf = res.toPandas()
            pdf.to_csv(out_dir / f"{name}.csv", index=False, encoding="utf-8-sig")
            print(f"[SQL OK] {name}: {len(pdf):,} rows -> {out_dir / (name + '.csv')}")
            ok.append(name)
        except Exception as exc:
            print(f"[SQL FAILED] {name}: {str(exc)[:300]}")
            failed.append(name)
    print(f"SQL file summary: {len(ok)} succeeded, {len(failed)} failed {failed or ''}")


def correlations(df):
    corr_cols = [c for c in NUMERIC_COLS + CORR_EXTRA if c in df.columns]
    rows = []
    for i, a in enumerate(corr_cols):
        for b in corr_cols[i + 1:]:
            pair = df.select(a, b).dropna()
            n = pair.count()
            if n < 3:
                rows.append((a, b, n, None))
                continue
            vec = VectorAssembler(inputCols=[a, b], outputCol="f").transform(pair).select("f")
            rho = Correlation.corr(vec, "f", "spearman").head()[0].toArray()[0][1]
            rows.append((a, b, n, round(float(rho), 3)))

    pdf = pd.DataFrame(rows, columns=["feature_a", "feature_b", "n_pairs", "spearman"])
    pdf = pdf.reindex(pdf["spearman"].abs().sort_values(ascending=False).index)
    print(pdf.to_string(index=False))
    path = OUT_DIR / "spark_numeric_correlations.csv"
    pdf.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"Saved {path} ({len(pdf):,} rows)")


def write_notes(total_rows, global_mean):
    notes = [
        "EMBER SPARK ANALYTICS - INTERPRETATION NOTES",
        f"Rows: {total_rows:,}",
        "- score averages use rated titles only; see rated_count / pct_rated in every table.",
        f"- weighted_score = Bayesian average with m={BAYES_M}, C={global_mean:.3f}.",
        "- members/favorites are engagement proxies, not sales; they are heavily skewed,"
        " so prefer median_* columns over mean_*.",
        "- Genre/theme/demographic rows overlap (one title can appear in several).",
        "- Repeated genres/creators inside one title are de-duplicated before counting.",
        f"- Groups with rated_count < {MIN_RATED_GROUP} are flagged reliable=False.",
        f"- Genre pairs with fewer than {MIN_PAIR_COUNT} co-occurrences are dropped.",
        "- lift = pair_count * N / (count_a * count_b); lift > 1 means the pair co-occurs "
        "more often than independence would predict.",
        "- Correlations are Spearman, computed pairwise on rows with both values (see n_pairs).",
        "- Correlation does not establish causation; large series are survivorship-biased.",
        "- Recent years may be incomplete or unrated due to the snapshot date.",
        "- Findings describe this catalogue snapshot only.",
    ]
    (OUT_DIR / "spark_analytics_notes.txt").write_text("\n".join(notes), encoding="utf-8")
    print("\n".join(notes))


def main():
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Cleaned dataset not found: {DATA_FILE}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SQL_OUT_DIR.mkdir(parents=True, exist_ok=True)

    spark = (SparkSession.builder
             .appName("EMBER-Analytics")
             .master("local[*]")
             .config("spark.sql.shuffle.partitions", "4")
             .getOrCreate())
    spark.sparkContext.setLogLevel("WARN")
    try:
        raw = load_data(spark)
        total_rows = raw.count()
        print(f"Spark loaded {total_rows:,} rows across {len(raw.columns)} columns.")
        raw.printSchema()

        raw.createOrReplaceTempView("titles")

        global_mean = raw.agg(F.avg("score")).first()[0]
        print(f"Global mean score C = {global_mean:.4f}; Bayesian m = {BAYES_M}")
        df = add_features(raw, global_mean)

        null_audit(df)
        basic_summaries(df)
        publication_trends(df, total_rows)
        list_column_summaries(df, total_rows)
        creator_summaries(df)
        popularity_tables(df)

        if "genre_list" in df.columns:
            g = df.filter(F.size("genre_list") >= 1).cache()
            genre_pair_analysis(g)
            distributed_demo(spark, df, g)

        run_sql_file(spark, SQL_FILE, SQL_OUT_DIR)
        correlations(df)
        write_notes(total_rows, global_mean)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()