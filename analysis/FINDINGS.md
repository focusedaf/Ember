# EMBER - Key Findings

_Auto-generated from `analysis/outputs/spark/*.csv`. Spark outputs are the canonical tables for charts._

## 1. Dataset and rating overview

| title_count | rated_titles | pct_rated | mean_score | median_score | sd_score | minimum_score | p25_score | p75_score | maximum_score | mean_weighted_score |
|---|---|---|---|---|---|---|---|---|---|---|
| 64,833 | 24,636 | 38 | 6.945 | 6.91 | 0.52 | 2.44 | 6.62 | 7.25 | 9.47 | 6.964 |

**Takeaway:** 64,833 titles, of which 38.0% have a score (mean 6.945, median 6.91, SD 0.52).

## 2. Content-format comparison

| content_format | title_count | pct_rated | mean_score | median_score | mean_weighted_score | median_members |
|---|---|---|---|---|---|---|
| Manga | 44,077 | 43.6 | 6.961 | 6.93 | 6.977 | 266 |
| Light Novel | 10,224 | 9.4 | 7.45 | 7.42 | 7.406 | 54 |
| One-shot | 5,248 | 40.5 | 6.514 | 6.55 | 6.593 | 171 |
| Manhwa | 2,986 | 51.6 | 7.058 | 7.01 | 7.065 | 425 |
| Doujinshi | 1,816 | 32.9 | 6.766 | 6.74 | 6.813 | 174 |
| Manhua | 350 | 46 | 7.081 | 7.05 | 7.091 | 314 |
| Novel | 132 | 35.6 | 7.834 | 7.79 | 7.76 | 239 |

**Takeaway:** 'Manga' is the largest format (44,077 titles). Among formats with 100+ rated titles, 'Light Novel' has the highest mean weighted score (7.406), but only 9.4% of its titles are rated, so treat it as a rated-subset result.

## 3. Genre summary (top 10 by volume)

| genre | title_count | pct_of_all_titles | mean_score | mean_weighted_score | median_members |
|---|---|---|---|---|---|
| Romance | 16,876 | 26.03 | 6.981 | 6.993 | 309 |
| Comedy | 14,099 | 21.75 | 6.977 | 6.992 | 327 |
| Hentai | 11,208 | 17.29 | 6.727 | 6.786 | 110 |
| Fantasy | 10,952 | 16.89 | 7.006 | 7.016 | 283 |
| Boys Love | 9,610 | 14.82 | 6.924 | 6.945 | 334 |
| Drama | 9,303 | 14.35 | 7.1 | 7.107 | 460 |
| Action | 8,910 | 13.74 | 7.028 | 7.038 | 354 |
| Erotica | 8,844 | 13.64 | 6.865 | 6.892 | 346 |
| Supernatural | 7,471 | 11.52 | 7.021 | 7.033 | 269 |
| Slice of Life | 5,155 | 7.95 | 7.083 | 7.088 | 270 |

**Takeaway:** Most common genre: Romance (26.03% of titles). Highest weighted score among reliable genres: Award Winning (7.792).

## 4. Genre combinations

**Most frequent pairs**

| genre_a | genre_b | pair_count | lift | mean_score | mean_weighted_score |
|---|---|---|---|---|---|
| Boys Love | Erotica | 7,613 | 5.591 | 6.901 | 6.924 |
| Comedy | Romance | 5,286 | 1.387 | 7.019 | 7.028 |
| Action | Fantasy | 3,778 | 2.417 | 7.019 | 7.027 |
| Drama | Romance | 3,388 | 1.347 | 7.082 | 7.089 |
| Adventure | Fantasy | 2,682 | 3.907 | 7.028 | 7.035 |
| Fantasy | Romance | 2,646 | 0.894 | 7.043 | 7.051 |
| Comedy | Fantasy | 2,440 | 0.986 | 6.994 | 7.005 |
| Action | Adventure | 2,208 | 3.954 | 7.071 | 7.077 |
| Comedy | Slice of Life | 2,163 | 1.858 | 7.084 | 7.088 |
| Comedy | Ecchi | 2,073 | 2.572 | 6.705 | 6.744 |

**Best-scoring pairs (reliable only)**

| genre_a | genre_b | pair_count | mean_weighted_score | mean_score |
|---|---|---|---|---|
| Adventure | Award Winning | 47 | 8.068 | 8.082 |
| Action | Award Winning | 72 | 7.954 | 7.974 |
| Award Winning | Fantasy | 37 | 7.871 | 7.9 |
| Award Winning | Drama | 181 | 7.85 | 7.875 |
| Award Winning | Sci-Fi | 44 | 7.839 | 7.863 |
| Award Winning | Supernatural | 50 | 7.797 | 7.821 |
| Award Winning | Comedy | 129 | 7.725 | 7.751 |
| Award Winning | Slice of Life | 80 | 7.724 | 7.755 |
| Award Winning | Romance | 117 | 7.699 | 7.723 |
| Drama | Sports | 192 | 7.411 | 7.425 |

**Strongest affinity (highest lift, reliable only)**

| genre_a | genre_b | pair_count | lift | mean_score |
|---|---|---|---|---|
| Horror | Suspense | 113 | 7.999 | 7.188 |
| Horror | Mystery | 461 | 6.939 | 7.094 |
| Mystery | Suspense | 133 | 6.553 | 7.309 |
| Gourmet | Slice of Life | 214 | 6.32 | 7.144 |
| Boys Love | Erotica | 7,613 | 5.591 | 6.901 |
| Action | Adventure | 2,208 | 3.954 | 7.071 |
| Adventure | Fantasy | 2,682 | 3.907 | 7.028 |
| Horror | Supernatural | 746 | 3.669 | 6.951 |
| Action | Sci-Fi | 1,537 | 3.333 | 7.011 |
| Mystery | Supernatural | 837 | 2.865 | 7.189 |

