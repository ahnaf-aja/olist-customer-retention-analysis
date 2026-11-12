# Panduan Power BI — Olist Customer Geography & Loyalty Dashboard

> File `.pbix` dibuat manual di Power BI Desktop dengan mengikuti panduan ini. Semua tabel, kolom, dan measure
> di bawah sudah disesuaikan dengan file di `data/processed/` dan [`measures.dax`](measures.dax).

---

## A. Data Model (Star Schema)

```
        DimCustomer (96.096 baris)                 DimGeography (4.304 baris)
        PK: customer_unique_id                     PK: city_state_key
        records, segment, is_repeat_customer,      customer_city, city_display,
        moved_location, primary_state, ...         customer_state, state_name, region
                    │ 1                                        │ 1
                    │                                          │
                    ▼ *                                        ▼ *
              ┌──────────────────────────────────────────────────────┐
              │ FactCustomerRecord (99.441 baris)                    │
              │ PK: customer_id                                      │
              │ FK: customer_unique_id, city_state_key               │
              │ customer_zip_code_prefix, records_per_customer, ...  │
              └──────────────────────────────────────────────────────┘
```

| Relasi | Kardinalitas | Cross-filter | Alasan |
|---|---|---|---|
| `DimCustomer[customer_unique_id]` → `FactCustomerRecord[customer_unique_id]` | 1 : * | Single | Satu orang bisa punya banyak record. Atribut loyalitas (segment, repeat) ada di level orang. |
| `DimGeography[city_state_key]` → `FactCustomerRecord[city_state_key]` | 1 : * | Single | Kunci gabungan kota + state wajib dipakai karena ada 163 nama kota yang sama di state berbeda. |

**Alasan memilih desain ini:**
- **Grain fact = 1 `customer_id`.** Ini level paling detail di data. Jika nanti `olist_orders_dataset` ditambahkan, tabel ini bisa langsung di-join lewat `customer_id`.
- **Geografi menjadi satu dimensi.** Kota, state, dan region digabung dalam satu tabel datar (bukan snowflake), sehingga hierarki drill-down Region → State → City cukup diambil dari satu tabel.
- **Filter satu arah.** Relasi dibuat single direction untuk menghindari ambiguitas. Measure loyalitas memakai `CALCULATE` dengan filter dari `DimCustomer`.
- **Tidak ada Date Table**, karena dataset tidak punya kolom tanggal. Begitu data orders tersedia, tambahkan `DimDate` (lihat bagian F).

---

## B. Power Query — langkah demi langkah

