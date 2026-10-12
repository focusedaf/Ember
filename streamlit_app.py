from pathlib import Path

import pandas as pd
import streamlit as st

HERE = Path(__file__).resolve().parent
ROOT = next((p for p in (HERE, HERE.parent) if (p / "visualizations").exists()), HERE)
SPARK_DIR = ROOT / "analysis" / "outputs" / "spark"
VIZ_DIR = ROOT / "visualizations"
REPO_URL = "https://github.com/focusedaf/Ember"

st.set_page_config(page_title="EMBER - Decay Analytics", layout="wide")


@st.cache_data
def load(name):
    path = SPARK_DIR / f"{name}.csv"
    return pd.read_csv(path) if path.exists() else None


def show_chart(name, caption=None):
    path = VIZ_DIR / f"{name}.png"
    if path.exists():
        st.image(str(path), caption=caption)
    else:
        st.info(f"Chart {name}.png not found. Run the chart script and push the visualizations folder.")


def need(df, label):
    if df is None or df.empty:
        st.warning(f"{label} data not found in analysis/outputs/spark/.")
        return False
    return True


def keep(df, cols):
    return df[[c for c in cols if c in df.columns]]


def only_reliable(df):
    if "reliable" in df.columns:
        return df[df["reliable"].astype(str).str.lower() == "true"]
    return df


st.title("EMBER - Decay Analytics")
st.caption("Explore the catalogue analysis: formats, genres, genre combinations, trends and popularity. "
           "All numbers come from the Spark analytics outputs.")

tabs = st.tabs(["Overview", "Formats", "Genres", "Genre pairs", "Trends",
                "Popularity and creators", "Chart gallery"])

with tabs[0]:
    rating = load("spark_rating_summary")
    if need(rating, "Rating summary"):
        r = rating.iloc[0]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Titles", f"{int(r['title_count']):,}")
        c2.metric("Rated titles", f"{int(r['rated_titles']):,}", f"{r['pct_rated']:.1f}% of catalogue", delta_color="off")
        c3.metric("Mean score", f"{r['mean_score']:.2f}")
        c4.metric("Median score", f"{r['median_score']:.2f}")
    st.subheader("Key insights")
    st.markdown(
        "- **Ratings cover a minority.** About 38% of titles have a score, tightly clustered around 6.9.\n"
        "- **Formats differ in coverage as much as in score.** Manga is 68% of the catalogue. "
        "Light Novels score highest (7.45) but only 9.4% of them are rated.\n"
        "- **Adult-tagged genres are about 30% of titles** but get much less engagement.\n"
        "- **Genre pairs reveal structure.** Boys Love + Erotica is the most frequent pair; "
        "Horror + Suspense has the strongest affinity (lift 8.0).\n"
        "- **Score tracks reach only moderately** (Spearman 0.64 with favorites, 0.51 with members) "
        "and not at all with publication year."
    )
    left, right = st.columns(2)
    with left:
        show_chart("02_rating_distribution")
    with right:
        show_chart("01_missing_values")

with tabs[1]:
    excl = st.checkbox("Exclude adult-tagged titles", value=False)
    fmt = load("spark_format_summary_excl_adult" if excl else "spark_format_summary")
    if need(fmt, "Format summary"):
        st.dataframe(keep(fmt, ["content_format", "title_count", "rated_count", "pct_rated", "mean_score",
                                "median_score", "mean_weighted_score", "median_members"]))
        options = [m for m in ["mean_weighted_score", "median_members", "title_count", "pct_rated"] if m in fmt.columns]
        metric = st.selectbox("Chart metric", options)
        st.bar_chart(fmt.set_index("content_format")[metric])
        st.caption("Formats with a low rated share (for example Light Novel) are scored by a small subset of their titles.")
    show_chart("17_format_comparison")
    show_chart("03_format_composition")

with tabs[2]:
    g = load("spark_genre_summary")
    if need(g, "Genre summary"):
        sort_options = [m for m in ["title_count", "mean_weighted_score", "median_members", "mean_score"] if m in g.columns]
        sort_by = st.selectbox("Sort genres by", sort_options)
        reliable = st.checkbox("Reliable genres only (30+ rated titles)", value=True)
        view = only_reliable(g) if reliable else g
        view = view.sort_values(sort_by, ascending=False)
        st.dataframe(keep(view, ["genre", "title_count", "pct_of_all_titles", "rated_count", "mean_score",
                                 "mean_weighted_score", "median_members"]))
        st.bar_chart(view.head(15).set_index("genre")[sort_by])

        st.subheader("Genre explorer")
        genres = list(g.sort_values("title_count", ascending=False)["genre"])
        choice = st.selectbox("Pick a genre", genres)
        row = g[g["genre"] == choice].iloc[0]
        m1, m2, m3 = st.columns(3)
        m1.metric("Titles", f"{int(row['title_count']):,}")
        m2.metric("Mean weighted score", f"{row['mean_weighted_score']:.3f}")
        m3.metric("Median members", f"{int(row['median_members']):,}")

        pairs = load("spark_genre_pairs")
        if pairs is not None and not pairs.empty:
            mine = pairs[(pairs["genre_a"] == choice) | (pairs["genre_b"] == choice)].copy()
            mine["partner"] = mine["genre_b"].where(mine["genre_a"] == choice, mine["genre_a"])
            rank_by = st.radio("Rank partner genres by", ["pair_count", "lift", "mean_weighted_score"], horizontal=True)
            st.dataframe(keep(mine.sort_values(rank_by, ascending=False),
                              ["partner", "pair_count", "lift", "mean_score", "mean_weighted_score", "median_members"]))
    show_chart("12_genre_distribution")
    show_chart("13_genre_quality")
    show_chart("14_genre_popularity")

    themes = load("spark_theme_summary")
    demos = load("spark_demographic_summary")
    left, right = st.columns(2)
    with left:
        if themes is not None:
            st.subheader("Themes")
            st.dataframe(keep(themes.sort_values("title_count", ascending=False),
                              ["theme", "title_count", "mean_weighted_score", "median_members"]))
    with right:
        if demos is not None:
            st.subheader("Demographics")
            st.dataframe(keep(demos.sort_values("title_count", ascending=False),
                              ["demographic", "title_count", "mean_weighted_score", "median_members"]))

