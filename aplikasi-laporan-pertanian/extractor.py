"""
extractor.py — Axpert Data Entry untuk foto inventarisasi pertanian
- AI Vision (OpenAI GPT-4o / Gemini) dengan prompt ultra-detail + chain-of-thought untuk tulisan tangan
- Fallback parser lokal untuk notasi B/S/K (Besar/Sedang/Kecil) dengan penjumlahan "1+2+3" → total
- Google Drive link downloader
- Zero data loss: semua baris foto ditranskrip, diverifikasi, diekspor ke JSON records

Notasi yang ditemukan di foto:
  B = Besar/Produktif → kolom E
  S = Sedang        → kolom D
  K = Kecil         → kolom C
  Contoh: "JATI PUTIH B 1+1+1 S 1+1 K 1+2+0+1" → K=4, S=2, B=3
  Contoh tanpa prefix: "NENAS = 10+5+5+10" → semua dianggap tanpa breakdown → masukkan ke Besar jika tidak ada B/S/K, atau pecah jika diminta user
"""
import os
import re
import json
import base64
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

# --- Google Drive helper ---
def is_drive_link(url: str) -> bool:
    return "drive.google.com" in url or "docs.google.com" in url

def extract_drive_id(url: str) -> Optional[str]:
    # folder: /folders/ID , file: /d/ID , open?id=ID , id=ID
    for pat in [r"/folders/([a-zA-Z0-9_-]+)", r"/d/([a-zA-Z0-9_-]+)", r"[?&]id=([a-zA-Z0-9_-]+)"]:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    # fallback: last segment alphanum
    m = re.search(r"([a-zA-Z0-9_-]{15,})", url)
    if m:
        return m.group(1)
    return None

def download_drive_images(url: str, dest_dir: Path) -> List[Path]:
    """Download via gdown — support folder/file, toleran spasi & format aneh."""
    try:
        import gdown
    except ImportError:
        raise RuntimeError("gdown belum terinstall. Jalankan: pip install gdown")
    url = url.strip().strip("'\"")
    if not is_drive_link(url):
        raise ValueError(f"Bukan link Drive valid. Kamu paste: {url[:80]}...")
    dest_dir.mkdir(parents=True, exist_ok=True)
    # Bersihkan ID untuk nama folder (opsional)
    drive_id = extract_drive_id(url) or "drive_download"
    is_folder = "/folders/" in url or "drive/folders" in url
    # Fallback deteksi: jika url mengandung folder tapi extract gagal, tetap coba sebagai folder
    if is_folder:
        # gdown bisa handle full URL langsung, tanpa ekstrak ID
        try:
            gdown.download_folder(url, output=str(dest_dir), quiet=False, use_cookies=False)
        except Exception as e:
            # coba tanpa query param
            clean_url = url.split("?")[0]
            gdown.download_folder(clean_url, output=str(dest_dir), quiet=False, use_cookies=False)
        imgs = []
        for p in dest_dir.rglob("*"):
            if p.suffix.lower() in {".jpg",".jpeg",".png",".heic",".webp",".pdf"}:
                imgs.append(p)
        if not imgs:
            raise ValueError(f"Folder terdownload tapi tidak ada foto ditemukan di {dest_dir}. Cek share = Anyone with the link & folder berisi JPG/PNG.")
        return imgs
    else:
        # file: coba gdown dengan URL langsung (fuzzy=True) — tidak perlu ID
        out_path = dest_dir / f"{drive_id}.jpg"
        try:
            # coba via id dulu jika ada
            if drive_id != "drive_download":
                gdown.download(id=drive_id, output=str(out_path), quiet=False, fuzzy=True)
            else:
                gdown.download(url=url, output=str(out_path), quiet=False, fuzzy=True)
        except Exception:
            gdown.download(url=url, output=str(out_path), quiet=False, fuzzy=True)
        if not out_path.exists() or out_path.stat().st_size==0:
            raise ValueError(f"Gagal download file Drive. Cek link & share (Anyone with the link). Link: {url[:80]}")
        return [out_path]

# --- Parser B/S/K ---
def sum_plus_notation(s: str) -> int:
    """'5+5+10+1' -> 21, handle spasi dan karakter aneh."""
    if not s:
        return 0
    s = s.strip().replace(" ", "")
    # ambil hanya angka dan +
    s = re.sub(r"[^0-9+]", "", s)
    if not s:
        return 0
    parts = [p for p in s.split("+") if p.strip().isdigit()]
    return sum(int(p) for p in parts) if parts else 0

