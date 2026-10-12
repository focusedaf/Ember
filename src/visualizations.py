import os
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

warnings.filterwarnings("ignore", message="Glyph")
warnings.filterwarnings("ignore", category=UserWarning, module="seaborn")

ROOT = Path(os.environ.get("EMBER_ROOT", Path(__file__).resolve().parent.parent))
DATA_FILE = ROOT / "data" / "processed" / "manga_cleaned.csv"
SPARK_DIR = ROOT / "analysis" / "outputs" / "spark"
VIZ_DIR = ROOT / "visualizations"

ADULT_GENRES = {"Hentai", "Erotica"}
MIN_YEAR = 1900
MAX_YEAR = pd.Timestamp.today().year
NUMERIC_COLS = ["score", "scored_by", "members", "favorites", "chapters", "volumes"]

BLUE = "#3B6FB6"
ORANGE = "#E4793B"
GREY = "#9AA3AE"
DARK = "#2B2F36"

sns.set_theme(style="whitegrid", context="notebook")
plt.rcParams.update({
    "figure.dpi": 110,
    "savefig.dpi": 160,
    "axes.titleweight": "bold",
    "axes.titlesize": 11,
    "axes.spines.top": False,
    "axes.spines.right": False,
})

CHARTS = {}


def chart(name):
    def deco(fn):
        fn.chart_name = name
        CHARTS[name] = fn
        return fn
    return deco


def load_dataset():
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Cleaned dataset not found: {DATA_FILE}")
    df = pd.read_csv(DATA_FILE, low_memory=False)
    df.columns = df.columns.str.strip().str.lower()
    for c in NUMERIC_COLS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    year = pd.Series(np.nan, index=df.index, dtype="float64")
    for col in ["start_date", "real_start_date"]:
        if col in df.columns:
            parsed = pd.to_datetime(df[col], errors="coerce").dt.year
            year = year.fillna(parsed.astype("float64"))
    df["pub_year"] = year.where(year.between(MIN_YEAR, MAX_YEAR))

    if "content_format" in df.columns:
        df["content_format"] = df["content_format"].fillna("Unknown")
    if "genres" in df.columns:
        split = df["genres"].fillna("").astype(str).str.split("|")
        df["genre_list"] = split.apply(lambda xs: sorted({x.strip() for x in xs if x.strip()}))
        df["n_genres"] = df["genre_list"].apply(len)
        df["is_adult"] = df["genre_list"].apply(lambda g: bool(ADULT_GENRES.intersection(g)))
    return df


class Data:
    def __init__(self):
        self.df = load_dataset()
        self._spark = {}
        order = self.df["content_format"].value_counts().index if "content_format" in self.df else []
        palette = sns.color_palette("deep", max(len(order), 1))
        self.format_colors = {f: palette[i % len(palette)] for i, f in enumerate(order)}

    def spark(self, name):
        if name not in self._spark:
            path = SPARK_DIR / f"{name}.csv"
            self._spark[name] = pd.read_csv(path) if path.exists() else None
        return self._spark[name]


def tables(d, *names):
    out = [d.spark(n) for n in names]
    if any(t is None or t.empty for t in out):
        return None
    return out


def short(text, n=34):
    text = str(text)
    return text if len(text) <= n else text[: n - 1] + "…"


def finalize(fig, title, note=None):
    fig.suptitle(title, x=0.01, ha="left", fontsize=14, fontweight="bold")
    fig.tight_layout(rect=(0, 0.04 if note else 0.0, 1, 0.95))
    if note:
        fig.text(0.01, 0.008, note, fontsize=8, color=GREY, ha="left", va="bottom")
    return fig


def barh(ax, labels, values, colors=None, fmt="{:,.0f}"):
    y = np.arange(len(labels))
    vals = np.asarray(values, dtype=float)
    ax.barh(y, vals, color=colors if colors is not None else BLUE)
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    top = float(np.nanmax(vals)) if len(vals) else 1.0
    for yi, v in zip(y, vals):
        ax.text(v + top * 0.01, yi, fmt.format(v), va="center", fontsize=9, color=DARK)
    ax.set_xlim(0, top * 1.16)
    ax.grid(axis="y", visible=False)


