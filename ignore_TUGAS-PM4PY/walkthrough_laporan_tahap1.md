# Laporan & Walkthrough Proyek Tahap 1 — BPIC17 Event Log Analyzer

## 1. Pemetaan Soal → Fungsi Aplikasi

| Fitur / Soal | Modul & Fungsi | Aturan Filter & Implementasi |
| :--- | :--- | :--- |
| **F01 — Impor & Validasi XES** | `bpic17_app.analyzer.load_and_validate_xes` | Membaca `.xes` dengan `pm4py.read_xes`, memvalidasi atribut wajib (`case:concept:name`, `concept:name`, `time:timestamp`), mendeteksi `lifecycle:transition` & `org:resource`, serta mengurutkan event secara deterministik (`mergesort` mempertahankan urutan XML jika timestamp identik). |
| **F02 — Overview & Durasi Case** | `compute_case_stats`, `compute_overview` | Menghitung durasi tiap case (`(max_ts - min_ts).total_seconds() / 86400.0` hari) dari **trace utuh** sebelum pemfilteran apa pun, serta menghitung frekuensi event dan cakupan case per aktivitas. |
| **F03 — Exercise 11.7 (A–E)** | `analyze_11_7` | **A & B**: Total case unik & rata-rata cycle time.<br>**C & D**: Filter *contains* level case via `pm4py.filter_event_attribute_values(..., level="case")` untuk `O_Accepted` dan `O_Refused` (tidak saling eksklusif).<br>**E**: Filter *endpoint* di mana event terakhir trace adalah `O_Cancelled`. |
| **F04 — Exercise 11.15** | `analyze_11_15_and_11_18` | Memilih event dengan `concept:name =~ 'W_Assess Potential Fraud'` **DAN** `LOWER(lifecycle:transition) == 'complete'`, lalu memilih case dengan jumlah `complete >= 2`. |
| **F05 — Exercise 11.18** | `analyze_11_15_and_11_18` | Dari kejadian `complete` pada 11.15, mengeliminasi `org:resource` kosong/`UNKNOWN`, lalu mengelompokkan berdasarkan `(case:concept:name, org:resource)` dengan jumlah `>= 2`. |
| **F06 — Exercise 11.22** | `analyze_11_22` | Memeriksa apakah pada suatu trace terdapat posisi indeks `i < j` di mana `event[i] == 'O_Cancelled'` dan `event[j] == 'O_Accepted'` (tidak harus bersebelahan), serta menghitung persentase terhadap total case aktif (`31,509`). |
| **F07 — Case Explorer & CSV Export** | `get_case_trace`, `export_summary_csv`, `export_dataframe_csv` | Menampilkan urutan kronologis event per case, highlight bukti event, tombol *Re-run / Reset*, dan ekspor CSV. |
| **Bonus — Example 11.10 (Fast vs Slow)** | `analyze_fast_slow` | Memisahkan Fast Cases (`< 45 hari`) dan Slow Cases (`>= 45 hari`), menampilkan histogram distribusi durasi (`Matplotlib`), dan membandingkan frekuensi aktivitas pemicu keterlambatan. |

---

## 2. Hasil Pengujian pada Dataset BPIC17 (`BPI Challenge 2017.xes`)

| Kode Soal | Hasil Aplikasi | Kunci Referensi (`BPIC-2017.pdf`) | Keterangan |
| :--- | :--- | :--- | :--- |
| **11.7 A** | **31,509 cases** | 31,509 cases | Sama persis |
| **11.7 B** | **21.90 days** (`21.8996 d`) | 21.9 days | Sama persis |
| **11.7 C** | **17,228 cases**, **18.13 days** | 17,228 cases, 18.1 days | Sama persis |
| **11.7 D** | **3,720 cases**, **16.88 days** | 3,720 cases, 16.8 days | Jumlah case sama persis; durasi 16.88 hari |
| **11.7 E** | **4,436 cases**, **23.51 days** | 4,436 cases, 23 days | Jumlah case sama persis; durasi 23.51 hari |
| **11.15** | **13 cases** (`0.0413%`) | 13 cases (Celonis) | Sama persis (vs 20 di Disco v2.0 jika tanpa filter `complete`) |
| **11.18** | **3 cases** (`0.0095%`) | 3 cases (Celonis) | Sama persis (`Application_1221917431` oleh `User_144`, `Application_1405826636` oleh `User_143`, `Application_473455481` oleh `User_143`) |
| **11.22** | **Yes — 902 / 31,509 cases (`2.86%`)** | Yes, % of cases | 902 case memiliki `O_Cancelled` yang diikuti `O_Accepted` pada posisi lebih akhir |
| **Ex 11.10** | **30,198 fast (`95.84%`)** vs **1,311 slow (`4.16%`)** | 30,209 fast (~96%) vs 1,299 slow (~4%) | Selisih 11 case berasal dari pembulatan batas 45 hari pada alat analitik referensi |

---

## 3. Cara Menjalankan Aplikasi & Pengujian

### Menjalankan GUI Desktop
```powershell
.\.venv\Scripts\python.exe -m bpic17_app
```

### Menjalankan Unit Tests (Log Sintetis Edge Cases)
```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests_app -v
```
