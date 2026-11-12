"""
Data Cleaning & Preprocessing — Olist Customers Dataset
=======================================================
Input  : data/raw/olist_customers_dataset.csv   (tidak pernah diubah)
Output : data/processed/
           - customers_clean.csv     (grain: customer_id, 1 baris per record pelanggan/pesanan)
           - dim_customer.csv        (grain: customer_unique_id, 1 baris per orang)
           - dim_city.csv            (grain: city_state_key)
           - dim_state.csv           (grain: customer_state)
           - cleaning_log.csv        (ringkasan before/after setiap langkah)

Jalankan dari root proyek:
    python scripts/data_cleaning.py
"""
from pathlib import Path
import unicodedata
import re

import sys
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "olist_customers_dataset.csv"
OUT = ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)

# Referensi eksternal (IBGE): nama negara bagian & 5 makro-region Brasil.
# Ini ENRICHMENT dari pengetahuan umum, bukan bagian dari dataset.
STATE_REF = {
    "AC": ("Acre", "Norte"), "AP": ("Amapá", "Norte"), "AM": ("Amazonas", "Norte"),
    "PA": ("Pará", "Norte"), "RO": ("Rondônia", "Norte"), "RR": ("Roraima", "Norte"),
    "TO": ("Tocantins", "Norte"),
    "AL": ("Alagoas", "Nordeste"), "BA": ("Bahia", "Nordeste"), "CE": ("Ceará", "Nordeste"),
    "MA": ("Maranhão", "Nordeste"), "PB": ("Paraíba", "Nordeste"), "PE": ("Pernambuco", "Nordeste"),
    "PI": ("Piauí", "Nordeste"), "RN": ("Rio Grande do Norte", "Nordeste"), "SE": ("Sergipe", "Nordeste"),
    "DF": ("Distrito Federal", "Centro-Oeste"), "GO": ("Goiás", "Centro-Oeste"),
    "MT": ("Mato Grosso", "Centro-Oeste"), "MS": ("Mato Grosso do Sul", "Centro-Oeste"),
    "ES": ("Espírito Santo", "Sudeste"), "MG": ("Minas Gerais", "Sudeste"),
    "RJ": ("Rio de Janeiro", "Sudeste"), "SP": ("São Paulo", "Sudeste"),
    "PR": ("Paraná", "Sul"), "RS": ("Rio Grande do Sul", "Sul"), "SC": ("Santa Catarina", "Sul"),
}

log = []


def snapshot(step: str, df: pd.DataFrame, note: str = "") -> None:
    log.append({"step": step, "rows": len(df), "cols": df.shape[1],
                "missing_cells": int(df.isna().sum().sum()),
                "duplicate_rows": int(df.duplicated().sum()), "note": note})
    print(f"[{step}] rows={len(df):,} cols={df.shape[1]} | {note}")


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


# 1. LOAD — semua kolom dibaca sebagai string agar leading zero kode pos tidak hilang
raw = pd.read_csv(RAW, dtype=str)
snapshot("0_raw", raw, "data mentah")
df = raw.copy()  # data asli tidak diubah

# 2. MISSING VALUES — validasi (hasil profiling: 0 missing). Tetap dijaga sebagai guard.
missing = df.isna().sum()
assert missing.sum() == 0, f"Ada missing value tak terduga:\n{missing}"
snapshot("1_missing_check", df, "0 missing value -> tidak ada imputasi")

# 3. DUPLIKAT — baris identik & duplikat primary key
n_dup = df.duplicated().sum()
n_dup_pk = df["customer_id"].duplicated().sum()
df = df.drop_duplicates()
snapshot("2_duplicates", df, f"duplikat baris={n_dup}, duplikat customer_id={n_dup_pk} -> tidak ada yang dihapus")

# 4. STANDARDISASI FORMAT
for c in df.columns:
    df[c] = df[c].str.strip()
df["customer_zip_code_prefix"] = df["customer_zip_code_prefix"].str.zfill(5)
df["customer_state"] = df["customer_state"].str.upper()
df["customer_city"] = (df["customer_city"].map(strip_accents).str.lower()
                       .str.replace(r"\s+", " ", regex=True))
snapshot("3_standardize", df, "trim, zfill(5) kode pos, UPPER state, lower+tanpa aksen city")

# 5. VALIDASI NILAI
bad_state = ~df["customer_state"].isin(STATE_REF)
bad_zip = ~df["customer_zip_code_prefix"].str.fullmatch(r"\d{5}")
bad_id = ~df["customer_id"].str.fullmatch(r"[0-9a-f]{32}") | ~df["customer_unique_id"].str.fullmatch(r"[0-9a-f]{32}")
print(f"   invalid state={bad_state.sum()}, invalid zip={bad_zip.sum()}, invalid id={bad_id.sum()}")
assert bad_state.sum() == 0 and bad_zip.sum() == 0 and bad_id.sum() == 0
snapshot("4_validate", df, "state termasuk 27 UF, zip 5 digit, id 32-hex: semua valid")

# 6. INKONSISTENSI NAMA KOTA — cek varian penulisan (mis. 'mogi-guacu' vs 'mogi guacu')
key = df["customer_city"].str.replace(r"[-'’]", " ", regex=True).str.replace(r"\s+", " ", regex=True)
variants = (df.assign(_k=key).groupby(["customer_state", "_k"])["customer_city"]
            .nunique().loc[lambda s: s > 1])