def diverging_barh(ax, labels, values, ref, fmt="{:.3f}"):
    y = np.arange(len(labels))
    vals = np.asarray(values, dtype=float)
    ax.barh(y, vals - ref, left=ref, color=[BLUE if v >= ref else ORANGE for v in vals])
    ax.axvline(ref, color=DARK, lw=1)
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    span = max(float(np.abs(vals - ref).max()), 1e-6)
    ax.set_xlim(ref - span * 1.4, ref + span * 1.4)
    for yi, v in zip(y, vals):
        right = v >= ref
        ax.text(v + (span * 0.04 if right else -span * 0.04), yi, fmt.format(v),
                va="center", ha="left" if right else "right", fontsize=9, color=DARK)
    ax.grid(axis="y", visible=False)


def dotplot(ax, labels, values, fmt="{:.3f}"):
    y = np.arange(len(labels))
    vals = np.asarray(values, dtype=float)
    lo, hi = float(vals.min()), float(vals.max())
    pad = (hi - lo) * 0.15 or 0.1
    ax.hlines(y, lo - pad, vals, color=GREY, lw=1.5)
    ax.scatter(vals, y, color=BLUE, s=55, zorder=3)
    for yi, v in zip(y, vals):
        ax.text(v + pad * 0.25, yi, fmt.format(v), va="center", fontsize=9, color=DARK)
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlim(lo - pad, hi + pad * 2.4)
    ax.grid(axis="y", visible=False)


def overall_weighted(d, fallback):
    r = d.spark("spark_rating_summary")
    if r is not None and "mean_weighted_score" in r and not r.empty:
        return float(r["mean_weighted_score"].iloc[0])
    return float(fallback)


def adult_colors(labels):
    return [GREY if x in ADULT_GENRES else BLUE for x in labels]


def adult_legend(ax):
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=BLUE, label="Other genres"),
                       Patch(color=GREY, label="Adult-tagged genres")],
              loc="lower right", frameon=False)


@chart("01_missing_values")
def missing_values(d):
    drop = ["genre_list", "n_genres", "is_adult", "pub_year"]
    miss = d.df.drop(columns=drop, errors="ignore").isna().mean().mul(100)
    miss = miss[miss > 0].sort_values(ascending=False).head(20)
    if miss.empty:
        return None
    fig, ax = plt.subplots(figsize=(9, 0.38 * len(miss) + 1.8))
    barh(ax, list(miss.index), list(miss.values),
         [ORANGE if v >= 50 else BLUE for v in miss.values], "{:.1f}%")
    ax.set_xlabel("% of titles with a missing value")
    return finalize(fig, "Missing values by column (top 20)",
                    "Orange = more than half of titles missing. Score is missing for unrated titles.")


@chart("02_rating_distribution")
def rating_distribution(d):
    s = d.df["score"].dropna()
    fig, ax = plt.subplots(figsize=(9, 5))
    sns.histplot(s, bins=40, color=BLUE, ax=ax)
    ax.axvline(s.median(), color=ORANGE, ls="--", lw=2, label=f"Median {s.median():.2f}")
    ax.axvline(s.mean(), color=DARK, ls=":", lw=2, label=f"Mean {s.mean():.2f}")
    ax.set_xlabel("Score")
    ax.set_ylabel("Titles")
    ax.legend(frameon=False)
    return finalize(fig, f"Distribution of scores ({len(s):,} rated titles of {len(d.df):,})",
                    f"Standard deviation {s.std():.2f}; middle 50% between {s.quantile(.25):.2f} and {s.quantile(.75):.2f}.")