**Takeaway:** The most frequent pairing is Boys Love + Erotica (7,613 titles, lift 5.591). Best-scoring reliable pair: Adventure + Award Winning (8.068). Strongest affinity: Horror + Suspense (lift 7.999; >1 means they co-occur more than chance).

## 5. Publication trend by decade

| decade | title_count | rated_count | mean_score | mean_weighted_score |
|---|---|---|---|---|
| 1920 | 1 | 0 | - | - |
| 1930 | 4 | 0 | - | - |
| 1940 | 16 | 7 | 6.541 | 6.591 |
| 1950 | 57 | 18 | 6.994 | 6.979 |
| 1960 | 170 | 62 | 7.066 | 7.063 |
| 1970 | 469 | 171 | 7.098 | 7.093 |
| 1980 | 1,135 | 347 | 6.998 | 7.013 |
| 1990 | 3,721 | 1,331 | 6.994 | 7.015 |
| 2000 | 16,961 | 7,801 | 6.974 | 6.992 |
| 2010 | 33,129 | 11,662 | 6.934 | 6.954 |
| 2020 | 7,287 | 2,366 | 6.947 | 6.959 |

**Takeaway:** Recent decades may be incomplete or less rated because of the snapshot date.

## 6. Creators (10+ rated titles, ranked by weighted score)

| creator | title_count | rated_count | mean_score | mean_weighted_score | total_members |
|---|---|---|---|---|---|
| Tomohi | 13 | 11 | 7.937 | 7.838 | 20,736 |
| Kinoko Nasu | 14 | 12 | 7.805 | 7.753 | 98,203 |
| Natsume Akatsuki | 11 | 10 | 7.739 | 7.717 | 117,775 |
| ZUN | 13 | 13 | 7.749 | 7.712 | 50,260 |
| Makoto Shinkai | 18 | 12 | 7.672 | 7.643 | 188,550 |
| Mei Sakuraga | 20 | 19 | 7.624 | 7.609 | 89,498 |
| Kou Yoneda | 10 | 10 | 7.604 | 7.585 | 87,849 |
| Kiyotaka Haimura | 22 | 14 | 7.601 | 7.569 | 69,179 |
| Takaya Kagami | 19 | 12 | 7.612 | 7.563 | 147,918 |
| Kazuya Minekura | 21 | 13 | 7.588 | 7.556 | 61,850 |

**Takeaway:** Top creator by weighted score: Tomohi.

## 7. Correlations (Spearman, pairwise)

| feature_a | feature_b | n_pairs | spearman |
|---|---|---|---|
| scored_by | members | 64,833 | 0.96 |
| chapters | volumes | 38,884 | 0.834 |
| members | favorites | 64,833 | 0.769 |
| scored_by | favorites | 64,833 | 0.734 |
| score | favorites | 24,636 | 0.641 |
| score | members | 24,636 | 0.513 |
| score | scored_by | 24,636 | 0.44 |
| score | chapters | 19,939 | 0.364 |
| score | volumes | 18,322 | 0.352 |
| favorites | volumes | 48,211 | 0.34 |
| favorites | chapters | 46,042 | 0.31 |
| members | n_genres | 64,833 | 0.309 |

**Takeaway:** Feature most associated with score: favorites (Spearman 0.641). Correlation is not causation.

## 8. Distributed-style processing demo

```text
DISTRIBUTED-STYLE PROCESSING DEMO (genre-pair job)
========================================================
Spark master                  : local[*]
Default parallelism           : 12
Input DataFrame partitions    : 8
spark.sql.shuffle.partitions  : 4

Rows per input partition:
 partition  count
         0   8104
         1   8104
         2   8105
         3   8104
         4   8104
         5   8104
         6   8104
         7   8104

Physical plan (look for 'Exchange hashpartitioning' = the shuffle):
== Physical Plan ==
AdaptiveSparkPlan isFinalPlan=false
+- HashAggregate(keys=[genre_a#38644, genre_b#38646], functions=[count(1), avg(score#63)])
   +- Exchange hashpartitioning(genre_a#38644, genre_b#38646, 4), ENSURE_REQUIREMENTS, [plan_id=3558]
      +- HashAggregate(keys=[genre_a#38644, genre_b#38646], functions=[partial_count(1), partial_avg(score#63)])
         +- Filter (genre_a#38644 < genre_b#38646)
            +- Generate explode(genre_list#1887), [score#63, genre_a#38644], false, [genre_b#38646]
               +- Generate explode(genre_list#1887), [score#63, genre_list#1887], false, [genre_a#38644]
                  +- Filter (size(genre_list#1887, false) > 0)
                     +- InMemoryTableScan [score#63, genre_list#1887], [(size(genre_list#1887, false) > 0)]
   ... (cached input scan omitted)
Timing (same aggregation, warm Spark run):
  Spark  :     0.19 s  (199 distinct pairs)
  Pandas :     0.21 s  (199 distinct pairs)
  Note: on one laptop Spark can be slower than pandas; the point is the
  explode -> shuffle -> aggregate pattern, which scales by adding executors.
```

**Takeaway:** The genre-pair job explodes each title into pairs, shuffles by (genre_a, genre_b) and aggregates; the Exchange in the plan is the shuffle.

## Caveats

- members/favorites are engagement proxies, not sales.
- Genre rows overlap (a title has several genres).
- Groups with fewer than 30 rated titles are flagged unreliable.
- Findings describe this catalogue snapshot only.