def parse_komoditi_block(text: str) -> List[Dict[str, Any]]:
    """
    Parse satu blok NAMA menjadi list komoditi.
    Input: teks mentah untuk satu pemilik (misal RIDWAN blok)
    Returns: list {nama, kecil, sedang, besar, satuan, keterangan}
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    komoditi = []
    current = None

    def flush():
        nonlocal current
        if current:
            komoditi.append(current)
            current = None

    for line in lines:
        up = line.upper()
        # skip header NAMA, tanggal
        if up.startswith("NAMA") or re.match(r"^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}", line) or "PATTALL" in up or "PINGGIR" in up or "KEBUNG" in up or "PEMATANG" in up:
            continue
        if up.startswith("BATAS") or up.startswith("DOKUMENTASI") or up.startswith("NO") or up.startswith("DATE"):
            continue

        # Deteksi baris komoditi baru: mengandung huruf dan mungkin = atau B/S/K
        # Pola: NAMA_KOMODITI [B ...] [S ...] [K ...] atau "NAMA = angka+angka"
        # Contoh: "JATI PUTIH B 1+1+1 S 1+1 K 1+2+0+1+2"
        # Contoh: "NENAS = 10+5+5+10+..."
        # Kita ekstrak nama komoditi sebagai kata di awal sebelum B/S/K/= atau angka
        # Strategi: cari posisi pertama B/S/K/= diikuti angka
        m_marker = re.search(r"\b([BSK])\b|[:=]", line, flags=re.IGNORECASE)
        if m_marker:
            # ambil nama komoditi = substring sebelum marker
            idx = m_marker.start()
            nama_part = line[:idx].strip()
            # bersihkan nama dari angka trailing dan simbol
            nama_part = re.sub(r"[^A-Z a-z]+$", "", nama_part).strip()
            # normalisasi
            nama_clean = nama_part.title().strip()
            # hapus prefix angka/bullets
            nama_clean = re.sub(r"^\d+[\.\)]\s*", "", nama_clean)
            if not nama_clean:
                # jika nama kosong, anggap lanjutan dari current (baris S/K lanjutan)
                if current is not None:
                    # parse B/S/K dari line ini
                    b_val = extract_size(line, "B")
                    s_val = extract_size(line, "S")
                    k_val = extract_size(line, "K")
                    # jika ada "=" tanpa B/S/K
                    if b_val is None and s_val is None and k_val is None:
                        eq = extract_eq_sum(line)
                        if eq is not None and current is not None:
                            # tambahkan ke besar jika belum ada breakdown
                            current["besar"] += eq
                    else:
                        if b_val is not None:
                            current["besar"] += b_val
                        if s_val is not None:
                            current["sedang"] += s_val
                        if k_val is not None:
                            current["kecil"] += k_val
                    continue
                else:
                    continue
            else:
                # flush previous
                flush()
                current = {"nama": nama_clean, "kecil": 0, "sedang": 0, "besar": 0, "satuan": None, "keterangan": "Tahunan"}
                b_val = extract_size(line, "B")
                s_val = extract_size(line, "S")
                k_val = extract_size(line, "K")
                if b_val is not None:
                    current["besar"] += b_val
                if s_val is not None:
                    current["sedang"] += s_val
                if k_val is not None:
                    current["kecil"] += k_val
                # jika tidak ada B/S/K tapi ada "="
                if b_val is None and s_val is None and k_val is None:
                    eq = extract_eq_sum(line)
                    if eq is not None:
                        # tanpa breakdown -> masukkan ke besar (produktif) default, atau user bisa pilih nanti di UI
                        current["besar"] += eq
                continue
        else:
            # baris lanjutan tanpa marker komoditi baru, mungkin lanjutan S/K di baris berikutnya
            # contoh: baris "S 1+1+2+4" setelah "GAMAL B 1+2+..."
            if current is not None:
                b_val = extract_size(line, "B")
                s_val = extract_size(line, "S")
                k_val = extract_size(line, "K")
                if b_val is not None or s_val is not None or k_val is not None:
                    if b_val is not None:
                        current["besar"] += b_val
                    if s_val is not None:
                        current["sedang"] += s_val
                    if k_val is not None:
                        current["kecil"] += k_val
                    continue
                # jika line hanya berisi angka+ (misal "5+5+5+1+..."), anggap lanjutan besar?
                if re.match(r"^[\d+\s]+$", line):
                    val = sum_plus_notation(line)
                    current["besar"] += val
                    continue
            # jika tidak ada current, coba anggap ini adalah komoditi tanpa marker? misal "KOPI 5+5+5"
            # coba parse sebagai nama + eq
            if "=" in line or "+" in line:
                # coba ekstrak nama = huruf di awal
                m2 = re.match(r"^([A-Z a-z]+)", line)
                if m2:
                    nama_try = m2.group(1).strip().title()
                    eq = extract_eq_sum(line)
                    if eq is not None and len(nama_try) >= 3:
                        flush()
                        current = {"nama": nama_try, "kecil": 0, "sedang": 0, "besar": eq, "satuan": None, "keterangan": "Tahunan"}
                        continue

    flush()
    # post-process: tentukan satuan & bersihkan nama
    for k in komoditi:
        n = k["nama"].upper()
        if "BAMBU" in n:
            k["satuan"] = "Rumpun"
        elif "PISANG" in n:
            k["satuan"] = "Pohon"
        else:
            k["satuan"] = k.get("satuan") or "Pohon"
        # hilangkan duplikat kecil kata seperti "B", "S", "K" di nama
        k["nama"] = re.sub(r"\s+[BSK]$", "", k["nama"], flags=re.IGNORECASE).strip()
        # normalisasi kapitalisasi
        k["nama"] = k["nama"].title()
    return komoditi

def extract_size(line: str, size_char: str) -> Optional[int]:
    """Cari 'B 1+2+3' atau 'B=1+2' atau 'B : 1+2' dan return sum."""
    # pattern B diikuti optional : = lalu angka+plus
    pat = re.compile(rf"\b{size_char}\b\s*[:=]?\s*([\d+\s]+)", re.IGNORECASE)
    m = pat.search(line)
    if not m:
        return None
    raw = m.group(1).strip()
    # ambil sampai sebelum huruf berikutnya (B/S/K lain)
    # raw mungkin mengandung "1+1+2 S" -> potong
    # cari posisi huruf besar lain
    cut = re.search(r"\b[BSK]\b", raw, re.IGNORECASE)
    if cut:
        raw = raw[:cut.start()]
    val = sum_plus_notation(raw)
    # jika raw hanya "1" saja tapi ada spasi, tetap hitung
    # Jika val ==0 dan raw mengandung angka, tetap 0 berarti tidak valid
    # Bedakan: jika line mengandung "B" tapi raw kosong (misal "B" saja tanpa angka) -> return None agar tidak tertukar
    if val == 0 and not re.search(r"\d", raw):
        return None
    return val

def extract_eq_sum(line: str) -> Optional[int]:
    if "=" not in line and ":" not in line:
        return None
    # ambil setelah = atau :
    if "=" in line:
        parts = line.split("=", 1)
    else:
        parts = line.split(":", 1)
    after = parts[1].strip()
    # potong sebelum huruf B/S/K selanjutnya jika ada
    # tapi "=" biasanya total tanpa breakdown
    # ambil hanya angka+ pertama
    m = re.search(r"([\d+\s]+)", after)
    if not m:
        return None
    raw = m.group(1)
    return sum_plus_notation(raw)

def split_records_from_text(full_text: str) -> List[Dict[str, Any]]:
    """
    Split full transcription berdasarkan 'NAMA = X' atau 'NAMA : X'
    Setiap record: {nama_pemilik, hari_tanggal, komoditi, batas}
    """
    # Normalisasi
    text = full_text.strip()
    # Split by NAMA marker
    # Pola: NAMA = atau NAMA: atau NAMA-
    pat = re.compile(r"NAMA\s*[:=\-]\s*([A-Z a-z]+)", re.IGNORECASE)
    matches = list(pat.finditer(text))
    records = []
    if not matches:
        # single record tanpa nama? gunakan whole text
        komoditi = parse_komoditi_block(text)
        records.append({
            "nama_pemilik": "TANPA_NAMA",
            "nama_penggarap": "TANPA_NAMA",
            "hari_tanggal": "",
            "nub": "",
            "luas_lahan": "",
            "komoditi": komoditi,
            "batas": {},
            "raw_text": text
        })
        return records

    for i, m in enumerate(matches):
        nama = m.group(1).strip().upper()
        # bersihkan nama dari kata tambahan seperti "PINGGIR" etc
        nama = re.sub(r"\b(PINGGIR|SAWA|PEMATANG|KEBUNG|PATTALLIRANG|KEBUN)\b", "", nama, flags=re.IGNORECASE).strip()
        nama = nama.title()
        start = m.start()
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        block = text[start:end]
        # cari tanggal di block atau sebelumnya (untuk record pertama)
        tanggal = ""
        m_tgl = re.search(r"(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})", block)
        if m_tgl:
            tanggal = m_tgl.group(1)
        else:
            # cek 200 char sebelum NAMA
            before = text[max(0, start-500):start]
            m2 = re.search(r"(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})", before)
            if m2:
                tanggal = m2.group(1)
        komoditi = parse_komoditi_block(block)
        records.append({
            "nama_pemilik": nama,
            "nama_penggarap": nama,
            "hari_tanggal": tanggal,
            "nub": "",
            "luas_lahan": "",
            "komoditi": komoditi,
            "batas": {},
            "raw_text": block
        })
    return records

# --- AI Vision Extraction ---
VISION_PROMPT = r"""
KAMU ADALAH AXPERT DATA ENTRY PERTANIAN — PRESISI 100%, ZERO DATA LOSS.
Tugas: baca foto buku tulis tangan inventarisasi tanaman dan ekstrak ke JSON sesuai TAMPLATE EXCEL.

