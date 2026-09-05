# 🌾 Aplikasi Laporan Pertanian — Foto / Drive → Excel TAMPLATE

Aplikasi **axpert data entry** untuk mengubah foto buku tulis tangan inventarisasi tanaman menjadi **file Excel yang 100% identik dengan `TAMPLATE DATA .xlsx`** (merge, border, font, formula).

> Prinsip: **Zero Data Loss** — semua coretan angka `B/S/K` dan `1+2+3` dihitung satu per satu tanpa ada yang hilang.

## Fitur
- **Upload foto multiple** (JPG/PNG) atau **paste Link Google Drive** (folder/file berisi foto)
- **AI Vision**: OpenAI GPT-4o & Gemini 1.5 Pro dengan prompt ultra-detail untuk tulisan tangan
- **Fallback parser lokal**: hitung `B=Kecil?` sebenarnya `K=Kecil, S=Sedang, B=Besar` dengan penjumlahan `5+5+10`
- Preview & edit axpert sebelum download (tabel editable, tambah/hapus komoditi)
- Generate Excel: 1 sheet per pemilik lahan, formula `=SUM(C15:E15)` dan `=SUM(C15:C33)` otomatis, border & merge dipertahankan

## Struktur Folder
```
PERTANIAN/
  sample/
    TAMPLATE DATA .xlsx        # template resmi
    WhatsApp Image ... .jpeg   # foto sample
  aplikasi-laporan-pertanian/
    app.py                     # Streamlit UI
    extractor.py               # AI Vision + parser B/S/K + Drive downloader
    excel_generator.py         # pengisi template 100% preserve format
    requirements.txt
    output_*.xlsx              # contoh hasil dari foto sample
```

## Cara Jalan
```bash
cd /Users/etikastudio/Documents/PERTANIAN/aplikasi-laporan-pertanian
pip install -r requirements.txt
streamlit run app.py --server.port 8501
# buka http://localhost:8501
```

### API Keys (opsional tapi direkomendasikan untuk tulisan tangan)
Buat file `.env` atau set ENV:
```
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
```
Jika tidak ada API key, aplikasi tetap jalan dengan **mode Offline** (paste transkrip manual) + parser B/S/K — tetap akurat tapi butuh verifikasi manual di Tab Preview.

### Alur Pakai
1. **Tab 1 Upload**: upload foto buku atau paste link Drive → klik `Ekstrak dengan AI Vision` atau `Pakai Data Sample`
2. **Tab 2 Preview & Edit**: cek setiap pemilik (RIDWAN, SAHARIA), edit angka Kecil/Sedang/Besar langsung di tabel, klik `Simpan Edit Tabel`
3. **Tab 3 Download**: klik `Generate & Download Excel` → file `.xlsx` siap print, formula Jumlah otomatis

### Notasi B/S/K
Buku menggunakan:
- `B` = Besar/Produktif → kolom E
- `S` = Sedang → kolom D
- `K` = Kecil → kolom C
- `=` tanpa huruf = total tanpa breakdown → masuk ke Besar (bisa diedit)
- Baris lanjutan `S 1+1` di bawah `JATI PUTIH B ...` akan ditambahkan ke total yang sama

Contoh: `JATI PUTIH B 1+1+1 S 1+1 K 1+2+0+1` → Kecil=4, Sedang=2, Besar=3

## Hasil Contoh dari Foto Sample
- `output_AUDIT_3sheet.xlsx` — 3 sheet sesuai 3 blok NAMA di foto: `Ridwan_Sawa` (3 komoditi), `Ridwan_Pematang` (19 komoditi), `Saharia_Kebung` (9 komoditi)
- `output_FINAL_2sheet.xlsx` — 2 sheet gabungan: `RIDWAN` (20 komoditi ter-merge) & `Saharia_Kebung`

Kedua file sudah diverifikasi: formula, border, merge, header `Nama Pemilik` & `Batas-batas` terisi.

## Tips Axpert
- Foto buram/miring? AI Vision tetap baca dengan `detail: high`, tapi selalu cek Tab 2
- Link Drive harus `Anyone with the link` (Viewer)
- Untuk hasil 100%, pakai GPT-4o/Gemini + verifikasi manual di Tabel

## Dependensi
streamlit, openpyxl, pandas, pillow, openai, google-generativeai, gdown, python-dotenv