@chart("03_format_composition")
def format_composition(d):
    g = d.df.groupby("content_format").agg(titles=("title", "size"), rated=("score", "count"))
    g["pct_rated"] = g["rated"] / g["titles"] * 100
    g = g.sort_values("titles", ascending=False)
    fig, axes = plt.subplots(1, 2, figsize=(12, 0.5 * len(g) + 2.4))
    share = g["titles"] / g["titles"].sum() * 100
    axes[0].barh(np.arange(len(g)), g["titles"], color=[d.format_colors.get(f, BLUE) for f in g.index])
    axes[0].set_yticks(np.arange(len(g)))
    axes[0].set_yticklabels(g.index)
    axes[0].invert_yaxis()
    axes[0].set_xscale("log")
    for i, (t, s) in enumerate(zip(g["titles"], share)):
        axes[0].text(t * 1.08, i, f"{t:,} ({s:.1f}%)", va="center", fontsize=9)
    axes[0].set_xlim(right=g["titles"].max() * 6)
    axes[0].set_xlabel("Titles (log scale)")
    axes[0].set_title("Catalogue size")
    axes[0].grid(axis="y", visible=False)
    barh(axes[1], list(g.index), list(g["pct_rated"]), [d.format_colors.get(f, BLUE) for f in g.index], "{:.1f}%")
    axes[1].set_yticklabels([])
    axes[1].set_xlabel("% of titles that have a score")
    axes[1].set_title("Share rated")
    return finalize(fig, "Content formats: how big, and how much is rated")


@chart("04_score_by_format")
def score_by_format(d):
    r = d.df[d.df["score"].notna()]
    counts = r.groupby("content_format").size()
    keep = counts[counts >= 30].index
    r = r[r["content_format"].isin(keep)]
    if r.empty:
        return None
    order = list(r.groupby("content_format")["score"].median().sort_values(ascending=False).index)
    fig, ax = plt.subplots(figsize=(9.5, 0.7 * len(order) + 2))
    sns.boxplot(data=r, y="content_format", x="score", order=order, color=BLUE,
                fliersize=2, linewidth=1, ax=ax)
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels([f"{o} (n={counts[o]:,})" for o in order])
    ax.set_xlabel("Score")
    ax.set_ylabel("")
    return finalize(fig, "Score distribution by content format (formats with 30+ rated titles)",
                    "Box = middle 50%, line = median. Formats with a small rated share may not represent the whole format.")


@chart("05_popularity_skew")
def popularity_skew(d):
    cols = [c for c in ["members", "favorites", "scored_by"] if c in d.df.columns]
    if not cols:
        return None
    fig, axes = plt.subplots(1, len(cols), figsize=(5 * len(cols), 4.6))
    for ax, c in zip(np.atleast_1d(axes), cols):
        s = d.df[c].dropna()
        sns.histplot(np.log10(s + 1), bins=40, color=BLUE, ax=ax)
        ax.axvline(np.log10(s.median() + 1), color=ORANGE, ls="--", lw=2, label=f"median {s.median():,.0f}")
        ax.axvline(np.log10(s.mean() + 1), color=DARK, ls=":", lw=2, label=f"mean {s.mean():,.0f}")
        ax.set_xlabel(f"log10({c} + 1)")
        ax.set_ylabel("Titles")
        ax.legend(frameon=False, fontsize=8)
    return finalize(fig, "Popularity measures are extremely right-skewed",
                    "A few titles hold most of the engagement, so medians describe a typical title better than means.")


@chart("06_outliers")
def outliers(d):
    cols = [c for c in ["score", "members", "favorites", "scored_by", "chapters", "volumes"] if c in d.df.columns]
    pct = {}
    frames = []
    for c in cols:
        s = d.df[c].dropna()
        q1, q3 = s.quantile(.25), s.quantile(.75)
        iqr = q3 - q1
        pct[c] = float(((s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)).mean() * 100)
        z = s if c == "score" else np.log10(s + 1)
        frames.append(pd.DataFrame({"feature": c, "value": (z - z.mean()) / z.std()}))
    long = pd.concat(frames)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    sns.boxplot(data=long, y="feature", x="value", order=cols, color=BLUE, fliersize=1.5, linewidth=1, ax=axes[0])
    axes[0].set_xlabel("Standardised value (log10 for count features)")
    axes[0].set_ylabel("")
    axes[0].set_title("Spread and extreme values")
    ordered = sorted(pct, key=pct.get, reverse=True)
    barh(axes[1], ordered, [pct[c] for c in ordered], BLUE, "{:.1f}%")
    axes[1].set_xlabel("% flagged by the 1.5 x IQR rule (raw values)")
    axes[1].set_title("Share of outliers")
    return finalize(fig, "Outlier check across numeric features",
                    "Outliers in members/favorites are real blockbuster titles, so they are kept and handled with medians and log scales.")


