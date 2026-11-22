# PM4Py Process Mining & Event Log Explorer (`bpic17_app`)

Aplikasi desktop berbasis **Python**, **PM4Py**, **pandas**, **Matplotlib**, dan **PySide6** untuk membaca, memvalidasi, memfilter, dan mengeksplorasi event log XES (khususnya **BPI Challenge 2017 / BPIC17**) secara interaktif tanpa angka hard-coded.

---

## 1. Struktur Folder

```text
tugas-kelompok-pm4py/
├── bpic17_app/
│   ├── __init__.py          # Metadata versi paket
│   ├── __main__.py          # Entrypoint aplikasi (`python -m bpic17_app`)
│   ├── analyzer.py          # Mesin analisis PM4Py & pandas (impor, filter, durasi, ekspor CSV)
│   └── gui.py               # Antarmuka desktop PySide6, QThread worker, & grafik Matplotlib
├── tests_app/
│   ├── test_analyzer.py          # Unit test log sintetis untuk skenario edge cases & verifikasi GUI
│   └── synthetic_edge_cases.xes  # File XES sintetis (10 case) siap dibuka di GUI saat demonstrasi
├── requirements.txt              # Daftar dependency untuk reproduksi environment
└── README.md                     # Dokumentasi instalasi, penggunaan, dan pemetaan soal ke menu
```

---

## 2. Langkah Instalasi di Komputer Lain

**Prasyarat:** Python `>= 3.11` (teruji pada Python 3.12).

1. **Clone / ekstrak source code** lalu masuk ke direktori proyek:
   ```powershell
   cd tugas-kelompok-pm4py
   ```
