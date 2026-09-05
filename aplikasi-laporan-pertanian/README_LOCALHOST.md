# 🏠 Localhost — Tanpa API Key (100% Offline)

Aplikasi sekarang **default jalan di localhost tanpa butuh API key sama sekali**.

## Cara Paling Mudah (Tanpa API, Tanpa Ollama)

1. Jalankan di terminal:
```bash
cd "/Users/etikastudio/Documents/PERTANIAN/aplikasi-laporan-pertanian"
chmod +x run_local.sh
./run_local.sh
# atau manual:
streamlit run app.py --server.address localhost --server.port 8501
```
2. Buka `http://localhost:8501` di browser
3. Pilih mode **✅ Localhost Offline (Default)** di sidebar
4. Upload foto buku → klik **Ekstrak (Localhost, Tanpa API Key)** → sistem akan minta kamu **Paste Transkrip Manual** di bawah
5. Paste tulisan tangan (contoh: `JATI PUTIH B 1+1+1 S 1+1 K 1+2+...`) → klik **Parse Transkrip Manual** → cek Tab Preview → Download Excel

> Ini **paling akurat** untuk tulisan tangan, karena kamu verifikasi langsung di Tab 2 (axpert verify). Tidak butuh internet.

## Opsi Vision 100% Offline (Ollama)

Jika ingin tetap otomatis baca foto **tanpa API key** tapi tidak mau paste manual, pakai Ollama lokal:

```bash
# 1. Install Ollama (macOS)
brew install ollama

# 2. Pull model vision (pilih salah satu, ~4-7GB)
ollama pull llava          # paling ringan
# atau
ollama pull qwen2-vl
ollama pull bakllava

# 3. Jalan server Ollama (biarkan jalan di terminal lain)
ollama serve

# 4. Di Streamlit sidebar pilih: 🖥️ Ollama Lokal (llava/qwen2-vl)
#    Host: http://localhost:11434  Model: llava
```

Semua proses foto → JSON → Excel jalan di `localhost`, tidak kirim data ke OpenAI/Google.

## Opsi OCR Murni Offline (Tesseract)

```bash
brew install tesseract
pip install pytesseract pillow

# Di sidebar pilih: 🔤 Tesseract OCR Lokal
```

Cocok untuk tulisan cetak; tulisan tangan akan tetap butuh koreksi di Tab Preview.

## Kenapa Localhost Direkomendasikan?

- **Privasi**: foto tidak keluar dari laptop
- **Gratis selamanya**: tanpa kuota API
- **Zero Data Loss**: tetap pakai parser `B/S/K` yang sama + verifikasi manual di Tab 2
- **Template 100% preserve**: `excel_generator.py` tetap pakai `TAMPLATE DATA .xlsx` asli

## Perbandingan Mode

| Mode | Butuh API Key | Butuh Internet | Akurasi Tulisan Tangan | Biaya |
|------|---------------|----------------|------------------------|-------|
| ✅ Localhost Offline (paste manual) | ❌ | ❌ | ⭐⭐⭐⭐⭐ (kamu yang verifikasi) | Gratis |
| 🖥️ Ollama llava/qwen2-vl | ❌ | ❌ (setelah pull) | ⭐⭐⭐⭐ | Gratis |
| 🔤 Tesseract | ❌ | ❌ | ⭐⭐ (cetak ok) | Gratis |
| ☁️ OpenAI/Gemini | ✅ | ✅ | ⭐⭐⭐⭐⭐ | Bayar |

## File Penting

- `run_local.sh` — sekali klik jalan di localhost
- `extractor_local.py` — logic Ollama & Tesseract lokal
- `app.py` — default provider sekarang `Localhost Offline`