print(f"   varian nama kota dalam state yang sama: {len(variants)}")
if len(variants):
    # standarkan ke ejaan yang paling sering muncul
    canon = (df.assign(_k=key).groupby(["customer_state", "_k"])["customer_city"]
             .agg(lambda s: s.value_counts().idxmax()))
    df["customer_city"] = [canon[(s, k)] for s, k in zip(df["customer_state"], key)]
snapshot("5_city_consistency", df, f"{len(variants)} grup varian kota distandarkan")

# 7. FEATURE ENGINEERING
df["city_state_key"] = df["customer_city"] + " - " + df["customer_state"]  # kota homonim lintas state
df["state_name"] = df["customer_state"].map(lambda s: STATE_REF[s][0])
df["region"] = df["customer_state"].map(lambda s: STATE_REF[s][1])
df["city_display"] = (df["customer_city"].str.title()
                      .str.replace(r"\b(Do|Da|De|Dos|Das|E)\b", lambda m: m.group(0).lower(), regex=True)
                      .str.replace(r"D'(\w)", lambda m: "d'" + m.group(1).upper(), regex=True)
                      .str.replace(r"^(\w)", lambda m: m.group(1).upper(), regex=True))

ids_per_person = df.groupby("customer_unique_id")["customer_id"].transform("count")
df["records_per_customer"] = ids_per_person
df["is_repeat_customer"] = ids_per_person > 1
snapshot("6_features", df, "city_state_key, state_name, region, city_display, records_per_customer, is_repeat_customer")

# 8. OUTLIER — jumlah record per pelanggan (IQR tidak bermakna karena Q1=Q3=1);
#    pelanggan >= 5 record diberi flag, TIDAK dihapus (bisa jadi pembeli loyal / reseller).
df["is_high_frequency"] = ids_per_person >= 5
snapshot("7_outlier_flag", df, f"{df.loc[df.is_high_frequency,'customer_unique_id'].nunique()} pelanggan ditandai high-frequency (>=5 record)")

# 9. TABEL TURUNAN UNTUK POWER BI
def segment(n: int) -> str:
    return "1. One-time" if n == 1 else ("2. Repeat (2x)" if n == 2 else "3. Loyal (3x+)")

# lokasi utama per orang = lokasi paling sering (tie -> urutan pertama di data)
primary_loc = (df.groupby(["customer_unique_id", "city_state_key", "customer_state", "region"])
               .size().reset_index(name="n")
               .sort_values(["customer_unique_id", "n"], ascending=[True, False])
               .drop_duplicates("customer_unique_id"))
dim_customer = (df.groupby("customer_unique_id")
                .agg(records=("customer_id", "count"),
                     distinct_states=("customer_state", "nunique"),
                     distinct_cities=("city_state_key", "nunique"),
                     distinct_zips=("customer_zip_code_prefix", "nunique"))
                .reset_index()
                .merge(primary_loc.drop(columns="n"), on="customer_unique_id"))
dim_customer["segment"] = dim_customer["records"].map(segment)
dim_customer["is_repeat_customer"] = dim_customer["records"] > 1
dim_customer["moved_location"] = dim_customer["distinct_zips"] > 1
dim_customer = dim_customer.rename(columns={"city_state_key": "primary_city_state_key",
                                            "customer_state": "primary_state",
                                            "region": "primary_region"})

dim_state = (pd.DataFrame([(k, v[0], v[1]) for k, v in STATE_REF.items()],
                          columns=["customer_state", "state_name", "region"])
             .sort_values("customer_state"))
dim_city = (df.groupby(["city_state_key", "customer_city", "city_display", "customer_state"])
            .size().reset_index(name="customer_records")
            .drop(columns="customer_records"))

clean_cols = ["customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city",
              "city_display", "customer_state", "state_name", "region", "city_state_key",
              "records_per_customer", "is_repeat_customer", "is_high_frequency"]
customers_clean = df[clean_cols]

# 10. VALIDASI AKHIR — memastikan preprocessing tidak menimbulkan kesalahan baru
assert len(customers_clean) == len(raw), "Jumlah baris berubah!"
assert customers_clean["customer_id"].is_unique
assert customers_clean["customer_unique_id"].nunique() == raw["customer_unique_id"].nunique() == len(dim_customer)
assert dim_customer["records"].sum() == len(raw)
assert dim_city["city_state_key"].is_unique
assert set(customers_clean["city_state_key"]) <= set(dim_city["city_state_key"])
assert set(dim_customer["primary_city_state_key"]) <= set(dim_city["city_state_key"])

customers_clean.to_csv(OUT / "customers_clean.csv", index=False)
dim_customer.to_csv(OUT / "dim_customer.csv", index=False)
dim_city.to_csv(OUT / "dim_city.csv", index=False)
dim_state.to_csv(OUT / "dim_state.csv", index=False, encoding="utf-8-sig")
pd.DataFrame(log).to_csv(OUT / "cleaning_log.csv", index=False)

print("\nBEFORE vs AFTER")
print(f"  raw   : {raw.shape}  kolom={list(raw.columns)}")
print(f"  clean : {customers_clean.shape}  (+{customers_clean.shape[1]-raw.shape[1]} kolom turunan)")
print(f"  dim_customer={dim_customer.shape} dim_city={dim_city.shape} dim_state={dim_state.shape}")
print("Semua validasi lolos. Output tersimpan di", OUT)
