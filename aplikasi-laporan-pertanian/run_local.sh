#!/bin/bash
# run_local.sh — Jalankan aplikasi 100% di localhost tanpa API key
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "🌾 Pertanian Laporan — Localhost Mode (Tanpa API Key)"
echo "======================================================"

# cek python
if ! command -v python3 &> /dev/null; then
  echo "❌ python3 tidak ditemukan"
  exit 1
fi

# install deps jika belum
if ! python3 -c "import streamlit" 2>/dev/null; then
  echo "📦 Install dependencies..."
  pip install -r requirements.txt
fi

# cek template
if [ ! -f "../sample/TAMPLATE DATA .xlsx" ]; then
  echo "⚠️  Template tidak ditemukan di ../sample/TAMPLATE DATA .xlsx"
fi

echo ""
echo "✅ Siap! Membuka di http://localhost:8501"
echo "   - Upload foto langsung di browser"
echo "   - Mode default: Offline (tanpa API key)"
echo "   - Opsional vision offline: ollama pull llava && ollama serve"
echo ""
echo "Tekan Ctrl+C untuk stop"
echo ""

# jalankan streamlit di localhost saja (tidak expose ke network)
python3 -m streamlit run app.py \
  --server.port 8501 \
  --server.address localhost \
  --server.headless true \
  --browser.gatherUsageStats false
