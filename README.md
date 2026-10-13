# Dari 26 Ribu Jawaban Survei yang Berantakan ke Gudang Data yang Bisa Dipercaya

**Portofolio Data Science #1: Data Cleansing, ETL, SQL Analytics, dan Predictive Modeling**
Michael Anggi G.A. · Dataset: *Ask a Manager Salary Survey 2021* (data terbuka)

> **Ringkasan.** Survei gaji publik dengan 26.232 responden ini sengaja dipilih karena datanya sangat kotor. Saya membangun pipeline ETL yang bisa diulang (satu perintah), gudang data SQLite dengan jejak audit untuk setiap koreksi, 10 query analitik SQL, dan model prediksi gaji dengan evaluasi yang jujur. Seluruh angka di bawah dapat direproduksi dari repo ini.

| Hasil kunci | Angka |
|---|---|
| Ejaan negara berbeda → negara baku | **294 → 91** |
| Ejaan industri berbeda → kategori baku | **1.068 → 32** |
| Baris layak analisis | **25.868 dari 26.232 (98,6%)**, sisanya dikeluarkan dengan alasan tercatat |
| Baris responden AS yang bisa dipakai | **21.453** (pencocokan naif `== "United States"` hanya menangkap 9.010) |
| Gerbang kualitas data (post-load) | **18/18 lulus** · 37 unit test lulus |
| Model gaji (holdout, disentuh sekali) | **R² 0,62**, error median **17%** (baseline 28%) |
| Interval prediksi 80% | cakupan nyata **79,9%** setelah kalibrasi conformal (mentah: 74,2%) |

---

## 1. Masalah dan data

Pertanyaan bisnis yang saya tetapkan: *"Berapa kisaran gaji wajar untuk sebuah profil pekerjaan, faktor apa yang paling menentukan, dan seberapa jauh angka ini bisa dipercaya?"*

Sumber: survei Ask a Manager (April–Mei 2021), 26.232 baris × 18 kolom, diambil dari repositori TidyTuesday (tautan di bagian Sumber). Data ini mewakili masalah data nyata: isian bebas, campuran mata uang, typo, dan jawaban ganda.

Contoh kekacauan yang ditemukan saat profiling:

- Negara: `USA`, `US`, `U.S.`, `United states`, `Unites States`, `Unitef Stated`, bahkan `California` dan kalimat panjang.
- Gaji: dari **0 sampai 870.000.000**, dan satu baris "USD 102 juta" yang ternyata peso Kolombia salah label.
- Mata uang "Other" dengan teks bebas: `Canadian`, `BRL (R$)`, `$76,302.34`, `RSU / equity`.
- Kolom ras berisi pilihan ganda yang opsinya mengandung koma (`Hispanic, Latino, or Spanish origin`), sehingga `split(",")` akan merusaknya.
- 148 pengiriman ganda, 233 responden yang "lama di bidang" melebihi "lama bekerja", dan 20 kombinasi usia–pengalaman yang mustahil.

## 2. Arsitektur pipeline

```
CSV mentah → extract → transform (aturan + audit log) → load SQLite → 18 gerbang kualitas
                                                          │
                                                          ├→ 10 query SQL analitik (CTE, window function)
                                                          └→ model gaji → figures + model tersimpan
```

| Lapisan | Isi |
|---|---|
| **Raw** | `raw_survey`, persis seperti diterima dan tidak pernah diubah |
| **Dimensi** | `dim_country`, `dim_industry`, `dim_job_family`, `dim_currency` |
| **Fakta** | `fact_response` (26.232 baris, FK + CHECK constraint) dan `bridge_response_race` (many-to-many) |
| **Audit** | `dq_issue_log` (12.324 catatan koreksi per baris), `dq_summary`, `map_country_raw`, `map_industry_raw` |
| **View** | `vw_analysis`, hanya baris yang layak dipercaya |

Prinsip desain: **baris tidak pernah dihapus diam-diam**. Baris yang bermasalah diberi flag dan alasan, lalu dikeluarkan dari analisis lewat satu gerbang (`is_analysis_ready`), sehingga setiap keputusan bisa diaudit dan diubah dengan mengatur satu konstanta di `config.py`.

