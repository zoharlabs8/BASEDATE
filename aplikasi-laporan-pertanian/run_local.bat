@echo off
echo ZETAPP - Drive | Foto / Drive -> Excel
echo =====================================
python --version
if errorlevel 1 (
  echo Python tidak ditemukan, install dari https://www.python.org
  pause
  exit /b
)
pip install -r requirements.txt
python -m streamlit run app.py --server.address localhost --server.port 8501 --server.headless true
pause