@chart("07_score_vs_popularity")
def score_vs_popularity(d):
    r = d.df[d.df["score"].notna() & (d.df["members"] > 0)]
    if len(r) < 50:
        return None
    t = pd.DataFrame({"x": np.log10(r["members"]), "y": r["score"]})
    rho = r["score"].corr(r["members"], method="spearman")
    fig, ax = plt.subplots(figsize=(9, 6))
    hb = ax.hexbin(t["x"], t["y"], gridsize=45, bins="log", cmap="Blues", mincnt=1)
    t["bin"] = pd.qcut(t["x"], 20, duplicates="drop")
    med = t.groupby("bin", observed=True)[["x", "y"]].median()
    ax.plot(med["x"], med["y"], color=ORANGE, lw=2.5, label="Median score per popularity bin")
    fig.colorbar(hb, ax=ax, label="Titles (log)")
    ax.set_xlabel("log10(members)")
    ax.set_ylabel("Score")
    ax.legend(frameon=False, loc="lower right")
    return finalize(fig, f"Score vs popularity (Spearman rho = {rho:.2f})",
                    "More popular titles tend to score higher, but the relationship is moderate, not causal.")


@chart("08_members_vs_favorites")
def members_vs_favorites(d):
    r = d.df[(d.df["members"] > 0) & (d.df["favorites"] > 0)]
    if len(r) < 50:
        return None
    rho = d.df["members"].corr(d.df["favorites"], method="spearman")
    fig, ax = plt.subplots(figsize=(8.5, 6))
    hb = ax.hexbin(np.log10(r["members"]), np.log10(r["favorites"]), gridsize=45, bins="log", cmap="Oranges", mincnt=1)
    fig.colorbar(hb, ax=ax, label="Titles (log)")
    ax.set_xlabel("log10(members)")
    ax.set_ylabel("log10(favorites)")
    return finalize(fig, f"Members vs favorites (Spearman rho = {rho:.2f} on all titles)",
                    "Titles with zero favorites are excluded from the plot because of the log scale.")


@chart("09_titles_per_year_by_format")
def titles_per_year(d):
    t = d.df[d.df["pub_year"].between(1960, MAX_YEAR)]
    if t.empty:
        return None
    top = list(t["content_format"].value_counts().head(4).index)
    t = t.assign(fmt=np.where(t["content_format"].isin(top), t["content_format"], "Other"))
    pivot = t.groupby(["pub_year", "fmt"]).size().unstack(fill_value=0)
    cols = [c for c in top if c in pivot.columns] + (["Other"] if "Other" in pivot.columns else [])
    pivot = pivot[cols]
    fig, ax = plt.subplots(figsize=(10.5, 5.5))
    ax.stackplot(pivot.index, pivot.T.values, labels=cols, colors=sns.color_palette("deep", len(cols)), alpha=0.9)
    ax.set_xlabel("Publication year")
    ax.set_ylabel("Titles started")
    ax.legend(frameon=False, loc="upper left")
    return finalize(fig, "Titles started per year, by content format",
                    f"Latest year ({MAX_YEAR}) is incomplete. Titles without a usable start date are excluded.")