## 3. Cleansing: apa yang dilakukan dan mengapa

![Dampak cleansing](reports/figures/fig1_cleaning_impact.png)

| Masalah | Perlakuan | Dampak |
|---|---|---|
| Negara: 294 ejaan | Bertingkat: *override* manual → alias → nama resmi (pycountry) → fuzzy match (difflib) → pencarian substring pada kalimat panjang → **"Unresolved"** (tidak pernah ditebak) | 91 negara; hanya 30 baris (0,11%) tak terselesaikan |
| Industri: 1.068 ejaan | Persis → sinonim → 39 aturan kata kunci berurutan → "Other / Unclassified" | 32 kategori; 99% baris terklasifikasi. Sampel pemetaan saya audit dan perbaiki (misal `Automotive technician` sempat salah masuk Tech) |
| Judul pekerjaan: 12.622 variasi | Normalisasi teks, lalu *seniority* dan *job family* berbasis aturan | 95,8% baris punya job family |
| Mata uang "Other" | Alias teks → kode ISO → pola regex; `AUD/NZD` dibedakan lewat negara | 578 baris diperbaiki (469 label `AUD/NZD` dibedakan lewat negara; 109 dari 133 isian "Other" dipulihkan); 24 tak terselesaikan dan dikeluarkan |
| Gaji tidak masuk akal | Dikonversi ke USD, lalu aturan berurutan: ≤0; 1–999 (ambigu ribuan/per jam); < USD 10 rb; > USD 1 jt | 143 baris dikeluarkan dengan alasan tercatat |
| Bonus > 5× gaji | Di-null-kan (salah ketik) | 30 baris |
| Pengiriman ganda | Jawaban identik dalam ≤48 jam: simpan yang pertama | 148 baris |
| Lama di bidang > lama bekerja | Dibatasi (*cap*) ke total pengalaman | 233 baris diperbaiki |
| Usia vs pengalaman mustahil | Dikeluarkan dari analisis | 20 baris |
| Ras pilihan ganda | Dicocokkan dengan daftar opsi resmi, bukan `split(",")`; disimpan di tabel *bridge* | 27.318 relasi, tanpa fragmen palsu |

Dua keputusan yang sengaja saya ambil dan saya tulis terbuka:

1. **Gaji 1–999 dikeluarkan, tidak "diselamatkan" dengan ×1000.** Judul seperti *Chief Data Scientist: 130* kemungkinan besar ribuan, tetapi *Operations Manager: 35* bisa jadi tarif per jam. Dengan 75 baris (0,29%), kehilangan datanya lebih murah daripada risiko menebak.
2. **Kurs mata uang di-hardcode (perkiraan Mei 2021) dan hanya dipakai untuk perbandingan deskriptif antarnegara.** Model memakai responden AS saja (USD), sehingga kesalahan kurs tidak bisa masuk ke model.

## 4. Kualitas data sebagai kode

`src/quality.py` menjalankan 18 gerbang terhadap gudang yang sudah terisi, dan pipeline **berhenti dengan error** bila satu saja gagal. Contohnya: rekonsiliasi jumlah baris (fakta = mentah = 26.232), tidak ada FK yatim, semua baris layak berada dalam rentang gaji valid, tidak ada duplikat di baris layak, ambang cakupan (negara tak terselesaikan ≤ 0,5%, industri tak terklasifikasi ≤ 2%, minimal 97% baris bertahan agar cleansing tidak berlebihan). Laporan lengkap: `reports/data_quality_report.md`.

## 5. Analisis SQL

Seluruh analisis ditulis sebagai SQL murni di `sql/analysis/`. SQLite tidak punya fungsi persentil, jadi median dan kuartil dihitung manual dengan `ROW_NUMBER()` dan `COUNT() OVER`:

