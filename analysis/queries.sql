CREATE OR REPLACE TEMP VIEW titles_enriched AS
SELECT t.*,
       CASE WHEN score IS NOT NULL AND scored_by IS NOT NULL
            THEN (scored_by / (scored_by + 50.0)) * score
               + (50.0 / (scored_by + 50.0)) * (SELECT AVG(score) FROM titles)
       END AS weighted_score,
       CASE WHEN regexp_extract(CAST(start_date AS STRING), '^(\\d{4})', 1) <> ''
            THEN CAST(regexp_extract(CAST(start_date AS STRING), '^(\\d{4})', 1) AS INT)
       END AS pub_year,
       COALESCE(genres, '') RLIKE 'Hentai|Erotica' AS is_adult_genre,
       array_distinct(filter(
           transform(split(COALESCE(genres, ''), '\\|'), x -> trim(x)),
           x -> x <> '')) AS genre_list
FROM titles t;

SELECT COALESCE(content_format, 'Unknown')              AS content_format,
       COUNT(*)                                         AS title_count,
       COUNT(score)                                     AS rated_count,
       ROUND(COUNT(score) * 100.0 / COUNT(*), 1)        AS pct_rated,
       ROUND(AVG(score), 3)                             AS mean_score,
       ROUND(percentile_approx(score, 0.5), 2)          AS median_score,
       ROUND(AVG(weighted_score), 3)                    AS mean_weighted_score,
       ROUND(AVG(members), 1)                           AS mean_members,
       percentile_approx(members, 0.5)                  AS median_members
FROM titles_enriched
GROUP BY COALESCE(content_format, 'Unknown')
ORDER BY title_count DESC;

SELECT COALESCE(content_format, 'Unknown')              AS content_format,
       COUNT(*)                                         AS title_count,
       COUNT(score)                                     AS rated_count,
       ROUND(AVG(score), 3)                             AS mean_score,
       ROUND(percentile_approx(score, 0.5), 2)          AS median_score,
       percentile_approx(members, 0.5)                  AS median_members
FROM titles_enriched
WHERE NOT is_adult_genre
GROUP BY COALESCE(content_format, 'Unknown')
ORDER BY title_count DESC;

SELECT title, score, scored_by, ROUND(weighted_score, 3) AS weighted_score, members, favorites
FROM titles_enriched
WHERE members IS NOT NULL
ORDER BY members DESC
LIMIT 50;

SELECT title, score, scored_by, ROUND(weighted_score, 3) AS weighted_score, members
FROM titles_enriched
WHERE scored_by >= 1000
ORDER BY weighted_score DESC
LIMIT 50;

SELECT pub_year                                         AS year,
       COUNT(*)                                         AS title_count,
       COUNT(score)                                     AS rated_count,
       ROUND(AVG(score), 3)                             AS mean_score,
       ROUND(STDDEV(score), 3)                          AS sd_score,
       ROUND(AVG(weighted_score), 3)                    AS mean_weighted_score
FROM titles_enriched
WHERE pub_year BETWEEN 1900 AND YEAR(CURRENT_DATE())
GROUP BY pub_year
HAVING COUNT(score) >= 30
ORDER BY year;

SELECT COUNT(*)                                         AS title_count,
       COUNT(score)                                     AS rated_titles,
       ROUND(COUNT(score) * 100.0 / COUNT(*), 1)        AS pct_rated,
       ROUND(AVG(score), 3)                             AS mean_score,
       ROUND(percentile_approx(score, 0.5), 2)          AS median_score,
       ROUND(STDDEV(score), 3)                          AS sd_score,
       MIN(score)                                       AS minimum_score,
       MAX(score)                                       AS maximum_score
FROM titles_enriched;

SELECT genre,
       COUNT(*)                                         AS title_count,
       COUNT(score)                                     AS rated_count,
       ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM titles), 2) AS pct_of_all_titles,
       ROUND(AVG(score), 3)                             AS mean_score,
       ROUND(percentile_approx(score, 0.5), 2)          AS median_score,
       ROUND(AVG(weighted_score), 3)                    AS mean_weighted_score,
       ROUND(AVG(members), 1)                           AS mean_members,
       percentile_approx(members, 0.5)                  AS median_members,
       SUM(favorites)                                   AS total_favorites
FROM titles_enriched
LATERAL VIEW explode(genre_list) e AS genre
GROUP BY genre
HAVING COUNT(score) >= 30
ORDER BY title_count DESC;

SELECT ga                                               AS genre_a,
       gb                                               AS genre_b,
       COUNT(*)                                         AS pair_count,
       COUNT(score)                                     AS rated_count,
       ROUND(AVG(score), 3)                             AS mean_score,
       ROUND(AVG(weighted_score), 3)                    AS mean_weighted_score,
       percentile_approx(members, 0.5)                  AS median_members
FROM titles_enriched
LATERAL VIEW explode(genre_list) a AS ga
LATERAL VIEW explode(genre_list) b AS gb
WHERE ga < gb
GROUP BY ga, gb
HAVING COUNT(*) >= 30 AND COUNT(score) >= 30
ORDER BY pair_count DESC
LIMIT 100;

SELECT creator,
       COUNT(*)                                         AS title_count,
       COUNT(score)                                     AS rated_count,
       ROUND(AVG(score), 3)                             AS mean_score,
       ROUND(AVG(weighted_score), 3)                    AS mean_weighted_score,
       SUM(COALESCE(members, 0))                        AS total_members
FROM titles_enriched
LATERAL VIEW explode(array_distinct(filter(
    transform(split(COALESCE(authors, ''), '\\|'),
              x -> trim(regexp_replace(x, '\\s*\\([^)]*\\)', ''))),
    x -> x <> ''))) c AS creator
GROUP BY creator
HAVING COUNT(*) >= 2
ORDER BY title_count DESC
LIMIT 50;

SELECT creator,
       COUNT(*)                                         AS title_count,
       COUNT(score)                                     AS rated_count,
       ROUND(AVG(score), 3)                             AS mean_score,
       ROUND(AVG(weighted_score), 3)                    AS mean_weighted_score,
       SUM(COALESCE(members, 0))                        AS total_members
FROM titles_enriched
LATERAL VIEW explode(array_distinct(filter(
    transform(split(COALESCE(authors, ''), '\\|'),
              x -> trim(regexp_replace(x, '\\s*\\([^)]*\\)', ''))),
    x -> x <> ''))) c AS creator
GROUP BY creator
HAVING COUNT(score) >= 10
ORDER BY mean_weighted_score DESC
LIMIT 50;