@chart("10_score_trend_by_year")
def score_trend_by_year(d):
    t = tables(d, "spark_publication_year_reliable")
    if t is None:
        return None
    ys = t[0].sort_values("year")
    fig, ax = plt.subplots(figsize=(10.5, 5.5))
    ax2 = ax.twinx()
    ax2.bar(ys["year"], ys["rated_count"], color=GREY, alpha=0.35, width=0.8)
    ax2.set_ylabel("Rated titles (bars)")
    ax2.grid(False)
    ax.set_zorder(ax2.get_zorder() + 1)
    ax.patch.set_visible(False)
    ax.plot(ys["year"], ys["mean_score"], color=BLUE, lw=2.2, marker="o", ms=3, label="Mean score")
    ax.plot(ys["year"], ys["mean_weighted_score"], color=ORANGE, lw=2.2, ls="--", label="Mean weighted score")
    ax.set_xlabel("Publication year")
    ax.set_ylabel("Score")
    ax.legend(frameon=False, loc="lower left")
    return finalize(fig, "Average score by publication year (years with 30+ rated titles)",
                    "Source: Spark publication-year table. Weighted score shrinks titles with few votes toward the overall mean.")


@chart("11_correlation_heatmap")
def correlation_heatmap(d):
    t = tables(d, "spark_numeric_correlations")
    if t is None:
        return None
    c = t[0].dropna(subset=["spearman"])
    c = c[(c["feature_a"] != "weighted_score") & (c["feature_b"] != "weighted_score")]
    preferred = ["score", "scored_by", "members", "favorites", "chapters", "volumes", "pub_year", "n_genres"]
    feats = [f for f in preferred if f in set(c["feature_a"]) | set(c["feature_b"])]
    n = len(feats)
    if n < 2:
        return None
    idx = {f: i for i, f in enumerate(feats)}
    arr = np.full((n, n), np.nan)
    for r in c.itertuples():
        if r.feature_a in idx and r.feature_b in idx:
            arr[idx[r.feature_a], idx[r.feature_b]] = arr[idx[r.feature_b], idx[r.feature_a]] = r.spearman
    np.fill_diagonal(arr, 1.0)
    mask = np.triu(np.ones((n, n), dtype=bool), k=1)
    fig, ax = plt.subplots(figsize=(8.5, 7))
    sns.heatmap(pd.DataFrame(arr, index=feats, columns=feats), mask=mask, annot=True, fmt=".2f",
                cmap="vlag", center=0, vmin=-1, vmax=1, square=True, linewidths=0.5,
                cbar_kws={"shrink": 0.75, "label": "Spearman rho"}, ax=ax)
    ax.grid(False)
    return finalize(fig, "Rank correlations between numeric features",
                    "Source: Spark. Computed pairwise on titles with both values. Correlation is not causation.")


@chart("12_genre_distribution")
def genre_distribution(d):
    t = tables(d, "spark_genre_summary")
    if t is None:
        return None
    g = t[0].sort_values("title_count", ascending=False).head(15)
    fig, ax = plt.subplots(figsize=(10, 6.5))
    barh(ax, list(g["genre"]), list(g["title_count"]), adult_colors(g["genre"]))
    for i, p in enumerate(g["pct_of_all_titles"]):
        ax.text(0.99, i, f"{p:.1f}% of titles", transform=ax.get_yaxis_transform(), ha="right", va="center", fontsize=8, color=GREY)
    ax.set_xlabel("Titles tagged with the genre")
    adult_legend(ax)
    return finalize(fig, "Most common genres (top 15)",
                    "A title can carry several genres, so shares add up to more than 100%.")


@chart("13_genre_quality")
def genre_quality(d):
    t = tables(d, "spark_genre_summary")
    if t is None:
        return None
    g = t[0]
    g = g[g["reliable"].astype(str).str.lower() == "true"] if "reliable" in g else g
    g = g.sort_values("mean_weighted_score", ascending=False)
    ref = overall_weighted(d, g["mean_weighted_score"].mean())
    fig, ax = plt.subplots(figsize=(10, 0.36 * len(g) + 2))
    diverging_barh(ax, list(g["genre"]), list(g["mean_weighted_score"]), ref)
    ax.set_xlabel(f"Mean weighted score (line = overall {ref:.2f})")
    return finalize(fig, "Genre quality: mean weighted score vs the overall average",
                    "Blue = above average, orange = below. 'Award Winning' is a recognition tag rather than a content genre.")


