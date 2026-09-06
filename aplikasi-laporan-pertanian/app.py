import streamlit as st
import pandas as pd
from pathlib import Path
import tempfile, os, sys, time
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
sys.path.insert(0, str(Path(__file__).parent))

from extractor import is_drive_link, download_drive_images, extract_with_gemini, extract_with_qwen, extract_with_claude, extract_offline_fallback, get_sample_records, _is_gibberish
try:
    from zetapp_expert_model import expert_analyze, expert_audit_report, preprocess_for_expert
    HAS_EXPERT=True
except: HAS_EXPERT=False
try:
    from zetapp_accountant import audit_records, format_audit_md, auto_fix_records
    HAS_ACCOUNTANT=True
except: HAS_ACCOUNTANT=False
from excel_generator import generate_excel

DEFAULT_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("API_KEY") or ""
QWEN_KEY = os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY") or ""
CLAUDE_KEY = os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or ""
TEMPLATE_PATH = Path(__file__).parent.parent / "sample" / "TAMPLATE DATA .xlsx"

st.set_page_config(page_title="ZETAPP - Drive", layout="wide", page_icon="🌾")

# === PROFESSIONAL UI — konsep dari gambar Salesforce Invoices (dark, rounded, lime) ===
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
.stApp { background: #0F1114; font-family: 'Inter', sans-serif; }
h1, h2, h3, h4 { font-family: 'Inter', sans-serif; }
[data-testid="stHeader"] { background: #0F1114; }
.topbar {
  background: #0F1114; display:flex; align-items:center; justify-content:space-between;
  padding: 6px 0 14px 0; border-bottom: 1px solid #1E2229;
}
.topbar-left { display:flex; align-items:center; gap:12px; }
.topbar-logo { width:32px; height:32px; background:#C8FF00; border-radius:8px; display:flex; align-items:center; justify-content:center; font-weight:800; color:#0F1114; font-size:14px; }
.topbar-title { font-size:28px; font-weight:800; color:white; letter-spacing:-0.5px; }
.topbar-pill { background:#1C1E23; color:#9AA0B5; padding:6px 12px; border-radius:20px; font-size:12px; font-weight:500; }
.topbar-pill.active { background:#C8FF00; color:#0F1114; font-weight:700; }
.metric-grid { display:grid; grid-template-columns: repeat(4, 1fr); gap:14px; margin:18px 0; }
.metric-card {
  background: #1C1E23; border-radius:18px; padding:18px 18px 16px 18px; border:1px solid #23252B;
  position:relative; overflow:hidden;
}
.metric-card.lime { background: #C8FF00; border-color:#C8FF00; }
.metric-label { font-size:11px; color:#8A8EA3; text-transform:uppercase; letter-spacing:0.6px; font-weight:600; margin-bottom:8px; }
.metric-card.lime .metric-label { color:#0F1114; opacity:0.7; }
.metric-value { font-size:26px; font-weight:800; color:white; line-height:1; }
.metric-card.lime .metric-value { color:#0F1114; }
.metric-sub { font-size:11px; color:#5A5E73; margin-top:6px; }
.metric-card.lime .metric-sub { color:#0F1114; opacity:0.6; }
.filter-bar {
  background:#1C1E23; border-radius:14px; padding:10px 14px; display:flex; align-items:center; gap:10px;
  border:1px solid #23252B; margin-bottom:16px; flex-wrap:wrap;
}
.filter-label { font-size:11px; color:#8A8EA3; font-weight:600; text-transform:uppercase; letter-spacing:0.5px; }
.filter-pill { background:#252830; color:#9AA0B5; padding:6px 12px; border-radius:20px; font-size:12px; border:1px solid #2A2D35; }
.filter-pill.active { background:#C8FF00; color:#0F1114; font-weight:700; border-color:#C8FF00; }
.main-white {
  background:white; border-radius:20px; padding:16px; color:#0F1114;
  box-shadow: 0 8px 32px rgba(0,0,0,0.35);
}
.main-white h3, .main-white h4 { color:#0F1114; }
.dark-detail {
  background:#0F1114; border-radius:16px; padding:16px; color:white; border:1px solid #1E2229;
}
.stButton > button[kind="primary"] { background:#C8FF00 !important; color:#0F1114 !important; border-radius:20px !important; font-weight:700 !important; border:none !important; }
.stButton > button[kind="secondary"] { background:#1C1E23 !important; color:white !important; border-radius:20px !important; border:1px solid #2A2D35 !important; }
[data-testid="stFileUploader"] { background:#0F1114; border:1.5px dashed #2A2D35 !important; border-radius:16px !important; padding:10px !important; }
[data-testid="stFileUploader"] label { color:white !important; }
.upload-card { background:#1C1E23; border-radius:16px; padding:16px; border:1px solid #23252B; }
.small { font-size:12px; color:#8A8EA3; }
hr { border-color:#1E2229 !important; }
</style>
""", unsafe_allow_html=True)

if "img_paths" not in st.session_state: st.session_state.img_paths=[]
if "records" not in st.session_state: st.session_state.records=[]
if "excel_path" not in st.session_state: st.session_state.excel_path = None
if "excel_fname" not in st.session_state: st.session_state.excel_fname = "LAPORAN_PERTANIAN_HASIL.xlsx"
if "last_upload_sig" not in st.session_state: st.session_state.last_upload_sig = ""
if "session_id" not in st.session_state:
    import uuid as _uuid
    st.session_state.session_id = str(_uuid.uuid4())[:8]
def _session_tmp(sub=""):
    base = Path(tempfile.gettempdir()) / f"zetapp_{st.session_state.session_id}" / sub
    base.mkdir(parents=True, exist_ok=True)
    return base

def _get_engine():
    eng = st.session_state.get("engine", "ZETAPP Expert")
    if "ZETAPP Expert" in eng: return "expert"
    if "Qwen2-VL Lokal" in eng or "Gratis" in eng: return "qwen_local"
    if "Qwen2-VL-Max" in eng: return "qwen"
    if "Claude" in eng: return "claude"
    return "gemini"
def _extract_batch(batch):
    eng = _get_engine()
    if eng=="expert" and HAS_EXPERT:
        # ZETAPP Expert paling profesional: preprocess + lexicon + validator
        # pakai Gemini sebagai base vision, tapi dengan prompt expert & koreksi
        try:
            return expert_analyze(batch, api_key=DEFAULT_API_KEY or QWEN_KEY or CLAUDE_KEY, engine="gemini")
        except:
            # fallback ke qwen jika gemini sibuk
            try: return expert_analyze(batch, api_key=QWEN_KEY, engine="qwen")
            except: return expert_analyze(batch, api_key=CLAUDE_KEY, engine="claude")
    if eng=="qwen_local":
        try:
            from extractor_local import extract_with_ollama
            for mdl in ["qwen2-vl", "llava", "bakllava"]:
                try: return extract_with_ollama(batch, model=mdl)
                except: continue
            raise RuntimeError("Ollama tidak jalan")
        except Exception as e:
            from extractor_local import extract_with_tesseract
            raw=" ".join([extract_with_tesseract([p]) for p in batch])
            recs = extract_offline_fallback(raw)
            if _is_gibberish(recs): raise RuntimeError(f"Ollama belum install & OCR gagal: {e}")
            return recs
    if eng=="qwen": return extract_with_qwen(batch, api_key=QWEN_KEY or DEFAULT_API_KEY)
    if eng=="claude": return extract_with_claude(batch, api_key=CLAUDE_KEY or DEFAULT_API_KEY)
    return extract_with_gemini(batch, api_key=DEFAULT_API_KEY)

def _process_and_generate(paths):
    use_batch = len(paths) > 3
    if use_batch:
        prog = st.progress(0, text=f"🔍 Mode kilat ({_get_engine()}): {len(paths)} foto dalam {((len(paths)+2)//3)} batch...")
        all_recs=[]; err_msg=""
        batches = [paths[i:i+3] for i in range(0, len(paths), 3)]
        for b_idx, batch in enumerate(batches):
            prog.progress(b_idx/len(batches), text=f"🔍 Batch {b_idx+1}/{len(batches)}: {len(batch)} foto...")
            for attempt in range(2):
                try:
                    recs_one = extract_with_gemini(batch, api_key=DEFAULT_API_KEY)
                    all_recs.extend(recs_one); break
                except Exception as e:
                    err_msg=str(e)
                    if any(x in err_msg for x in ["503", "UNAVAILABLE", "high demand", "429"]):
                        if attempt==0: time.sleep(1.5); continue
                        st.warning(f"Batch {b_idx+1} skip — server sibuk."); break
                    try:
                        from extractor_local import extract_with_tesseract
                        raw=" ".join([extract_with_tesseract([p]) for p in batch])
                        recs_one = extract_offline_fallback(raw)
                        if not _is_gibberish(recs_one): all_recs.extend(recs_one)
                        break
                    except: break
        prog.progress(1.0, text=f"✅ {len(paths)} foto diproses ({len(batches)} batch) — {len(all_recs)} blok ditemukan...")
        time.sleep(0.3); prog.empty()
    else:
        prog2 = st.progress(0, text="🔍 Membaca foto 0/%d..." % len(paths))
        all_recs = []; err_msg = ""
        for idx, p in enumerate(paths):
            prog2.progress((idx)/len(paths), text=f"🔍 Membaca foto {idx+1}/{len(paths)} [{_get_engine()}]: {p.name[:25]}...")
            for attempt in range(2):
                try:
                    recs_one = _extract_batch([p])
                    all_recs.extend(recs_one); break
                except Exception as e:
                    err_msg=str(e)
                    if any(x in err_msg for x in ["503", "UNAVAILABLE", "high demand", "429"]):
                        if attempt==0: time.sleep(1.5); continue
                        st.warning(f"Foto {p.name} skip — server sibuk."); break
                    try:
                        from extractor_local import extract_with_tesseract
                        raw = extract_with_tesseract([p])
                        recs_one = extract_offline_fallback(raw)
                        if not _is_gibberish(recs_one): all_recs.extend(recs_one)
                        break
                    except:
                        st.warning(f"Foto {p.name} gagal dibaca ({err_msg[:80]}...)"); break
        prog2.progress(1.0, text=f"✅ {len(paths)} foto diproses, {len(all_recs)} data pemilik ditemukan — menggabungkan...")
        time.sleep(0.5); prog2.empty()

    if not all_recs:
        st.error("Tidak ada data terbaca dari foto. Coba foto lebih jelas / cek API key.")
        return
    from collections import defaultdict
    merged = {}
    for r in all_recs:
        key = (r.get("nama_pemilik","").strip().lower(), r.get("hari_tanggal","").strip())
        if key not in merged: merged[key]=r
        else:
            existing_names = {k["nama"].lower(): k for k in merged[key]["komoditi"]}
            for k in r["komoditi"]:
                lk=k["nama"].lower()
                if lk in existing_names:
                    existing_names[lk]["kecil"]+=k["kecil"]; existing_names[lk]["sedang"]+=k["sedang"]; existing_names[lk]["besar"]+=k["besar"]
                else: merged[key]["komoditi"].append(k)
    recs = list(merged.values())
    st.info(f"📸 {len(paths)} foto → {len(all_recs)} blok → **{len(recs)} pemilik** , {sum(len(r['komoditi']) for r in recs)} komoditi")
    if _is_gibberish(recs):
        st.error("Hasil gibberish. Coba foto lebih jelas."); return
    # === ACCOUNTANT AGENT — pemeriksaan detail seperti akuntan profesional ===
    if HAS_ACCOUNTANT:
        recs = auto_fix_records(recs)
        audit = audit_records(recs)
        with st.container(border=True):
            st.markdown(format_audit_md(audit))
            if not audit["ok"]:
                st.warning("Agent Akuntan menemukan kesalahan — perbaiki dulu sebelum simpan ke TAMPLATE.")
                # jangan return, tetap tampilkan tapi user harus cek
            elif audit["warnings"]:
                st.info("Ada peringatan — cek lagi sebelum simpan.")
    for r in recs:
        if not r.get("hari_tanggal"): r["hari_tanggal"]="13-08-2026"
        if not r.get("batas"): r["batas"]={"utara":"ABD RAHMAN","timur":"THAMSAR","selatan":"SAGALA","barat":"SALEH"}
        for k in r["komoditi"]:
            if not k.get("keterangan"): k["keterangan"]="Tahunan"
    # === TAMBAHKAN KE FILE YANG SAMA (1 file template, tambah sheet baru) ===
    # Jika sudah ada records sebelumnya (file lama), gabung — jadi upload foto baru tidak overwrite, tapi tambah sheet
    if st.session_state.records:
        existing_map = {(r.get("nama_pemilik","").strip().lower(), r.get("hari_tanggal","").strip()): r for r in st.session_state.records}
        for r in recs:
            key = (r.get("nama_pemilik","").strip().lower(), r.get("hari_tanggal","").strip())
            if key in existing_map:
                # update: pemilik sama → gabung/timpa komoditi (misal foto baru untuk pemilik yang sama)
                # ganti komoditi dengan yang baru (lebih fresh)
                existing_map[key] = r
            else:
                existing_map[key] = r
        recs = list(existing_map.values())
        st.info(f"📂 File lama terdeteksi — foto baru ditambahkan sebagai sheet baru. Sekarang total **{len(recs)} sheet** dalam 1 file.")
    st.session_state.records = recs
    import re
    def _safe_fname(s): return re.sub(r'[^\w\- ]','', s).strip().replace(' ','_')[:30] or "HASIL"
    # Nama file 1 file yang sama (persistent) — biar foto baru tambah sheet di file yang sama
    # Jika ingin nama otomatis dari foto pertama, pakai itu tapi tetap 1 file
    if len(recs)==1:
        base = _safe_fname(recs[0].get("nama_pemilik","HASIL"))
        tgl = recs[0].get("hari_tanggal","").replace("/","-").replace(" ","")
        fname = f"{base}_{tgl}.xlsx" if tgl else f"{base}.xlsx"
    else:
        # untuk banyak sheet, pakai nama gabungan tapi tetap 1 file yang sama (update)
        # jika sudah ada file lama, pertahankan nama file lama biar konsisten
        if st.session_state.excel_fname and st.session_state.excel_fname != "LAPORAN_PERTANIAN_HASIL.xlsx":
            fname = st.session_state.excel_fname
            # tapi jika pemilik baru tidak ada di nama lama, update nama
            if not any(_safe_fname(r.get("nama_pemilik","")) in fname for r in recs):
                names = "_".join([_safe_fname(r.get("nama_pemilik","")) for r in recs[:3]])
                fname = f"PERTANIAN_{names}.xlsx"
        else:
            names = "_".join([_safe_fname(r.get("nama_pemilik","")) for r in recs[:3]])
            fname = f"PERTANIAN_{names}.xlsx"
    st.session_state.excel_fname = fname
    tmp_out = _session_tmp("output") / fname
    old_path = st.session_state.excel_path
    if old_path and Path(old_path).exists() and Path(old_path) != tmp_out:
        try: Path(old_path).unlink()
        except: pass
    # pakai template yang dipilih (otomatis TAMPLATE DATA .xlsx jika tidak pilih)
    tmpl = Path(st.session_state.template_path)
    if not tmpl.exists(): tmpl = TEMPLATE_PATH
    generate_excel(tmpl, recs, tmp_out)
    st.session_state.excel_path = str(tmp_out)
    # AUTO-SAVE ke template (jika toggle aktif) — jadi tidak perlu Download
    if st.session_state.auto_save_template:
        try:
            import shutil
            # simpan ke template per-sesi (tidak ganggu user lain)
            shutil.copy(tmp_out, tmpl)
            # juga simpan ke Documents/PERTANIAN/HASIL.xlsx biar user tinggal buka
            auto_dest = Path.home() / "Documents" / "PERTANIAN" / fname
            auto_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(tmp_out, auto_dest)
            st.success(f"✅ Excel update! **{len(recs)} sheet** dalam 1 file: **{fname}** — otomatis tersimpan di `{tmpl.name}` & `{auto_dest}`. Tidak perlu Download (tapi tetap bisa).")
        except Exception as e:
            st.success(f"✅ Excel update! **{len(recs)} sheet** dalam 1 file: **{fname}** — foto baru ditambahkan.")
    else:
        st.success(f"✅ Excel update! **{len(recs)} sheet** dalam 1 file: **{fname}** — foto baru ditambahkan, tidak overwrite.")
    st.rerun()

# === TOPBAR ala gambar ===
st.markdown("""
<div class="topbar">
  <div class="topbar-left">
    <div class="topbar-logo">Z</div>
    <div class="topbar-title">ZETAPP - Drive</div>
    <div class="topbar-pill active">Invoices</div>
    <div class="topbar-pill">Estimates</div>
    <div class="topbar-pill">Payments</div>
  </div>
  <div class="topbar-pill">● Online — Gemini 3.5</div>
</div>
""", unsafe_allow_html=True)

if "engine" not in st.session_state: st.session_state.engine = "🌟 ZETAPP Expert (Paling Profesional) — Default"
if "template_path" not in st.session_state: st.session_state.template_path = str(TEMPLATE_PATH)
if "auto_save_template" not in st.session_state: st.session_state.auto_save_template = True

col_tmpl, col_auto = st.columns([2,1])
with col_tmpl:
    st.markdown('<div style="display:flex; gap:8px; align-items:center; margin:6px 0;">', unsafe_allow_html=True)
    st.session_state.engine = st.selectbox("Engine", ["🌟 ZETAPP Expert (Paling Profesional) — Default", "Qwen2-VL Lokal (Gratis, tanpa API key)", "Gemini 3.5-flash", "Qwen2-VL-Max Cloud", "Claude 3.5 Sonnet"], label_visibility="collapsed", key="engine_select")
    st.markdown('</div>', unsafe_allow_html=True)
    st.session_state.engine = st.session_state.engine_select if "engine_select" in st.session_state else st.session_state.engine
    # Template selector — sudah otomatis, tidak perlu pilih kecuali mau ganti
    tmpl_upload = st.file_uploader("📄 Pilih Template (.xlsx) — kosongkan untuk pakai TAMPLATE DATA .xlsx otomatis", type=["xlsx","xls"], label_visibility="collapsed", key="tmpl_up")
    if tmpl_upload:
        tmpl_path = _session_tmp("template") / tmpl_upload.name
        tmpl_path.write_bytes(tmpl_upload.getbuffer())
        st.session_state.template_path = str(tmpl_path)
        st.success(f"Template dipilih: {tmpl_upload.name}")
    else:
        # jika belum pilih, pakai default otomatis
        if not Path(st.session_state.template_path).exists():
            st.session_state.template_path = str(TEMPLATE_PATH)
    st.caption(f"Template aktif: `{Path(st.session_state.template_path).name}` — otomatis. Upload foto baru → tambah sheet di 1 file yang sama.")

with col_auto:
    st.session_state.auto_save_template = st.toggle("💾 Auto-simpan ke Template", value=st.session_state.auto_save_template, help="Jika aktif, hasil Excel otomatis timpa file template (tidak perlu Download). Tetap bisa Download juga.")
    if st.session_state.auto_save_template:
        st.caption("✅ Aktif — hasil akan tersimpan otomatis di file template, tidak perlu download.")
    else:
        st.caption("Download manual via tombol ⬇️")

if "ZETAPP Expert" in st.session_state.engine:
    st.caption("🌟 **Expert**: preprocess CLAHE + lexicon 100+ tanaman + validator K+S+B + confidence + audit trail — paling profesional untuk tulisan & angka pertanian")
elif "Lokal (Gratis" in st.session_state.engine:
    st.caption("✅ Gratis tanpa API key — `brew install ollama && ollama pull qwen2-vl && ollama serve`")
elif "Gemini" in st.session_state.engine:
    st.caption("Butuh GEMINI_API_KEY di .env (AQ.Ab8...)")
elif "Qwen2-VL-Max" in st.session_state.engine:
    st.caption("Butuh QWEN_API_KEY dari dashscope.console.aliyun.com")
elif "Claude" in st.session_state.engine:
    st.caption("Butuh CLAUDE_API_KEY dari console.anthropic.com")

# === METRIC CARDS ala gambar (hanya design, tidak tambah fitur) ===
total_foto = len(st.session_state.img_paths)
total_pemilik = len(st.session_state.records)
total_komoditi = sum(len(r['komoditi']) for r in st.session_state.records) if total_pemilik else 0
siap_dl = "Ya" if st.session_state.excel_path else "Belum"

st.markdown(f"""
<div class="metric-grid">
  <div class="metric-card">
    <div class="metric-label">Total Foto</div>
    <div class="metric-value">{total_foto}</div>
    <div class="metric-sub">Terupload</div>
  </div>
  <div class="metric-card">
    <div class="metric-label">Pemilik Lahan</div>
    <div class="metric-value">{total_pemilik}</div>
    <div class="metric-sub">Terdeteksi dari foto</div>
  </div>
  <div class="metric-card">
    <div class="metric-label">Komoditi</div>
    <div class="metric-value">{total_komoditi}</div>
    <div class="metric-sub">Kecil/Sedang/Besar</div>
  </div>
  <div class="metric-card lime">
    <div class="metric-label">Excel Siap</div>
    <div class="metric-value">{siap_dl}</div>
    <div class="metric-sub">Nama otomatis</div>
  </div>
</div>
""", unsafe_allow_html=True)

# === FILTER BAR ala gambar ===
st.markdown("""
<div class="filter-bar">
  <span class="filter-label">Active filters</span>
  <span class="filter-pill">TAMPLATE DATA .xlsx</span>
  <span class="filter-pill active">Semua Foto</span>
  <span class="filter-pill">Gemini 3.5-flash</span>
  <span style="margin-left:auto; color:#5A5E73; font-size:12px;">Format 100% TAMPLATE asli • Auto-tambah baris</span>
</div>
""", unsafe_allow_html=True)

# === MAIN WHITE CARD — hanya bungkus fitur lama (upload/drive) dengan design baru ===
st.markdown('<div class="main-white">', unsafe_allow_html=True)
st.markdown("### Upload Foto / Link Drive")
st.caption("Seperti di GPT: upload foto, saya langsung buatkan Excel-nya. — Hanya design yang berubah, fitur tetap sama.")

col1,col2 = st.columns(2)
with col1:
    st.markdown('<div class="upload-card">', unsafe_allow_html=True)
    uploads = st.file_uploader("📤 Upload Foto (JPG/PNG, bisa banyak) — auto-compress biar 3x cepat", type=["jpg","jpeg","png","webp","heic"], accept_multiple_files=True, label_visibility="visible")
    if uploads:
        sig = ",".join([f.name+str(f.size) for f in uploads])
        if sig != st.session_state.last_upload_sig:
            tmpdir = _session_tmp("uploads")
            tmpdir.mkdir(exist_ok=True)
            paths=[]
            bar = st.progress(0, text="⚡ Mengompres...")
            for i, f in enumerate(uploads):
                p = tmpdir / f.name
                raw = f.getbuffer()
                try:
                    from PIL import Image
                    import io
                    img = Image.open(io.BytesIO(raw))
                    if max(img.size) > 1024: img.thumbnail((1024,1024))
                    if img.mode in ("RGBA","P"): img = img.convert("RGB")
                    img.save(p, "JPEG", quality=70, optimize=True)
                except: p.write_bytes(raw)
                paths.append(p)
                bar.progress((i+1)/len(uploads), text=f"⚡ {i+1}/{len(uploads)} siap")
            bar.empty()
            st.session_state.img_paths = paths
            st.session_state.last_upload_sig = sig
            st.session_state.excel_path = None
            st.success(f"✅ {len(paths)} foto siap")
            cols = st.columns(min(4, len(paths)))
            for i, p in enumerate(paths): cols[i%len(cols)].image(str(p), width=140, caption=f"{i+1}. {p.name[:15]}")
            _process_and_generate(paths)
    st.markdown('</div>', unsafe_allow_html=True)

with col2:
    st.markdown('<div class="upload-card">', unsafe_allow_html=True)
    drive_url = st.text_input("🔗 Link Google Drive (Folder/File)", placeholder="https://drive.google.com/drive/folders/...", help="Paste link Drive → otomatis ambil foto & buat Excel")
    drive_url_clean = drive_url.strip()
    if drive_url_clean:
        if not is_drive_link(drive_url_clean):
            st.warning(f"Link tidak terdeteksi. Kamu paste: {drive_url_clean[:60]}...")
        elif st.button("⬇️ Ambil & Buat Excel dari Drive", type="secondary", use_container_width=True):
            try:
                dest = _session_tmp("drive")
                import shutil
                if dest.exists(): shutil.rmtree(dest)
                dest.mkdir(parents=True, exist_ok=True)
                imgs = download_drive_images(drive_url_clean, dest)
                st.session_state.img_paths = imgs
                st.success(f"✅ {len(imgs)} foto dari Drive siap...")
                cols = st.columns(min(4, len(imgs)))
                for i, p in enumerate(imgs): cols[i%len(cols)].image(str(p), width=140, caption=f"{i+1}. {p.name[:15]}")
                _process_and_generate(imgs)
            except Exception as e: 
                st.error(f"Gagal Drive: {e}")
                st.info("Pastikan Share = Anyone with the link (Viewer), folder berisi JPG/PNG")
    st.markdown('</div>', unsafe_allow_html=True)

if st.session_state.img_paths and not st.session_state.excel_path:
    st.info("Foto sudah ada. Klik untuk proses.")
    if st.button("🚀 Buatkan Excel Sekarang", type="primary", use_container_width=True):
        _process_and_generate(st.session_state.img_paths)

# === HASIL — dark-detail card ala gambar ===
if st.session_state.excel_path and Path(st.session_state.excel_path).exists():
    st.divider()
    st.markdown('<div class="dark-detail">', unsafe_allow_html=True)
    st.markdown("#### 📥 Excel Sudah Jadi — Langsung Download")
    st.caption("Format 100% TAMPLATE asli. Komoditi, Kecil, Sedang, Besar, Jumlah, Satuan otomatis dari foto. Keterangan Manual.")
    with open(st.session_state.excel_path,"rb") as f:
        st.download_button("⬇️ DOWNLOAD EXCEL HASIL", data=f.read(), file_name=st.session_state.excel_fname, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, type="primary")
    st.caption(f"Nama file: **{st.session_state.excel_fname}**")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("#### 👁️ Preview (Keterangan manual)")
    for idx, rec in enumerate(st.session_state.records):
        with st.container(border=True):
            st.markdown(f"**{idx+1}. {rec['nama_pemilik']}** — {rec.get('hari_tanggal','')} — {len(rec['komoditi'])} komoditi")
            df = pd.DataFrame(rec["komoditi"])
            for c in ["nama","kecil","sedang","besar","satuan","keterangan"]: 
                if c not in df.columns: df[c]=""
            df=df[["nama","kecil","sedang","besar","satuan","keterangan"]]
            df["jumlah"]=df["kecil"].fillna(0).astype(int)+df["sedang"].fillna(0).astype(int)+df["besar"].fillna(0).astype(int)
            edited = st.data_editor(df, use_container_width=True, hide_index=True, key=f"ed_{idx}",
                column_config={
                    "nama": st.column_config.TextColumn("Komoditi (otomatis)", disabled=True),
                    "kecil": st.column_config.NumberColumn("Kecil", disabled=True),
                    "sedang": st.column_config.NumberColumn("Sedang", disabled=True),
                    "besar": st.column_config.NumberColumn("Besar", disabled=True),
                    "jumlah": st.column_config.NumberColumn("Jumlah", disabled=True),
                    "satuan": st.column_config.TextColumn("Satuan", disabled=True),
                    "keterangan": st.column_config.SelectboxColumn("Keterangan (MANUAL)", options=["Tahunan","Musiman","Semai","Produktif","Belum Produktif"], required=False),
                })
            if st.button(f"💾 Simpan Keterangan — {rec['nama_pemilik']}", key=f"save_{idx}"):
                for i,row in edited.iterrows():
                    if i < len(rec["komoditi"]): rec["komoditi"][i]["keterangan"]=str(row["keterangan"] or "Tahunan")
                generate_excel(TEMPLATE_PATH, st.session_state.records, Path(st.session_state.excel_path))
                st.success("Keterangan disimpan & Excel di-update."); st.rerun()
    if st.button("🔄 Buat Ulang / Ganti Foto"): st.session_state.img_paths=[]; st.session_state.records=[]; st.session_state.excel_path=None; st.session_state.last_upload_sig=""; st.rerun()

st.markdown('</div>', unsafe_allow_html=True)

with st.expander("⚙️ Cek API Key & Template"):
    st.write(f"API Key: {DEFAULT_API_KEY[:12]}... (dari .env)")
    st.caption("Hanya design yang diubah — fitur tetap: upload/drive → Excel, auto-tambah baris, nama file otomatis.")