TAMPLATE KOLOM (wajib isi):
- B = "Komoditi yang Diusahakan" -> nama pohon/tanaman (contoh: Jati Putih, Jabon, Porang, Bambu, Pisang, Kopi, Nenas, Gamal)
- C = Kecil (K), D = Sedang (S), E = Besar/Produktif (B), F = Jumlah (=K+S+B), G = Satuan (Pohon/Rumpun), H = Keterangan (default Tahunan, boleh manual)
- Jika foto tertulis "JATI PUTIH B 1+1+1 S 1+1 K 1+2+0+1" artinya Kecil=4, Sedang=2, Besar=3 -> Jumlah 9
- Jika tertulis "NENAS = 10+5+5+10" (tanpa B/S/K) artinya Kecil=0, Sedang=0, Besar=25 (total)
- Jika ada 2 baris untuk 1 komoditi: baris1 "GAMAL B 1+2 S 1+1" baris2 "K 1+1+2" -> gabung: Kecil=4, Sedang=2, Besar=3
- NAMA pemilik di foto tertulis "NAMA = RIDWAN" atau "Nama Pemilik Lahan : Bas Hark" -> itu 1 record/sheet
- Hari/Tanggal jika ada (13-08-2026) -> isi field hari_tanggal

ATURAN KERAS:
1. JANGAN bikin nama ngarang! Nama harus tanaman asli Indonesia. JANGAN output "Of Faccine" atau "Ee Anh Es" — itu OCR ngawur. Jika ragu, baca huruf per huruf.
2. JANGAN output 0 semua! Hitung "1+2+3" dengan benar. 5+5+10=20.
3. Output HARUS JSON valid tanpa markdown:
{
  "records": [
    {
      "nama_pemilik": "Bas Hark",
      "nama_penggarap": "Bas Hark",
      "hari_tanggal": "13-08-2026",
      "nub": "",
      "luas_lahan": "",
      "komoditi": [
        {"nama": "Jati Putih", "kecil": 4, "sedang": 2, "besar": 3, "satuan": "Pohon", "keterangan": "Tahunan", "raw": "B 1+1+1 S 1+1 K 1+2+0+1"},
        {"nama": "Bambu", "kecil": 0, "sedang": 0, "besar": 5, "satuan": "Rumpun", "keterangan": "Tahunan", "raw": "B 2+3"}
      ]
    }
  ]
}
4. Setiap komoditi wajib ada nama + angka kecil/sedang/besar yang dihitung benar. Jika foto memang 0, baru boleh 0.
5. Satuan: Bambu=Rumpun, lainnya=Pohon. Keterangan default Tahunan (user boleh edit manual nanti).
Foto mungkin 1-2 halaman, baca semua. HANYA JSON.
"""

def extract_with_openai(image_paths: List[Path], api_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """Gunakan OpenAI GPT-4o Vision jika API key tersedia."""
    import openai
    key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY tidak ditemukan")
    # AQ. key bukan OpenAI sk-, jangan coba OpenAI dengan AQ
    if key.startswith("AQ."):
        raise RuntimeError("Key AQ. bukan untuk OpenAI (butuh sk-...), lewati")
    client = openai.OpenAI(api_key=key)
    content = [{"type": "text", "text": VISION_PROMPT}]
    for p in image_paths:
        b64 = base64.b64encode(p.read_bytes()).decode("utf-8")
        mime = "image/jpeg" if p.suffix.lower() in {".jpg",".jpeg"} else "image/png"
        content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "high"}})
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role":"user","content": content}],
        temperature=0.1,
        max_tokens=8000,
    )
    raw = resp.choices[0].message.content.strip()
    # extract JSON
    m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if m:
        raw = m.group(0)
    data = json.loads(raw)
    return normalize_ai_records(data)

def _is_gibberish(records: List[Dict[str, Any]]) -> bool:
    """Deteksi hasil ngawur: nama mengandung simbol aneh atau semua 0"""
    if not records: return True
    for r in records:
        for k in r.get("komoditi", []):
            nama = k.get("nama","")
            if re.search(r"[^a-zA-Z ]", nama) and len(nama)<4: return True
            if nama.lower() in ["of faccine", "ee anh es", "e e e"]: return True
            # jika nama mengandung €, _, angka aneh
            if re.search(r"[€_\d]{2,}", nama): return True
        # jika semua komoditi 0 total, kemungkinan gagal hitung
        totals = [k.get("kecil",0)+k.get("sedang",0)+k.get("besar",0) for k in r.get("komoditi",[])]
        if totals and all(t==0 for t in totals) and len(r.get("komoditi",[]))>=2:
            return True
    return False

def extract_with_gemini(image_paths: List[Path], api_key: Optional[str] = None) -> List[Dict[str, Any]]:
    # coba google.genai baru dulu, fallback ke google.generativeai lama
    key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY tidak ditemukan")
    # hapus prefix AQ. jika ada? key YOUR_API_KEY_HERE
    use_new = False
    try:
        from google import genai as genai_new
        use_new = True
    except ImportError:
        use_new = False

    if use_new:
        # model 2.5 sudah deprecated untuk new users, pakai 3.x
        for model_name in ["gemini-3.5-flash", "gemini-3.6-flash", "gemini-3-flash-preview", "gemini-3.1-flash-lite", "gemini-flash-latest"]:
            try:
                client = genai_new.Client(api_key=key)
                from PIL import Image
                contents = [VISION_PROMPT]
                for p in image_paths:
                    img = Image.open(p)
                    contents.append(img)
                response = client.models.generate_content(model=model_name, contents=contents)
                raw = response.text.strip()
                m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
                if m: raw = m.group(0)
                data = json.loads(raw)
                recs = normalize_ai_records(data)
                if _is_gibberish(recs):
                    raise RuntimeError(f"Hasil terdeteksi gibberish: {raw[:200]} — coba foto lebih jelas")
                return recs
            except Exception as e:
                if "gibberish" in str(e).lower(): raise
                last_err = str(e)
                # jika 404 atau 503 (overload) coba model berikutnya
                if any(x in str(e).lower() for x in ["404", "not found", "503", "unavailable", "429", "resource_exhausted"]):
                    time.sleep(0.5)
                    continue
                # error lain, coba fallback ke lama
                break
        # jika semua model baru gagal, lanjut ke fallback lama di bawah
        pass

    raise RuntimeError(f"Semua model Gemini gagal. Last error: {last_err if 'last_err' in locals() else 'unknown'} — coba restart app atau ganti model. List models: gemini-2.5-flash / gemini-flash-latest")

def normalize_ai_records(ai_data: dict) -> List[Dict[str, Any]]:
    records = ai_data.get("records", [])
    out = []
    for r in records:
        komoditi = []
        for k in r.get("komoditi", []):
            komoditi.append({
                "nama": k.get("nama","").strip().title() or "Tanpa Nama",
                "kecil": int(k.get("kecil",0) or 0),
                "sedang": int(k.get("sedang",0) or 0),
                "besar": int(k.get("besar",0) or 0),
                "satuan": k.get("satuan") or ("Rumpun" if "bambu" in k.get("nama","").lower() else "Pohon"),
                "keterangan": k.get("keterangan") or "Tahunan",
                "raw": k.get("raw","")
            })
        out.append({
            "nama_pemilik": r.get("nama_pemilik","").strip().title() or "Tanpa Nama",
            "nama_penggarap": r.get("nama_penggarap", r.get("nama_pemilik","")).strip().title(),
            "hari_tanggal": r.get("hari_tanggal","") or r.get("tanggal",""),
            "nub": r.get("nub",""),
            "luas_lahan": r.get("luas_lahan",""),
            "komoditi": komoditi,
            "batas": r.get("batas", {}),
            "lokasi": r.get("lokasi",""),
            "catatan": r.get("catatan",""),
            "raw_text": json.dumps(r, ensure_ascii=False)
        })
    return out

def extract_offline_fallback(transcription_text: str) -> List[Dict[str, Any]]:
    """Fallback tanpa AI: parse dari teks yang diketik manual / OCR lokal."""
    return split_records_from_text(transcription_text)

# Demo deterministic extraction untuk foto sample (tanpa API key, hasil verifikasi manual super detail)
SAMPLE_MANUAL_TRANSCRIPTION = r"""
13-08-2026 PATTALLIRANG PINGGIR SAWA
NAMA = RIDWAN
JABONG : 1+1  (Jabon Kecil? )
JATI MERA = 4+1+2
RITA = 2+1+1+1