```sql
WITH ranked AS (
  SELECT exp_overall_ord AS ord, exp_overall_band AS band, salary_usd AS v,
         ROW_NUMBER() OVER (PARTITION BY exp_overall_ord ORDER BY salary_usd) AS rn,
         COUNT(*)     OVER (PARTITION BY exp_overall_ord)                    AS n
  FROM vw_analysis WHERE country_std = 'United States'
)
SELECT band, n, ROUND(AVG(CASE WHEN rn IN ((n+1)/2, (n+2)/2) THEN v END)) AS median_usd
FROM ranked GROUP BY ord, band ORDER BY ord;
```

![Gaji berdasarkan pengalaman](reports/figures/fig2_salary_by_experience.png)

![Industri bergaji tertinggi](reports/figures/fig3_top_industries.png)

Temuan (responden AS, n ≥ ambang minimum per sel; semua deskriptif):

- **Kurva pengalaman melandai.** Median naik dari USD 59,7 rb (≤1 tahun) ke USD 91 rb (21–30 tahun); setelah ±20 tahun hampir datar (`LAG()` menunjukkan kenaikan antar-band turun dari +10–13% menjadi +6% lalu ≈0).
- **Industri menentukan.** Tech: median total kompensasi USD 130 rb (1,59× median AS), diikuti Biotech & Pharma (USD 123 rb) dan Law (USD 100,5 rb).
- **Peran data vs lainnya.** Pada tiap band pengalaman dengan sampel cukup, median gaji peran *Data & Analytics* 1,3–1,6× kelompok di luar data/software/IT; peran *Software Engineering* masih lebih tinggi lagi (misal pada 11–20 tahun: USD 145 rb vs USD 115 rb).
- **Premi pendidikan pada pengalaman setara (11–20 tahun):** S2 hanya +2% dari S1, PhD +18%, gelar profesional (MD/JD) +47%; "some college" −18%.
- **Geografi.** California median USD 101 rb tertinggi, diikuti Washington, DC, New York. Perbandingan antarnegara (kurs perkiraan, tanpa penyesuaian daya beli) hanya indikatif.

## 6. Pemodelan

**Desain evaluasi (bagian yang paling sering salah di proyek serupa):**

- Target: `log(gaji USD)`; hanya responden AS (21.453 baris).
- Split 80/20. Seleksi model memakai **5-fold CV pada 80% saja**; set uji 20% **dipakai satu kali** di akhir.
- Fitur: pengalaman, usia, pendidikan, industri, job family, seniority, negara bagian, dan teks judul pekerjaan. **Gender dan ras bukan fitur**; kompensasi lain (bonus) tidak dipakai karena bocor dari target.
- Kandidat dibandingkan dengan baseline naif (median per job family); model akhir adalah blend Ridge + TF-IDF judul (bobot 0,4) dan gradient boosting dengan token judul (bobot 0,6) hasil *randomized search*.

![Performa model](reports/figures/fig4_model_performance.png)

| Model | R² (CV, log-gaji) |
|---|---:|
| Baseline: median per job family | 0,19 |
| Ridge (fitur terstruktur) | 0,51 |
| Ridge + TF-IDF judul | 0,59 |
| Gradient boosting + token judul | 0,60 |
| **Blend (terpilih)** | **0,61** |

**Holdout:** R² 0,616 · RMSE log 0,306 · MAE USD 21.006 · error persentase median 17,2% · 57% prediksi dalam ±20% · 74% dalam ±30%. Baseline pada set yang sama: R² 0,168 dan error median 28%.

**Interval prediksi.** Kuantil 10%/90% mentah hanya mencakup 74,2% data uji (target 80%), artinya terlalu percaya diri. Dengan *conformalized quantile regression* (kalibrasi pada sebagian data latih), cakupan menjadi **79,9%** dengan lebar median USD 59,8 rb. Model dapat dipakai lewat `python -m src.predict`.

![Fitur penting](reports/figures/fig5_feature_importance.png)

Industri, judul pekerjaan, negara bagian, seniority, lama di bidang, dan pendidikan memberi kontribusi terbesar. Usia dan total pengalaman tampak kecil karena berkorelasi kuat dengan "lama di bidang"; permutation importance memang meremehkan fitur yang saling berkorelasi.