with tabs[3]:
    pairs = load("spark_genre_pairs")
    if need(pairs, "Genre pair"):
        c1, c2, c3 = st.columns(3)
        all_genres = sorted(set(pairs["genre_a"]) | set(pairs["genre_b"]))
        focus = c1.selectbox("Show pairs containing", ["All genres"] + all_genres)
        min_count = c2.slider("Minimum shared titles", int(pairs["pair_count"].min()), int(pairs["pair_count"].max()),
                              int(pairs["pair_count"].min()))
        sort_by = c3.selectbox("Sort by", ["pair_count", "lift", "mean_weighted_score", "mean_score"])
        view = only_reliable(pairs) if st.checkbox("Reliable pairs only (30+ rated titles)", value=True) else pairs
        view = view[view["pair_count"] >= min_count]
        if focus != "All genres":
            view = view[(view["genre_a"] == focus) | (view["genre_b"] == focus)]
        st.dataframe(keep(view.sort_values(sort_by, ascending=False),
                          ["genre_a", "genre_b", "pair_count", "lift", "pct_of_a", "pct_of_b", "rated_count",
                           "mean_score", "mean_weighted_score", "median_members"]))
        st.caption("Lift above 1 means two genres appear together more often than chance would predict.")
    show_chart("19_genre_pair_lift_heatmap")
    show_chart("20_top_genre_pairs")
    show_chart("21_best_scoring_pairs")

with tabs[4]:
    year = load("spark_publication_year_reliable")
    if need(year, "Publication year"):
        st.subheader("Average score by publication year (years with 30+ rated titles)")
        st.line_chart(year.set_index("year")[["mean_score", "mean_weighted_score"]])
    all_years = load("spark_publication_year")
    if all_years is not None and not all_years.empty:
        st.subheader("Titles started per year")
        st.bar_chart(all_years.set_index("year")["title_count"])
    decade = load("spark_publication_decade")
    if decade is not None and not decade.empty:
        st.subheader("By decade")
        st.dataframe(keep(decade, ["decade", "title_count", "rated_count", "mean_score", "mean_weighted_score"]))
        st.caption("The latest decade is incomplete.")
    show_chart("09_titles_per_year_by_format")
    show_chart("10_score_trend_by_year")

with tabs[5]:
    pop = load("spark_popularity_summary")
    if need(pop, "Popularity"):
        st.subheader("Most popular titles (by members)")
        st.dataframe(keep(pop, ["title", "content_format", "members", "favorites", "score", "weighted_score"]))
    top = load("spark_top_rated_titles")
    if top is not None and not top.empty:
        st.subheader("Top-rated titles (1,000+ votes)")
        st.dataframe(keep(top, ["title", "content_format", "weighted_score", "score", "scored_by", "members"]))
    which = st.radio("Creators ranked by", ["Weighted score (10+ rated titles)", "Output (titles credited)"], horizontal=True)
    creators = load("spark_creator_summary_by_weighted_score" if which.startswith("Weighted")
                    else "spark_creator_summary_by_output")
    if creators is not None and not creators.empty:
        st.dataframe(keep(creators, ["creator", "title_count", "rated_count", "mean_score",
                                     "mean_weighted_score", "total_members"]))
    corr = load("spark_numeric_correlations")
    if corr is not None and not corr.empty:
        st.subheader("Rank correlations")
        corr = corr.dropna(subset=["spearman"])
        corr = corr[(corr["feature_a"] != "weighted_score") & (corr["feature_b"] != "weighted_score")]
        features = sorted(set(corr["feature_a"]) | set(corr["feature_b"]))
        involve = st.selectbox("Show correlations involving", ["All"] + features)
        if involve != "All":
            corr = corr[(corr["feature_a"] == involve) | (corr["feature_b"] == involve)]
        corr = corr.reindex(corr["spearman"].abs().sort_values(ascending=False).index)
        st.dataframe(corr)
        st.caption("Correlation does not establish causation.")
    show_chart("11_correlation_heatmap")
    show_chart("07_score_vs_popularity")
    show_chart("22_top_popular_titles")
    show_chart("23_top_rated_titles")
    show_chart("24_creators")

with tabs[6]:
    files = sorted(VIZ_DIR.glob("*.png")) if VIZ_DIR.exists() else []
    if not files:
        st.info("No charts found in the visualizations folder.")
    cols = st.columns(2)
    for i, path in enumerate(files):
        with cols[i % 2]:
            st.image(str(path), caption=path.stem.replace("_", " "))

st.divider()
st.caption(f"Members and favorites are engagement proxies, not sales. Groups with fewer than 30 rated titles are flagged unreliable. "
           f"Findings describe this catalogue snapshot only. Source code: {REPO_URL}")