FROM python:3.11-slim
WORKDIR /app
# system deps
RUN apt-get update && apt-get install -y libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app/aplikasi-laporan-pertanian
COPY sample /app/sample
WORKDIR /app/aplikasi-laporan-pertanian
EXPOSE 8501
# untuk 5+ user bersamaan, streamlit handle session isolasi per user
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true", "--server.maxUploadSize=50", "--browser.gatherUsageStats=false"]