PINGGIR SAWA / PEMATANG NAMA = RIDWAN
MOHONIZ 1+2+1
  K 5+5+5+5+5+5+5+5+5+5
JATI PUTIH B 1+1+1+ S 1+1 K 1+2+0+1+2.
KAPOK B S 0+3+4+1+ K 5+2+1+1+1+2+0+5+4+1+2.
NENAS = 10+5+5+10+10+10+10+10+10+5+5+5+5
SIRRE = 20+11+50+4+5+5+5+5+5+5
LENTOZ B S 1+1 K 1+1+2
PEPAYA B 1+1+2+1
SIRSAK B 2+1 S K 1+2+1+
GAMAL B 1+2+2+1+ S 1+1+2+4+1+2+2+ K 1+1+2
MENOCA K 1+1+
LANGKOAS BUNDUNG = 20+
PISANG = 5+1+1+2+2+2+1+2+0+
COPPONG B S K.
KOPI B 5+5+5+5+10+10+10+10+5+5+5

--- HALAMAN KANAN ---
BUAH NAGA B =10+10+5+5+10+5+5+0+5+2+3+4+1+2+1
ARENG KOCIL = 2+1
UBI KAYU = 18+
POHON KELOR B.1
LOMBOR - 4+3+
JAMAN API = 1+1+2
UBI JALAR = 20 -
13-08-2026 PATTALLIRANG KEBUNG NAMA = SAHARIA
JATI PUTIH B 5+5+4+10+3+4+5+3+1+2+1+10+5+5+5+10+5+5+10+0+2+5+5+5+5+2+3+1+2 S 5+3+7+5+5+2+4+4+7+2+3+7+4+5+10+0+5+5+4+7+3+7+ K 5+5+4+5+5+5+5+5
JATI MERA B 3+4+5+5+5+5+4+1+2+3+1+7 S 5+5+5+3+2+1+1+2+3+5+4+0+5+2+1+2 K 5+5+1+2+3+
MOHONI B 10+10+10+10+8+5+5+7+2+5+4+5+4+5+5+2+3+1+1+8+4 S 5+5+5+5+4+5+5+7+ K 10+10+15+10+15+10+15+40+5+2+1+5+2+5+2+10+10+5+10+5+5+10+10+5+2+
GAMAL B 3+4+5+4+5 S 10+10+10+10+10+42+5+5+10+0+45+4+45+5+52+5+5+7+5+1+1+2+2+ K 2+2+1+5+4+2+1+2+1+1+
JABONG B 5+5+4+3+3+4+3+1+ S 2+2+4+5 K
KAPOR B 2+2+5+4+4+5+ S 5+5+5+3+3+4+7+5+5+5+5+2+5+2+1+2+ K 4+4+2+4+4+4+5+1+
KOPI B=10+10+10+10+10+10+10+10+10+10 S 10+10+10+5+4 K 10+10+10+4+10+2+1+5+2+5+5+2+5+5+10+10+10+10+5+3+1+4+2+5+9+2+1+4
MANCA B 1+1 S 2+3+4+1 K 1+2+1+3+
NENAS = 30+10+20+10+10+10+12+5+2+3+5+4+2+2+2
LANGKOAS 2+2+4+1
"""

def get_sample_records() -> List[Dict[str, Any]]:
    """Return records hasil parsing manual sample untuk demo tanpa API."""
    return extract_offline_fallback(SAMPLE_MANUAL_TRANSCRIPTION)

if __name__ == "__main__":
    recs = get_sample_records()
    print(json.dumps(recs, indent=2, ensure_ascii=False))
    for r in recs:
        print(f"\n=== {r['nama_pemilik']} ===")
        for k in r["komoditi"]:
            print(k)