@chart("14_genre_popularity")
def genre_popularity(d):
    t = tables(d, "spark_genre_summary")
    if t is None:
        return None
    g = t[0].sort_values("median_members", ascending=False)
    fig, ax = plt.subplots(figsize=(10, 0.36 * len(g) + 2))
    barh(ax, list(g["genre"]), list(g["median_members"]), adult_colors(g["genre"]))
    ax.set_xlabel("Median members per title")
    adult_legend(ax)
    return finalize(fig, "Genre popularity: median members per title",
                    "Median is used because member counts are extremely skewed.")


@chart("15_theme_summary")
def theme_summary(d):
    t = tables(d, "spark_theme_summary")
    if t is None:
        return None
    th = t[0].sort_values("title_count", ascending=False).head(15)
    ref = overall_weighted(d, th["mean_weighted_score"].mean())
    fig, axes = plt.subplots(1, 2, figsize=(13, 6.2))
    barh(axes[0], list(th["theme"]), list(th["title_count"]))
    axes[0].set_xlabel("Titles")
    axes[0].set_title("Most common themes")
    diverging_barh(axes[1], list(th["theme"]), list(th["mean_weighted_score"]), ref)
    axes[1].set_yticklabels([])
    axes[1].set_xlabel(f"Mean weighted score (line = overall {ref:.2f})")
    axes[1].set_title("Quality of the same themes")
    return finalize(fig, "Themes: volume and quality (top 15 by volume)")


@chart("16_demographics")
def demographics(d):
    t = tables(d, "spark_demographic_summary")
    if t is None:
        return None
    dm = t[0].sort_values("title_count", ascending=False)
    ref = overall_weighted(d, dm["mean_weighted_score"].mean())
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.2))
    barh(axes[0], list(dm["demographic"]), list(dm["title_count"]))
    axes[0].set_title("Titles")
    diverging_barh(axes[1], list(dm["demographic"]), list(dm["mean_weighted_score"]), ref)
    axes[1].set_yticklabels([])
    axes[1].set_title(f"Mean weighted score (line = {ref:.2f})")
    barh(axes[2], list(dm["demographic"]), list(dm["median_members"]))
    axes[2].set_yticklabels([])
    axes[2].set_title("Median members")
    return finalize(fig, "Target demographics compared")


@chart("17_format_comparison")
def format_comparison(d):
    t = tables(d, "spark_format_summary")
    if t is None:
        return None
    f = t[0].sort_values("title_count", ascending=False)
    ref = overall_weighted(d, f["mean_weighted_score"].mean())
    labels = list(f["content_format"])
    fig, axes = plt.subplots(1, 3, figsize=(15, 0.55 * len(f) + 2.4))
    diverging_barh(axes[0], labels, list(f["mean_weighted_score"]), ref)
    axes[0].set_title(f"Mean weighted score (line = {ref:.2f})")
    barh(axes[1], labels, list(f["median_members"]))
    axes[1].set_yticklabels([])
    axes[1].set_title("Median members")
    barh(axes[2], labels, list(f["pct_rated"]), None, "{:.1f}%")
    axes[2].set_yticklabels([])
    axes[2].set_title("% of titles rated")
    return finalize(fig, "Content-format comparison: quality, engagement and rating coverage",
                    "Source: Spark format summary. Low rated coverage means the score reflects only a subset of that format.")


