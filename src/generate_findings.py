from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SPARK_DIR = ROOT / "analysis" / "outputs" / "spark"
OUT_FILE = ROOT / "analysis" / "FINDINGS.md"


def read(name):
    p = SPARK_DIR / f"{name}.csv"
    return pd.read_csv(p) if p.exists() else None


def fmt(v):
    if pd.isna(v):
        return "-"
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int,)) or (isinstance(v, float) and float(v).is_integer()):
        return f"{int(v):,}"
    if isinstance(v, float):
        return f"{v:,.3f}".rstrip("0").rstrip(".")
    return str(v)


def md_table(df, cols, n=10):
    cols = [c for c in cols if c in df.columns]
    d = df[cols].head(n)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, row in d.iterrows():
        cells = []
        for c in cols:
            v = row[c]
            cells.append(str(int(v)) if c in ("year", "decade") and pd.notna(v) else fmt(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def section(title, body, takeaway=None):
    out = [f"## {title}", "", body, ""]
    if takeaway:
        out += [f"**Takeaway:** {takeaway}", ""]
    return "\n".join(out)


def main():
    parts = ["# EMBER - Key Findings", "",
             "_Auto-generated from `analysis/outputs/spark/*.csv`. "
             "Spark outputs are the canonical tables for charts._", ""]

    rating = read("spark_rating_summary")
    if rating is not None:
        r = rating.iloc[0]
        parts.append(section(
            "1. Dataset and rating overview",
            md_table(rating, list(rating.columns), 1),
            f"{int(r.title_count):,} titles, of which {r.pct_rated}% have a score "
            f"(mean {r.mean_score}, median {r.median_score}, SD {r.sd_score})."))

    fmt_df = read("spark_format_summary")
    if fmt_df is not None:
        top = fmt_df.iloc[0]
        best = fmt_df[fmt_df.rated_count >= 100].sort_values("mean_weighted_score", ascending=False)
        take = f"'{top.content_format}' is the largest format ({int(top.title_count):,} titles)."
        if len(best):
            b = best.iloc[0]
            take += (f" Among formats with 100+ rated titles, '{b.content_format}' has the highest "
                     f"mean weighted score ({b.mean_weighted_score}), but only {b.pct_rated}% of its "
                     f"titles are rated, so treat it as a rated-subset result.")
        parts.append(section(
            "2. Content-format comparison",
            md_table(fmt_df, ["content_format", "title_count", "pct_rated", "mean_score",
                              "median_score", "mean_weighted_score", "median_members"], 10),
            take))

    genre = read("spark_genre_summary")
    if genre is not None:
        rel = genre[genre.reliable]
        take = (f"Most common genre: {genre.iloc[0].genre} "
                f"({genre.iloc[0].pct_of_all_titles}% of titles).")
        if len(rel):
            b = rel.sort_values("mean_weighted_score", ascending=False).iloc[0]
            take += f" Highest weighted score among reliable genres: {b.genre} ({b.mean_weighted_score})."
        parts.append(section(
            "3. Genre summary (top 10 by volume)",
            md_table(genre, ["genre", "title_count", "pct_of_all_titles", "mean_score",
                             "mean_weighted_score", "median_members"], 10),
            take))

    pairs = read("spark_genre_pairs")
    if pairs is not None and len(pairs):
        by_count = pairs.sort_values("pair_count", ascending=False)
        rel = pairs[pairs.reliable]
        by_score = rel.sort_values("mean_weighted_score", ascending=False)
        by_lift = rel.sort_values("lift", ascending=False)
        c = by_count.iloc[0]
        body = ["**Most frequent pairs**", "",
                md_table(by_count, ["genre_a", "genre_b", "pair_count", "lift",
                                    "mean_score", "mean_weighted_score"], 10), ""]
        take = (f"The most frequent pairing is {c.genre_a} + {c.genre_b} "
                f"({int(c.pair_count):,} titles, lift {c.lift}).")
        if len(by_score):
            s = by_score.iloc[0]
            body += ["**Best-scoring pairs (reliable only)**", "",
                     md_table(by_score, ["genre_a", "genre_b", "pair_count", "mean_weighted_score",
                                         "mean_score"], 10), ""]
            take += f" Best-scoring reliable pair: {s.genre_a} + {s.genre_b} ({s.mean_weighted_score})."
        if len(by_lift):
            l = by_lift.iloc[0]
            body += ["**Strongest affinity (highest lift, reliable only)**", "",
                     md_table(by_lift, ["genre_a", "genre_b", "pair_count", "lift",
                                        "mean_score"], 10)]
            take += (f" Strongest affinity: {l.genre_a} + {l.genre_b} (lift {l.lift}; "
                     f">1 means they co-occur more than chance).")
        parts.append(section("4. Genre combinations", "\n".join(body), take))

    decade = read("spark_publication_decade")
    if decade is not None:
        parts.append(section(
            "5. Publication trend by decade",
            md_table(decade, ["decade", "title_count", "rated_count", "mean_score",
                              "mean_weighted_score"], 15),
            "Recent decades may be incomplete or less rated because of the snapshot date."))

    cr = read("spark_creator_summary_by_weighted_score")
    if cr is not None and len(cr):
        parts.append(section(
            "6. Creators (10+ rated titles, ranked by weighted score)",
            md_table(cr, ["creator", "title_count", "rated_count", "mean_score",
                          "mean_weighted_score", "total_members"], 10),
            f"Top creator by weighted score: {cr.iloc[0].creator}."))

    corr = read("spark_numeric_correlations")
    if corr is not None:
        corr = corr[(corr.feature_a != "weighted_score") & (corr.feature_b != "weighted_score")]
        sc = corr[(corr.feature_a == "score") | (corr.feature_b == "score")].dropna(subset=["spearman"])
        take = None
        if len(sc):
            top = sc.reindex(sc.spearman.abs().sort_values(ascending=False).index).iloc[0]
            other = top.feature_b if top.feature_a == "score" else top.feature_a
            take = (f"Feature most associated with score: {other} (Spearman {top.spearman}). "
                    "Correlation is not causation.")
        parts.append(section(
            "7. Correlations (Spearman, pairwise)",
            md_table(corr.dropna(subset=["spearman"]), ["feature_a", "feature_b", "n_pairs",
                                                          "spearman"], 12),
            take))

    demo = SPARK_DIR / "spark_distributed_demo.txt"
    if demo.exists():
        parts.append(section(
            "8. Distributed-style processing demo",
            "```text\n" + demo.read_text(encoding="utf-8") + "\n```",
            "The genre-pair job explodes each title into pairs, shuffles by (genre_a, genre_b) "
            "and aggregates; the Exchange in the plan is the shuffle."))

    parts.append(section(
        "Caveats",
        "- members/favorites are engagement proxies, not sales.\n"
        "- Genre rows overlap (a title has several genres).\n"
        "- Groups with fewer than 30 rated titles are flagged unreliable.\n"
        "- Findings describe this catalogue snapshot only."))

    OUT_FILE.write_text("\n".join(parts), encoding="utf-8")
    print(f"Wrote {OUT_FILE}")


if __name__ == "__main__":
    main()