**Di mana model lemah:** peran eksekutif (error median 23%), sales (22%), dan *general management* (21%), karena kompensasi di sana sangat bervariasi; terbaik pada IT & Systems (13,5%). Band ≥41 tahun hanya 17 sampel uji, jadi angkanya tidak bisa dipercaya.

## 7. Audit keadilan: gender gap

![Gender gap](reports/figures/fig6_gender_gap.png)

Median gaji perempuan hanya 65–89% dari laki-laki pada semua band pengalaman (selisih terbesar di 11–30 tahun). Karena **gender bukan fitur model**, saya memeriksa selisih aktual vs prediksi per gender di set uji: perempuan +0,4% (CI 95%: −0,6% s.d. +1,4%), laki-laki **+2,9%** (CI: +0,4% s.d. +5,2%). Artinya, sebagian besar selisih mentah dijelaskan oleh *komposisi* (industri, peran, seniority), dengan sisa selisih kecil (±2,5 poin persen) yang tidak dijelaskan fitur.

Dua kehati-hatian penting: (1) ini **korelasi pada survei yang self-selected**, bukan bukti kausal diskriminasi; (2) seniority dan peran sendiri bisa dipengaruhi ketimpangan (*bad controls*), sehingga selisih sebenarnya bisa lebih besar dari 2,5 poin.

## 8. Keterbatasan

- **Bias sampel:** pembaca blog Ask a Manager, didominasi perempuan, kulit putih, dan sektor tech/nirlaba/pendidikan; hasil tidak mewakili populasi pekerja AS.
- **Kurs perkiraan dan tanpa penyesuaian daya beli:** perbandingan antarnegara hanya ilustratif.
- **Pemetaan berbasis aturan:** ~4% judul masuk "Other", dan aturan kata kunci tetap bisa salah pada kasus langka. Langkah berikut yang logis: embedding teks atau klasifikasi terawasi dengan sampel berlabel.
- **Gaji dilaporkan sendiri, tanpa verifikasi.** Satu band survei = rentang lebar, sehingga "pengalaman" di model adalah titik tengah band.
- **Skala:** SQLite cukup untuk 26 ribu baris. Desain (lapisan raw/clean, aturan sebagai konfigurasi, gerbang kualitas) bisa dipindah ke gudang data lain, tetapi proyek ini tidak mendemonstrasikan tooling Big Data.

## 9. Cara menjalankan

```bash
pip install -r requirements.txt
python -m src.run_pipeline          # ±2,5 menit: ETL → gerbang kualitas → SQL → model → grafik
python -m src.run_pipeline --skip-model   # hanya ETL + kualitas + SQL (±5 detik)
pytest -q                           # 37 unit test
python -m src.predict               # contoh inferensi dengan interval 80%
```

```
src/    config · clean_geo · clean_money · clean_text · clean_demo · transform · load · quality · run_sql · model · figures · predict
sql/    schema.sql · analysis/A01…A10.sql
tests/  test_cleaning.py
reports/  data_quality_report.md · model_metrics.json · tables/ · figures/
```

## 10. Pemetaan ke kebutuhan lowongan

| Kebutuhan | Bukti di proyek ini |
|---|---|
| SQL Query | Skema relasional dengan FK/CHECK, view, dan 10 query analitik (CTE, window function, pivot kondisional, `LAG`) |
| Python | Pipeline modular, unit test, evaluasi model dengan scikit-learn |
| Proses ETL | extract → transform → load idempoten dengan audit log dan gerbang kualitas |
| Data Science end-to-end | Perumusan masalah, cleansing, analisis, modeling, kalibrasi ketidakpastian, audit keadilan, inferensi |
| Platform Data Science / Big Data | Tidak ditunjukkan di proyek ini (lihat Keterbatasan) |

**Sumber data:** Ask a Manager Salary Survey 2021, didistribusikan oleh TidyTuesday: `https://github.com/rfordatascience/tidytuesday/tree/master/data/2021/2021-05-18`. Kredit data milik penyelenggara survei.
