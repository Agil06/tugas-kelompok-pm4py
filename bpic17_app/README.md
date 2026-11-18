# PM4Py Process Mining & Event Log Explorer (`bpic17_app`)

Aplikasi desktop interaktif berbasis **Python**, **PM4Py**, **pandas**, **Matplotlib**, dan **PySide6** untuk mengeksplorasi event log XES secara dinamis.

---

## Fitur Utama & Workspace Tab

1. **Log Overview**: Ringkasan total case, total event, rata-rata/median/maksimum cycle time (hari), rentang waktu log, tabel frekuensi & cakupan aktivitas, serta tabel durasi per case.
2. **Activity & Endpoint Filter**: Filter case secara interaktif dengan aturan *Contains Activity*, *Ends With Activity*, *Starts With Activity*, atau *Does Not Contain Activity* beserta filter transisi lifecycle dan tabel komparasi (*Pin to Comparison*).
3. **Rework & Resource Filter**: Eksplorasi pengulangan aktivitas ($\ge N$ kali) berdasarkan transisi lifecycle (`complete`, `schedule`, `All`, dll.) dengan pilihan cakupan *Any Resource* (level case) atau *Same Resource* (resource identik dalam case yang sama) serta tabel event bukti.
4. **Sequence & Follower Filter**: Analisis urutan dua aktivitas (`Event A` diikuti `Event B`) dengan mode *Eventually Followed By ($i < j$)* atau *Directly Followed By ($j = i + 1$)*, dilengkapi persentase terhadap total case dan tabel pasangan event saksi (*witness pairs*).
5. **Duration & Bottlenecks**: Pemisahan *Fast Cases* vs *Slow Cases* menggunakan ambang durasi hari yang dapat diatur secara interaktif (default `45.0` hari), dilengkapi histogram distribusi durasi (`Matplotlib`) dan grafik perbandingan aktivitas bottleneck.
6. **Case Explorer**: Pencarian Case ID, pemilihan *Highlight Activity* secara dinamis, tampilan kronologis seluruh event dalam case, dan ekspor CSV di setiap tabel.

---

## Instalasi & Cara Menjalankan

1. Aktifkan virtual environment:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```
2. Instal dependency (jika belum):
   ```powershell
   pip install -r requirements-app.txt
   ```
3. Jalankan aplikasi desktop:
   ```powershell
   python -m bpic17_app
   ```
4. Jalankan pengujian unit:
   ```powershell
   python -m unittest discover -s tests_app -v
   ```
