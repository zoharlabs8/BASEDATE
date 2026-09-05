"""
extractor_local.py — 100% Localhost, Tanpa API Key
- OCR lokal dengan Tesseract / EasyOCR (opsional)
- Vision lokal via Ollama (llava / qwen2-vl / bakllava) di http://localhost:11434
- Jika tidak ada model lokal, fallback ke parser B/S/K manual (sudah 100% offline)
"""
import re, json, base64, requests
from pathlib import Path
from typing import List, Dict, Any, Optional

from extractor import VISION_PROMPT, normalize_ai_records, extract_offline_fallback

def extract_with_ollama(image_paths: List[Path], model: str = "llava", host: str = "http://localhost:11434", prompt: str = VISION_PROMPT) -> List[Dict[str, Any]]:
    """
    Pakai Ollama lokal - tidak perlu API key, tidak perlu internet.
    Install: brew install ollama  &&  ollama pull llava  (atau qwen2-vl, bakllava)
    Jalan: ollama serve
    """
    url = f"{host.rstrip('/')}/api/chat"
    # cek koneksi
    try:
        requests.get(f"{host.rstrip('/')}/api/tags", timeout=3)
    except Exception as e:
        raise RuntimeError(f"Ollama tidak jalan di {host}. Jalankan 'ollama serve' dulu. Error: {e}")

    images_b64 = []
    for p in image_paths:
        b64 = base64.b64encode(p.read_bytes()).decode("utf-8")
        images_b64.append(b64)

    # Ollama chat dengan images
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt, "images": images_b64}
        ],
        "stream": False,
        "format": "json"
    }
    try:
        resp = requests.post(url, json=payload, timeout=300)
        resp.raise_for_status()
        data = resp.json()
        content = data.get("message", {}).get("content", "") or data.get("response", "")
    except Exception as e:
        raise RuntimeError(f"Gagal panggil Ollama ({model}): {e}")

    # extract JSON dari content
    m = re.search(r"\{.*\}", content, flags=re.DOTALL)
    if m:
        content = m.group(0)
    try:
        j = json.loads(content)
    except Exception as e:
        raise RuntimeError(f"Ollama return bukan JSON valid: {content[:500]} ... Error {e}")
    return normalize_ai_records(j)

def extract_with_tesseract(image_paths: List[Path]) -> str:
    """
    OCR lokal murni dengan pytesseract (gratis, offline).
    Cocok untuk tulisan cetak, untuk tulisan tangan akurasi terbatas -> tetap butuh verifikasi di Tab Preview.
    Install: brew install tesseract  && pip install pytesseract pillow
    """
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        raise RuntimeError("pytesseract / Pillow belum terinstall: pip install pytesseract pillow ; brew install tesseract")

    full_text = ""
    for p in image_paths:
        try:
            img = Image.open(p)
            # preprocessing simpel: grayscale
            if img.mode != "L":
                img = img.convert("L")
            text = pytesseract.image_to_string(img, lang="ind+eng", config="--psm 6")
            full_text += "\n" + text
        except Exception as e:
            full_text += f"\n[OCR_GAGAL {p.name}: {e}]"
    return full_text

def extract_local_auto(image_paths: List[Path], use_ollama: bool = True, ollama_model: str = "llava") -> List[Dict[str, Any]]:
    """
    Coba Ollama dulu (vision), jika gagal fallback ke Tesseract OCR + parser B/S/K.
    Semua 100% localhost, tanpa API key.
    """
    if use_ollama:
        try:
            return extract_with_ollama(image_paths, model=ollama_model)
        except Exception as e:
            print(f"[local] Ollama gagal: {e} -> fallback Tesseract")
    # fallback tesseract
    try:
        raw = extract_with_tesseract(image_paths)
        if raw.strip():
            return extract_offline_fallback(raw)
    except Exception as e:
        print(f"[local] Tesseract gagal: {e}")
    # terakhir: return empty agar user paste manual
    raise RuntimeError("OCR lokal belum menghasilkan teks. Silakan pakai 'Paste Transkrip Manual' di Tab 1.")
