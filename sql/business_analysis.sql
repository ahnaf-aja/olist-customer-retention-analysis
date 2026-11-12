-- =====================================================================
-- Olist Customers — Business Analysis SQL
-- Dialek: ANSI SQL (diuji di SQLite, kompatibel PostgreSQL/MySQL 8+)
-- Tabel sumber: customers (= data/raw/olist_customers_dataset.csv)
--   customer_id, customer_unique_id, customer_zip_code_prefix,
--   customer_city, customer_state
-- ASUMSI: 1 customer_id = 1 pesanan (proksi jumlah pesanan).
-- =====================================================================

-- Q1. Data quality: baris, unik, missing
SELECT COUNT(*)                                   AS total_records,
       COUNT(DISTINCT customer_id)                AS distinct_customer_id,
       COUNT(DISTINCT customer_unique_id)         AS unique_customers,
       SUM(CASE WHEN customer_id IS NULL OR customer_unique_id IS NULL
                  OR customer_zip_code_prefix IS NULL OR customer_city IS NULL
                  OR customer_state IS NULL THEN 1 ELSE 0 END) AS rows_with_missing,
       SUM(CASE WHEN LENGTH(customer_zip_code_prefix) <> 5 THEN 1 ELSE 0 END) AS invalid_zip
FROM customers;

-- Q2. KPI utama: repeat customer rate & rata-rata record per pelanggan
WITH per_customer AS (
    SELECT customer_unique_id, COUNT(*) AS records
    FROM customers
    GROUP BY customer_unique_id
)
SELECT COUNT(*)                                               AS unique_customers,
       SUM(records)                                           AS total_records,
       SUM(CASE WHEN records > 1 THEN 1 ELSE 0 END)           AS repeat_customers,
       ROUND(100.0 * SUM(CASE WHEN records > 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS repeat_rate_pct,
       ROUND(1.0 * SUM(records) / COUNT(*), 4)                AS avg_records_per_customer,
       MAX(records)                                           AS max_records
FROM per_customer;

-- Q3. Segmentasi frekuensi
WITH per_customer AS (
    SELECT customer_unique_id, COUNT(*) AS records
    FROM customers GROUP BY customer_unique_id
)
SELECT CASE WHEN records = 1 THEN '1. One-time'
            WHEN records = 2 THEN '2. Repeat (2x)'
            ELSE '3. Loyal (3x+)' END                     AS segment,
       COUNT(*)                                            AS customers,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)  AS share_pct
FROM per_customer
GROUP BY 1
ORDER BY 1;

-- Q4. Distribusi & kontribusi per state (record level) + kumulatif
SELECT customer_state,
       COUNT(*)                                                     AS records,
       COUNT(DISTINCT customer_unique_id)                           AS unique_customers,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)           AS share_pct,
       ROUND(100.0 * SUM(COUNT(*)) OVER (ORDER BY COUNT(*) DESC
             ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
             / SUM(COUNT(*)) OVER (), 2)                            AS cumulative_share_pct,
       RANK() OVER (ORDER BY COUNT(*) DESC)                         AS rank_state
FROM customers
GROUP BY customer_state
ORDER BY records DESC;

-- Q5. Repeat rate per state (lokasi utama = lokasi dengan record terbanyak per pelanggan)
WITH loc AS (
    SELECT customer_unique_id, customer_state, COUNT(*) AS n,
           ROW_NUMBER() OVER (PARTITION BY customer_unique_id ORDER BY COUNT(*) DESC, customer_state) AS rn
    FROM customers GROUP BY customer_unique_id, customer_state
),
per_customer AS (
    SELECT c.customer_unique_id, l.customer_state AS primary_state, COUNT(*) AS records
    FROM customers c
    JOIN loc l ON l.customer_unique_id = c.customer_unique_id AND l.rn = 1
    GROUP BY c.customer_unique_id, l.customer_state
)
SELECT primary_state,
       COUNT(*)                                                    AS unique_customers,
       SUM(CASE WHEN records > 1 THEN 1 ELSE 0 END)                AS repeat_customers,
       ROUND(100.0 * SUM(CASE WHEN records > 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS repeat_rate_pct
FROM per_customer
GROUP BY primary_state
HAVING COUNT(*) >= 300          -- hindari kesimpulan dari sampel kecil
ORDER BY repeat_rate_pct DESC;

-- Q6. Top 15 kota (kota + state sebagai kunci, karena ada nama kota homonim)
SELECT customer_city, customer_state,
       COUNT(DISTINCT customer_unique_id)                                     AS unique_customers,
       ROUND(100.0 * COUNT(DISTINCT customer_unique_id)
             / (SELECT COUNT(DISTINCT customer_unique_id) FROM customers), 2) AS share_pct
FROM customers
GROUP BY customer_city, customer_state
ORDER BY unique_customers DESC
LIMIT 15;

-- Q7. Konsentrasi kota (Pareto): berapa kota untuk 80% record
WITH city AS (
    SELECT customer_city, customer_state, COUNT(*) AS records
    FROM customers GROUP BY customer_city, customer_state
),
cum AS (
    SELECT records,
           SUM(records) OVER (ORDER BY records DESC, customer_city, customer_state
                              ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) * 1.0
           / SUM(records) OVER () AS cum_share,
           COUNT(*) OVER () AS total_cities
    FROM city
)
SELECT MIN(total_cities)                                     AS total_cities,
       SUM(CASE WHEN cum_share < 0.8 THEN 1 ELSE 0 END) + 1  AS cities_for_80pct,
       SUM(CASE WHEN records = 1 THEN 1 ELSE 0 END)          AS cities_with_1_record
FROM cum;

-- Q8. Nama kota yang muncul di lebih dari satu state (risiko salah agregasi)
SELECT customer_city, COUNT(DISTINCT customer_state) AS n_states
FROM customers
GROUP BY customer_city
HAVING COUNT(DISTINCT customer_state) > 1
ORDER BY n_states DESC, customer_city
LIMIT 20;

-- Q9. Pelanggan dengan frekuensi tinggi (outlier >= 5 record) untuk ditinjau tim CRM
SELECT customer_unique_id, COUNT(*) AS records,
       COUNT(DISTINCT customer_zip_code_prefix) AS distinct_zips,
       COUNT(DISTINCT customer_state)           AS distinct_states
FROM customers
GROUP BY customer_unique_id
HAVING COUNT(*) >= 5
ORDER BY records DESC;
