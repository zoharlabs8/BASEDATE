# ZETAPP - Drive | Foto/Drive → Excel

Aplikasi 1-klik: upload foto buku tulis tangan inventarisasi pertanian atau link Google Drive → langsung jadi Excel TAMPLATE (100% format asli, auto-tambah baris, nama file otomatis dari foto, support 5+ user bersamaan).

**Live:** `http://localhost:8501` (judul: ZETAPP - Drive)

## Fitur
- Upload foto / Drive Folder (7 foto sekaligus) → baca satu per satu via Gemini 3.5-flash (API key AQ.) → hitung B/S/K (Kecil/Sedang/Besar) → isi TAMPLATE
- Template `sample/TAMPLATE DATA .xlsx` kosong → auto-tambah baris jika foto punya 19 komoditi >7 baris
- Nama file otomatis: `Bas_Hark_13-08-2026.xlsx` atau `PERTANIAN_Ridwan_Saharia.xlsx`
- 5+ user: session isolasi per user (folder temp per sesi), tidak tabrakan

## Jalankan Lokal
```bash
cd aplikasi-laporan-pertanian
pip install -r requirements.txt
cp .env.example .env  # isi GEMINI_API_KEY
./run_local.sh
# atau: streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

## Deploy
- Docker: `docker-compose up --build`
- Streamlit Cloud: push ke GitHub → deploy di share.streamlit.io

Original template: `sample/TAMPLATE DATA .xlsx`