### B.1 Parameter folder
*Home → Manage Parameters → New*: `ProjectPath` (Text) = `D:\porto analyst\business-analyst-project\data\processed\`

### B.2 FactCustomerRecord
*Get Data → Text/CSV → customers_clean.csv → Transform Data*, lalu ganti isi Advanced Editor dengan kode berikut:

```m
let
    Source   = Csv.Document(File.Contents(ProjectPath & "customers_clean.csv"),
                 [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Headers  = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    // 1. Tipe data: kode pos HARUS Text agar leading zero (mis. 01151) tidak hilang
    Typed    = Table.TransformColumnTypes(Headers, {
                 {"customer_id", type text}, {"customer_unique_id", type text},
                 {"customer_zip_code_prefix", type text}, {"city_state_key", type text},
                 {"records_per_customer", Int64.Type},
                 {"is_repeat_customer", type logical}, {"is_high_frequency", type logical}}),
    // 2. Buang kolom yang sudah ada di DimGeography (hindari redundansi di fact)
    Removed  = Table.RemoveColumns(Typed, {"customer_city", "city_display", "customer_state",
                                           "state_name", "region"}),
    // 3. Guard: hapus baris tanpa key (seharusnya 0)
    NoNull   = Table.SelectRows(Removed, each [customer_id] <> null and [customer_id] <> "")
in
    NoNull
```

### B.3 DimCustomer
```m
let
    Source  = Csv.Document(File.Contents(ProjectPath & "dim_customer.csv"),
                [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    Typed   = Table.TransformColumnTypes(Headers, {
                {"records", Int64.Type}, {"distinct_states", Int64.Type},
                {"distinct_cities", Int64.Type}, {"distinct_zips", Int64.Type},
                {"is_repeat_customer", type logical}, {"moved_location", type logical}}),
    // Kolom baru: label Ya/Tidak untuk slicer yang lebih ramah pengguna
    RepeatLbl = Table.AddColumn(Typed, "Repeat Status",
                each if [is_repeat_customer] then "Repeat" else "One-time", type text)
in
    RepeatLbl
```

### B.4 DimGeography (merge dim_city + dim_state)
1. Load `dim_state.csv` sebagai query **DimState**, lalu klik kanan → *Enable load* **dimatikan** (query ini hanya untuk staging).
2. Buat query **DimGeography**:

```m
let
    Source  = Csv.Document(File.Contents(ProjectPath & "dim_city.csv"),
                [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    // Merge (Left Outer) ke DimState untuk mengambil nama state & region
    Merged  = Table.NestedJoin(Headers, {"customer_state"}, DimState, {"customer_state"},
                "st", JoinKind.LeftOuter),
    Expanded = Table.ExpandTableColumn(Merged, "st", {"state_name", "region"}),
    // Urutan region untuk sorting visual (Sudeste dulu)
    RegionOrder = Table.AddColumn(Expanded, "region_order", each
                  List.PositionOf({"Sudeste","Sul","Centro-Oeste","Nordeste","Norte"}, [region]) + 1,
                  Int64.Type),
    // Kolom lokasi untuk Map visual (lebih akurat dari nama kota saja)
    MapLoc  = Table.AddColumn(RegionOrder, "map_location",
                each [city_display] & ", " & [customer_state] & ", Brazil", type text)
in
    MapLoc
```

3. Di Model view, atur:
   - `region` → *Sort by column* = `region_order`.
   - Buat hierarki **Geo**: `region` → `customer_state` → `city_display`.
   - `customer_state` → *Data category* = **State or Province**.
   - `map_location` → *Data category* = **Place**.

### B.5 Tabel measure
*Enter Data* → tabel kosong bernama `_Measures`. Lalu salin semua measure dari [`measures.dax`](measures.dax) satu per satu (*New measure*).

### B.6 Validasi setelah Load
| Cek | Nilai yang diharapkan |
|---|---|
| `[Total Records]` | 99.441 |
| `[Unique Customers]` | 96.096 |
| `[Repeat Customer Rate]` | 3,12% |
| `[Cities Covered]` | 4.304 |
| `[Top 5 State Share %]` | ~77% |

Jika angka berbeda, periksa tipe data dan relasi antartabel terlebih dahulu.

---

## C. Penjelasan DAX Measure utama

| Measure | Fungsi | Interpretasi |
|---|---|---|
| `Total Records` | `COUNTROWS` fact | Proksi jumlah pesanan |
| `Unique Customers` | `DISTINCTCOUNT` id orang | Ukuran basis pelanggan; bersifat non-additive antar-state (39 pelanggan pindah state) |
| `Repeat Customer Rate` | `CALCULATE` dengan filter `DimCustomer[is_repeat_customer]` | Persentase pelanggan yang membeli lebih dari sekali. Ini indikator utama loyalitas. |
| `Repeat Rate vs National (pp)` | Memakai `ALL(DimGeography)` sebagai baseline | Selisih wilayah terpilih dari rata-rata nasional |
| `Repeat Rate Flag` | `SWITCH` dengan ambang sampel minimal 300 | Mencegah kesimpulan dari state kecil seperti AC (n=77) |
| `Top 5 State Share %` | `TOPN` + `CALCULATE` | Tingkat ketergantungan pada 5 pasar terbesar |
| `Cumulative City Share %` | `ADDCOLUMNS` + `SUMX` + `FILTER` | Kurva Pareto konsentrasi kota |
| `Customers per City` | `DIVIDE` | Kepadatan pelanggan per kota (rendah = tersebar/long tail) |

---

## D. Rancangan Dashboard (3 halaman + 1 drill-through)

Kanvas 1280 × 720. Grid 8 px. Latar halaman `#F5F5F3`, kartu putih. Import tema [`olist_theme.json`](olist_theme.json) melalui *View → Themes → Browse*.
**Aturan warna:** biru `#2a78d6` untuk metrik utama, oranye `#eb6834` **hanya** untuk sorotan atau garis rata-rata, abu-abu `#b5b4ae` untuk konteks. Tidak ada warna pelangi.

### PAGE 1 — Executive Overview
Tujuan: dalam 10 detik, manajemen paham **seberapa besar basis pelanggan, seberapa loyal, dan seberapa terkonsentrasi**.

| Posisi | Visual | Field / Measure | Tujuan |
|---|---|---|---|
| Atas (y=16) – 5 kartu sejajar | Card (new) | `Unique Customers`, `Total Records`, `Repeat Customer Rate`, `Cities Covered`, `Top 5 State Share %` | KPI utama |
| Tengah-kiri (60% lebar) | Clustered bar (horizontal) | Axis `customer_state`, Value `Unique Customers`, Top N = 10 | Pasar terbesar |
| Tengah-kanan | Donut **atau** 100% bar | Legend `segment`, Value `Unique Customers` | Proporsi one-time vs repeat |
| Bawah-kiri | Bar | Axis `region`, Value `Customer Share %` | Ketimpangan antarregion |
| Bawah-kanan | Text box / Smart narrative | 3 insight utama (dari laporan) | Ringkasan untuk eksekutif |
| Kanan atas | Slicer (dropdown) | `region` | Filter global |

### PAGE 2 — Geographic Performance
Tujuan: menentukan wilayah inti yang harus dijaga dan wilayah yang bisa menjadi target ekspansi.

| Posisi | Visual | Field / Measure | Tujuan |
|---|---|---|---|
| Kiri (50%) | Filled map / Azure map | Location `customer_state`, Color saturation `Unique Customers` (gradien biru) | Peta sebaran |
| Kanan-atas | Line chart (satu sumbu, tanpa combo dual-axis) | X `city_display` (urut desc), Y `Cumulative City Share %` | Pareto: 1% kota = 50% pelanggan |
| Kanan-bawah | Matrix | Rows hierarki Geo; Values `Unique Customers`, `Customer Share %`, `Cities Covered`, `Customers per City`, `Repeat Customer Rate` | Drill Region → State → City |
| Atas | Slicer | `region`, `customer_state` | Interaksi |
| Tooltip page | Custom tooltip | `Unique Customers`, `Repeat Customer Rate`, `State Rank` | Detail saat hover |

### PAGE 3 — Customer Loyalty & Segmentation
Tujuan: mengetahui di mana pelanggan repeat berada dan seberapa besar perbedaannya.

| Posisi | Visual | Field / Measure | Tujuan |
|---|---|---|---|
| Atas – 4 kartu | Card | `Repeat Customers`, `Repeat Customer Rate` (subtitle `KPI Subtitle Repeat`), `Loyal Customers (3x+)`, `Avg Records per Customer` | KPI loyalitas |
| Tengah-kiri | Bar (horizontal) + reference line | Axis `customer_state`; Value `Repeat Customer Rate`; constant line = `Repeat Rate National` (oranye, putus-putus); Conditional color by `Repeat Rate Flag` | Peringkat loyalitas per state |
| Tengah-kanan | Matrix heatmap | Rows `region`; Columns `city_tier` *(kolom kalkulasi di DimCustomer; lihat catatan)*; Values `Repeat Customer Rate` dengan background gradient biru | Pola region × ukuran kota |
| Bawah | Column chart | Axis `DimCustomer[records]`; Value `Unique Customers`; skala log | Distribusi frekuensi pembelian |
| Slicer | Dropdown | `segment`, `Repeat Status`, `region` | Interaksi |

> Catatan `city_tier`: tambahkan calculated column di DimCustomer.
> ```DAX
> City Size = CALCULATE ( COUNTROWS ( DimCustomer ), ALLEXCEPT ( DimCustomer, DimCustomer[primary_city_state_key] ) )
> city_tier = SWITCH ( TRUE (), [City Size] <= 10, "1. Kecil (1-10)", [City Size] <= 100, "2. Menengah (11-100)",
>                     [City Size] <= 1000, "3. Besar (101-1.000)", "4. Metro (>1.000)" )
> ```

### PAGE 4 — City Detail (Drill-through, hidden)
- Drill-through field: `DimGeography[city_state_key]`.
- Visual: kartu KPI kota, tabel detail (`customer_unique_id`, `records`, `segment`, `customer_zip_code_prefix`), dan bar per `customer_zip_code_prefix`.
- Cara pakai: klik kanan sebuah kota di Page 2 atau Page 3 → *Drill through → City Detail*.

### UI/UX checklist
- Ikuti hierarki F-pattern: KPI di atas, visual tren/komposisi di tengah, detail di bawah.
- Maksimal 6–7 visual per halaman. Judul visual berupa **kalimat insight**, misalnya "3 state menguasai 67% pelanggan", bukan sekadar "Customers by State".
- Format angka memakai pemisah ribuan. Persentase memakai 2 desimal karena repeat rate kecil sehingga selisihnya penting.
- Hindari sumbu ganda dan pie chart dengan lebih dari 3 irisan.
- Aktifkan *Edit interactions* agar slicer region tidak memfilter kartu "Repeat Rate National".

---

## E. Yang tidak bisa dibuat dari dataset ini
Revenue, Profit, AOV, Revenue Growth, Conversion Rate, Churn berbasis waktu, dan Time Intelligence (YoY/MoM). Semua ini membutuhkan tabel orders, payments, dan items.

## F. Ekstensi bila data orders tersedia
1. Tambahkan `FactOrders` (grain `order_id`) dengan relasi `customer_id` → `FactCustomerRecord[customer_id]` (1:1), atau lebih baik jadikan `FactOrders` sebagai fact utama.
2. Buat `DimDate = CALENDAR(MIN(order_purchase_timestamp), MAX(...))`, lalu *Mark as date table*.
3. Tambahkan measure `Total Revenue = SUM(FactPayments[payment_value])`, `AOV = DIVIDE([Total Revenue], [Total Orders])`, dan `Revenue YoY % = DIVIDE([Total Revenue] - CALCULATE([Total Revenue], SAMEPERIODLASTYEAR(DimDate[Date])), CALCULATE([Total Revenue], SAMEPERIODLASTYEAR(DimDate[Date])))`.