2. **Buat dan aktifkan virtual environment:**
   - **Windows (PowerShell):**
     ```powershell
     python -m venv .venv
     .\.venv\Scripts\Activate.ps1
     ```
   - **macOS / Linux:**
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```
3. **Instal seluruh dependency dari `requirements.txt`:**
   ```powershell
   pip install -r requirements.txt
   ```
   *(Menginstal `pm4py` otomatis turut menginstal `pandas`, `numpy`, `matplotlib`, `lxml`, `scipy`, `tqdm`, dll.)*

---

## 3. Petunjuk Penggunaan

### Menjalankan Aplikasi Desktop
Pastikan virtual environment aktif, lalu jalankan:
```powershell
python -m bpic17_app
```
Atau langsung memuat file `.xes` tertentu lewat argumen CLI:
```powershell
python -m bpic17_app --xes "path/ke/BPI Challenge 2017.xes"
```

### Alur Kerja di Aplikasi
1. **Impor Dataset XES:** Klik tombol **Open XES File...** di pojok kiri atas (atau menu `File → Open XES Event Log...`) lalu pilih file `.xes` / `.xes.gz`. Proses parsing berjalan di *background thread* (`QThread`) dengan progress bar sehingga antarmuka tidak membeku.
2. **Eksplorasi Menu Tab:** Pilih salah satu dari 6 tab utama di bagian atas untuk melihat ringkasan, menerapkan filter dinamis, atau menganalisis bottleneck durasi.
3. **Inspeksi Bukti Kasus (*Case Explorer*):** Pada tabel hasil filter mana pun, klik **Inspect Case in Explorer** (atau *double-click* baris case) untuk langsung membuka urutan event kronologis lengkap (timestamp, aktivitas, lifecycle, resource, OfferID) beserta *highlight* bukti.
4. **Ekspor & Reset:** Klik **Export CSV** di setiap tabel untuk menyimpan daftar case/bukti terpilih, **Export Summary (CSV)** di bar atas untuk ringkasan metrik, atau **Reload / Reset Filters** untuk memuat ulang analisis.
5. **Info Versi Environment:** Klik **About** di pojok kanan atas untuk melihat versi Python, PM4Py, pandas, numpy, dan PySide6.

### Menjalankan Pengujian Unit & Demo Log Sintetis (Edge Cases)
1. **Pengujian otomatis via terminal:**
   ```powershell
   python -m unittest discover -s tests_app -v
   ```
2. **Demonstrasi interaktif di GUI:** Klik **Open XES File...** lalu pilih `tests_app/synthetic_edge_cases.xes` (10 case buatan dengan total rata-rata durasi tepat `10.00` hari) untuk membuktikan seluruh 8 skenario *edge case*:
   - `CASE_01_DUP_ACCEPTED`: `O_Accepted` 2× → dihitung 1× di filter `Contains O_Accepted` (durasi tetap 10 hari penuh).
   - `CASE_02_MID_CANCELLED` vs `CASE_03_END_CANCELLED`: hanya yang berakhir `O_Cancelled` yang lolos filter `Ends With O_Cancelled` (2 case total bersama `CASE_10`).
   - `CASE_04_BOTH_ACCEPT_REFUSE`: lolos kedua filter `Contains O_Accepted` (4 case) dan `Contains O_Refused` (1 case).
   - `CASE_05_FRAUD_SCHED2_COMP1`: `schedule` 2× tapi `complete` 1× → **tidak** lolos `Rework (complete ≥ 2)`.
   - `CASE_06_FRAUD_DIFF_RES`, `CASE_07_FRAUD_SAME_RES`, `CASE_08_FRAUD_EMPTY_RES`: ketiganya lolos `Any Resource` (3 case), namun pada `Same Resource` hanya `CASE_07_FRAUD_SAME_RES` (`User_X`) yang lolos (1 case).
   - `CASE_09_CANCEL_THEN_ACCEPT` vs `CASE_10_ACCEPT_THEN_CANCEL`: pada `Sequence (O_Cancelled → O_Accepted)`, hanya `CASE_09` yang lolos (`1 / 10 = 10.00%`), sekaligus menjadi 1-satunya *Slow Case* (`50.0` hari ≥ 45 hari).

---

## 4. Pemetaan Soal Bab 11 (`BPIC-2017.pdf`) ke Navigasi Menu Aplikasi

Antarmuka aplikasi disusun berdasarkan fungsi analitik Process Mining yang umum agar pengguna dapat mengeksplorasi log secara bebas. Berikut pemetaan tiap soal wajib (dan fitur tambahan) ke tab menu serta pengaturan filter yang dipilih:

| Soal / Kebutuhan | Menu Tab di Aplikasi | Navigasi & Pengaturan Filter | Output & Bukti yang Ditampilkan |
| :--- | :--- | :--- | :--- |
| **Impor & Validasi XES** | **Top Bar** & **`Log Overview`** | Klik **Open XES File...** → pilih `BPI Challenge 2017.xes` | Nama file, status validasi, jumlah case & event, daftar atribut XES, nilai `lifecycle:transition`, & ketersediaan `org:resource`. |
| **Exercise 11.7 A** *(Jumlah keseluruhan case)* | **`Log Overview`** | Langsung tampil di kartu KPI **TOTAL CASES** (atau baris `All Cases` di tab berikutnya) | `31,509` unique cases. |
| **Exercise 11.7 B** *(Rata-rata cycle time seluruh case)* | **`Log Overview`** | Langsung tampil di kartu KPI **MEAN CYCLE TIME** & tabel **All Cases & Cycle Time Duration** | `21.9 days` (`21.8996 days`) dihitung dari `max - min` timestamp trace utuh. |
| **Exercise 11.7 C** *(Successful cases & mean cycle time — contains `O_Accepted`)* | **`Activity & Endpoint Filter`** | • **Filter Rule:** `Contains Activity (≥ 1 in trace)`<br>• **Activity:** `O_Accepted`<br>• **Lifecycle:** `All` → klik **Apply Filter** *(opsional: klik **Pin to Comparison**)* | Jumlah case (`17,228`), persentase (`54.68%`), mean cycle time trace utuh (`18.1 days`), daftar case ID, & tombol **Inspect Case in Explorer**. |
| **Exercise 11.7 D** *(Unsuccessful cases & mean cycle time — contains `O_Refused`)* | **`Activity & Endpoint Filter`** | • **Filter Rule:** `Contains Activity (≥ 1 in trace)`<br>• **Activity:** `O_Refused`<br>• **Lifecycle:** `All` → klik **Apply Filter** | Jumlah case (`3,720`), persentase (`11.81%`), mean cycle time trace utuh (`16.9 days`), daftar case ID (tidak dipaksa saling eksklusif dengan 11.7 C). |
| **Exercise 11.7 E** *(Canceled cases & mean cycle time — event terakhir `O_Cancelled`)* | **`Activity & Endpoint Filter`** | • **Filter Rule:** `Ends With Activity (Last event in trace)`<br>• **Activity:** `O_Cancelled`<br>• **Lifecycle:** `All` → klik **Apply Filter** | Jumlah case (`4,436`), persentase (`14.08%`), mean cycle time (`23.5 days`), daftar case yang benar-benar berakhir di `O_Cancelled`. |
| **Exercise 11.15** *(`W_Assess Potential Fraud` selesai `complete` minimal 2×)* | **`Rework & Resource Filter`** | • **Activity:** `W_Assess potential fraud`<br>• **Lifecycle:** `complete`<br>• **Min Occurrences (≥):** `2`<br>• **Resource Scope:** `Any Resource (Case-Level Rework)` → klik **Apply Filter** | Jumlah case (`13 cases` / `0.0413%`), jumlah event bukti (`27 events`), tabel case terpilih, & tabel **Supporting Event Evidence** berstatus `complete`. |
| **Exercise 11.18** *(`W_Assess Potential Fraud` selesai `complete` minimal 2× oleh resource sama)* | **`Rework & Resource Filter`** | • Pengaturan sama seperti 11.15<br>• Ubah **Resource Scope:** `Same Resource (Identical Resource in Case)`<br>• Centang **Exclude Empty / UNKNOWN Resource** → klik **Apply Filter** | Jumlah case (`3 cases`), Resource ID identik (`User_144`, `User_143`), jumlah penyelesaian per resource, timestamp bukti, & tombol **Inspect Case in Explorer**. |
| **Exercise 11.22** *(`O_Cancelled` diikuti `O_Accepted` kemudian dalam trace & persentasenya)* | **`Sequence & Follower Filter`** | • **First Activity (A):** `O_Cancelled`<br>• **Relation:** `Eventually Followed By (A ... → B, i < j)`<br>• **Second Activity (B):** `O_Accepted`<br>• **Lifecycle:** `All` → klik **Apply Sequence Filter** | Jawaban `Yes`, numerator (`902 cases`), denominator (`31,509 cases`), persentase (`2.86%`), & tabel pasangan event saksi (*witness pairs* + `events_between`). |
| **Fitur Tambahan — Example 11.10** *(Fast `< 45d` vs Slow `≥ 45d` & Histogram)* | **`Duration & Bottlenecks`** | • Atur **Slow Case Threshold (days):** `45.0` → klik **Apply Split** | Perbandingan jumlah & persentase Fast (`30,198`) vs Slow (`1,311`), histogram distribusi durasi, grafik bottleneck aktivitas, & daftar *Slow Cases*. |
| **Case Explorer & Ekspor CSV** | **`Case Explorer`** & tombol **Export CSV** di tiap tab | Cari Case ID di panel kiri atau klik **Inspect Case in Explorer** dari tab mana saja; pilih **Highlight Activity** di kanan atas | Urutan kronologis event (`step`, `timestamp`, `activity`, `lifecycle`, `resource`, `OfferID`) dengan *highlight* warna & ekspor CSV. |

---

## 5. Sumber Dataset

Dataset **BPI Challenge 2017 (`BPI Challenge 2017.xes`)** tidak disertakan dalam repositori ini karena ukurannya (~552 MB). Dataset asli dapat diunduh dari sumber resmi:

- **4TU.ResearchData — BPI Challenge 2017:** https://data.4tu.nl/articles/dataset/BPI_Challenge_2017/12696884 (`doi:10.4121/uuid:5f3067df-f10b-45da-b98b-86ae4c7a310b`)