@chart("18_adult_vs_other")
def adult_vs_other(d):
    t = tables(d, "spark_adult_vs_nonadult_summary")
    if t is None:
        return None
    a = t[0].copy()
    a["label"] = a["is_adult_genre"].astype(str).str.lower().map({"true": "Adult-tagged", "false": "Other"})
    a = a.sort_values("label", ascending=False)
    metrics = [("title_count", "Titles"), ("mean_weighted_score", "Mean weighted score"),
               ("median_members", "Median members"), ("mean_favorites", "Mean favorites")]
    fig, axes = plt.subplots(1, 4, figsize=(14, 4))
    for ax, (col, name) in zip(axes, metrics):
        ax.bar(a["label"], a[col], color=[GREY if x == "Adult-tagged" else BLUE for x in a["label"]])
        for i, v in enumerate(a[col]):
            ax.text(i, v, f"{v:,.2f}" if v < 100 else f"{v:,.0f}", ha="center", va="bottom", fontsize=9)
        ax.set_title(name)
        ax.grid(axis="x", visible=False)
        ax.set_ylim(0, a[col].max() * 1.15)
    return finalize(fig, "Adult-tagged genres vs everything else",
                    "Adult-tagged = Hentai or Erotica in the genre list. Mean favorites is shown because adult titles get almost none.")


@chart("19_genre_pair_lift_heatmap")
def pair_lift_heatmap(d):
    t = tables(d, "spark_genre_summary", "spark_genre_pairs")
    if t is None:
        return None
    g, p = t
    genres = list(g.sort_values("title_count", ascending=False)["genre"].head(14))
    n = len(genres)
    idx = {x: i for i, x in enumerate(genres)}
    lift = np.full((n, n), np.nan)
    for r in p.itertuples():
        if r.genre_a in idx and r.genre_b in idx:
            lift[idx[r.genre_a], idx[r.genre_b]] = lift[idx[r.genre_b], idx[r.genre_a]] = r.lift
    log = np.log2(lift)
    annot = np.where(np.isnan(lift), "", np.char.mod("%.1f", lift))
    mask = np.triu(np.ones((n, n), dtype=bool))
    fig, ax = plt.subplots(figsize=(11, 9))
    sns.heatmap(pd.DataFrame(log, index=genres, columns=genres), mask=mask, annot=annot, fmt="",
                cmap="vlag", center=0, vmin=-2, vmax=2, linewidths=0.5, square=True,
                cbar_kws={"shrink": 0.7, "label": "log2(lift)   0 = chance, above 0 = together more often"}, ax=ax)
    ax.grid(False)
    return finalize(fig, "Which genres go together? Pair lift among the 14 most common genres",
                    "Numbers are lift (1.0 = chance). Blank cells have fewer than 30 shared titles.")


@chart("20_top_genre_pairs")
def top_genre_pairs(d):
    t = tables(d, "spark_genre_pairs")
    if t is None:
        return None
    p = t[0].sort_values("pair_count", ascending=False).head(15)
    labels = [f"{a} + {b}" for a, b in zip(p["genre_a"], p["genre_b"])]
    cmap = sns.color_palette("crest", as_cmap=True)
    lo, hi = float(p["mean_weighted_score"].min()), float(p["mean_weighted_score"].max())
    norm = plt.Normalize(lo, hi if hi > lo else lo + 0.01)
    fig, ax = plt.subplots(figsize=(10.5, 6.5))
    barh(ax, labels, list(p["pair_count"]), [cmap(norm(v)) for v in p["mean_weighted_score"]])
    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    fig.colorbar(sm, ax=ax, label="Mean weighted score of the pair")
    ax.set_xlabel("Titles with both genres")
    return finalize(fig, "Most frequent genre combinations (top 15)")


@chart("21_best_scoring_pairs")
def best_scoring_pairs(d):
    t = tables(d, "spark_genre_pairs")
    if t is None:
        return None
    p = t[0]
    p = p[(p["rated_count"] >= 100) & (p["genre_a"] != "Award Winning") & (p["genre_b"] != "Award Winning")]
    p = p.sort_values("mean_weighted_score", ascending=False).head(12)
    if p.empty:
        return None
    ref = overall_weighted(d, p["mean_weighted_score"].mean())
    labels = [f"{a} + {b} (n={int(n):,})" for a, b, n in zip(p["genre_a"], p["genre_b"], p["rated_count"])]
    fig, ax = plt.subplots(figsize=(10.5, 5.8))
    diverging_barh(ax, labels, list(p["mean_weighted_score"]), ref)
    ax.set_xlabel(f"Mean weighted score (line = overall {ref:.2f})")
    return finalize(fig, "Best-scoring genre combinations (100+ rated titles, excluding the 'Award Winning' tag)",
                    "n = rated titles carrying both genres.")


@chart("22_top_popular_titles")
def top_popular_titles(d):
    t = tables(d, "spark_popularity_summary")
    if t is None:
        return None
    p = t[0].sort_values("members", ascending=False).head(15)
    colors = [d.format_colors.get(f, BLUE) for f in p.get("content_format", ["x"] * len(p))]
    fig, ax = plt.subplots(figsize=(10.5, 6.5))
    barh(ax, [short(x) for x in p["title"]], list(p["members"]), colors)
    if "content_format" in p:
        from matplotlib.patches import Patch
        seen = list(dict.fromkeys(p["content_format"]))
        ax.legend(handles=[Patch(color=d.format_colors.get(f, BLUE), label=f) for f in seen],
                  loc="lower right", frameon=False)
    ax.set_xlabel("Members (readers who added the title)")
    return finalize(fig, "The 15 most popular titles by members")


@chart("23_top_rated_titles")
def top_rated_titles(d):
    t = tables(d, "spark_top_rated_titles")
    if t is None:
        return None
    p = t[0].sort_values("weighted_score", ascending=False).head(15)
    fig, ax = plt.subplots(figsize=(10.5, 6.5))
    dotplot(ax, [short(x) for x in p["title"]], list(p["weighted_score"]), "{:.2f}")
    ax.set_xlabel("Weighted score")
    return finalize(fig, "Top-rated titles (at least 1,000 votes)",
                    "Weighted score = Bayesian average, so titles with few votes cannot reach the top.")


@chart("24_creators")
def creators(d):
    t = tables(d, "spark_creator_summary_by_weighted_score", "spark_creator_summary_by_output")
    if t is None:
        return None
    q = t[0].sort_values("mean_weighted_score", ascending=False).head(12)
    o = t[1].sort_values("title_count", ascending=False).head(12)
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    dotplot(axes[0], [f"{short(c, 24)} ({int(n)} rated)" for c, n in zip(q["creator"], q["rated_count"])],
            list(q["mean_weighted_score"]), "{:.2f}")
    axes[0].set_xlabel("Mean weighted score")
    axes[0].set_title("Highest quality (10+ rated titles)")
    barh(axes[1], [short(c, 28) for c in o["creator"]], list(o["title_count"]))
    axes[1].set_xlabel("Titles credited")
    axes[1].set_title("Most prolific")
    return finalize(fig, "Creators: quality vs output")


def chart_title(fig):
    sup = getattr(fig, "_suptitle", None)
    return sup.get_text() if sup is not None else (fig.axes[0].get_title() if fig.axes else "")


def build_all(d=None):
    VIZ_DIR.mkdir(parents=True, exist_ok=True)
    d = d or Data()
    print(f"Loaded {len(d.df):,} rows. Writing charts to {VIZ_DIR}")
    saved, skipped, failed = [], [], []
    for name, fn in CHARTS.items():
        try:
            fig = fn(d)
        except Exception as exc:
            print(f"[FAILED]  {name}: {exc}")
            failed.append(name)
            plt.close("all")
            continue
        if fig is None:
            print(f"[SKIPPED] {name}: required data not available")
            skipped.append(name)
            continue
        path = VIZ_DIR / f"{name}.png"
        title = chart_title(fig)
        fig.savefig(path, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        saved.append((name, title))
        print(f"[SAVED]   {path.name}")

    lines = ["# Chart gallery", "", f"{len(saved)} charts generated by `src/make_visualizations.py`.", ""]
    for name, title in saved:
        lines += [f"## {title}", f"![{name}]({name}.png)", ""]
    (VIZ_DIR / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Done: {len(saved)} saved, {len(skipped)} skipped, {len(failed)} failed.")
    return saved, skipped, failed


def main():
    plt.switch_backend("Agg")
    _, _, failed = build_all()
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()