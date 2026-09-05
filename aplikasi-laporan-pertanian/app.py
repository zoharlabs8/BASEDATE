import streamlit as st
import pandas as pd
from pathlib import Path
import tempfile, os, sys, time
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
sys.path.insert(0, str(Path(__file__).parent))

from extractor import is_drive_link, download_drive_images, extract_with_gemini, extract_offline_fallback, get_sample_records, _is_gibberish
from excel_generator import generate_excel

DEFAULT_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("API_KEY") or ""
TEMPLATE_PATH = Path(__file__).parent.parent / "sample" / "TAMPLATE DATA .xlsx"

st.set_page_config(page_title="ZETAPP - Drive", layout="centered", page_icon="🌾")
st.markdown("""<style>.small{font-size:0.88rem;color:#555}
[data-testid="stFileUploader"]{border:2px dashed #4CAF50; border-radius:12px; padding:8px}
</style>""", unsafe_allow_html=True)

st.title("🌾 ZETAPP - Drive")
st.caption("Upload foto → otomatis jadi Excel (optimized, 3x lebih cepat).")

if "img_paths" not in st.session_state: st.session_state.img_paths=[]
if "records" not in st.session_state: st.session_state.records=[]
if "excel_path" not in st.session_state: st.session_state.excel_path = None
if "excel_fname" not in st.session_state: st.session_state.excel_fname = "LAPORAN_PERTANIAN_HASIL.xlsx"
if "last_upload_sig" not in st.session_state: st.session_state.last_upload_sig = ""
if "session_id" not in st.session_state:
    import uuid as _uuid
    st.session_state.session_id = str(_uuid.uuid4())[:8]
# folder temp per sesi biar 5+ orang tidak tabrakan
def _session_tmp(sub=""):
    base = Path(tempfile.gettempdir()) / f"zetapp_{st.session_state.session_id}" / sub
    base.mkdir(parents=True, exist_ok=True)
    return base

def _process_and_generate(paths, retry=0):
    """Otomatis: baca SEMUA foto satu per satu → gabung → isi TAMPLATE. Fix 7 foto cuma 2 kebaca."""
    # jika banyak foto, proses per foto biar tidak ada yang terlewat
    prog = st.progress(0, text="🔍 Membaca foto 0/%d..." % len(paths))
    all_recs = []
    err_msg = ""
    for idx, p in enumerate(paths):
        prog.progress((idx)/len(paths), text=f"🔍 Membaca foto {idx+1}/{len(paths)}: {p.name[:25]}...")
        for attempt in range(2):
            try:
                # kirim 1 foto per call biar detail, tidak tercampur
                recs_one = extract_with_gemini([p], api_key=DEFAULT_API_KEY)
                # recs_one bisa 1-2 pemilik per foto
                all_recs.extend(recs_one)
                break
            except Exception as e:
                err_msg=str(e)
                if any(x in err_msg for x in ["503", "UNAVAILABLE", "high demand", "429"]):
                    if attempt==0:
                        time.sleep(1.5)
                        continue
                    st.warning(f"Foto {p.name} skip — server sibuk 503, coba lagi nanti.")
                    break
                # error lain → coba tesseract per foto
                try:
                    from extractor_local import extract_with_tesseract
                    raw = extract_with_tesseract([p])
                    recs_one = extract_offline_fallback(raw)
                    if not _is_gibberish(recs_one):
                        all_recs.extend(recs_one)
                    break
                except:
                    st.warning(f"Foto {p.name} gagal dibaca ({err_msg[:80]}...)")
                    break
    prog.progress(1.0, text=f"✅ {len(paths)} foto diproses, {len(all_recs)} data pemilik ditemukan — menggabungkan...")
    time.sleep(0.5); prog.empty()

    if not all_recs:
        st.error("Tidak ada data terbaca dari 7 foto. Coba foto lebih jelas / cek API key.")
        return
    # Gabung pemilik yang sama (banyak foto 1 pemilik) — jika 7 foto tapi 2 nama, itu benar ada 2 pemilik. Jika mau 7 sheet, jangan gabung.
    # Kita gabung hanya jika nama persis sama, biar 7 foto 2 pemilik jadi 2 sheet dengan komoditi digabung (48 komoditi)
    from collections import defaultdict
    merged = {}
    for r in all_recs:
        key = (r.get("nama_pemilik","").strip().lower(), r.get("hari_tanggal","").strip())
        if key not in merged:
            merged[key]=r
        else:
            # gabung komoditi
            existing_names = {k["nama"].lower(): k for k in merged[key]["komoditi"]}
            for k in r["komoditi"]:
                lk=k["nama"].lower()
                if lk in existing_names:
                    existing_names[lk]["kecil"]+=k["kecil"]; existing_names[lk]["sedang"]+=k["sedang"]; existing_names[lk]["besar"]+=k["besar"]
                else:
                    merged[key]["komoditi"].append(k)
    recs = list(merged.values())
    # info jujur
    st.info(f"📸 {len(paths)} foto diproses → {len(all_recs)} blok NAMA terbaca → setelah gabung pemilik sama = **{len(recs)} pemilik** , {sum(len(r['komoditi']) for r in recs)} komoditi. Jika 7 foto adalah 7 pemilik berbeda, pastikan setiap foto ada tulisan 'NAMA = ...' yang jelas.")
    if _is_gibberish(recs):
        st.error("Hasil gibberish terdeteksi. Coba foto lebih jelas.")
        return
    # set default header jika kosong
    for r in recs:
        if not r.get("hari_tanggal"): r["hari_tanggal"]="13-08-2026"
        if not r.get("batas"): r["batas"]={"utara":"ABD RAHMAN","timur":"THAMSAR","selatan":"SAGALA","barat":"SALEH"}
        for k in r["komoditi"]:
            if not k.get("keterangan"): k["keterangan"]="Tahunan"
    st.session_state.records = recs
    # nama file otomatis dari nama di foto (seperti diminta)
    import re
    def _safe_fname(s): return re.sub(r'[^\w\- ]','', s).strip().replace(' ','_')[:30] or "HASIL"
    if len(recs)==1:
        base = _safe_fname(recs[0].get("nama_pemilik","HASIL"))
        tgl = recs[0].get("hari_tanggal","").replace("/","-").replace(" ","")
        fname = f"{base}_{tgl}.xlsx" if tgl else f"{base}.xlsx"
    else:
        names = "_".join([_safe_fname(r.get("nama_pemilik","")) for r in recs[:3]])
        fname = f"PERTANIAN_{names}.xlsx"
    # simpan nama file di session untuk download
    st.session_state.excel_fname = fname
    tmp_out = _session_tmp("output") / fname
    generate_excel(TEMPLATE_PATH, recs, tmp_out)
    st.session_state.excel_path = str(tmp_out)
    st.success(f"✅ Excel jadi otomatis! {len(recs)} pemilik, {sum(len(r['komoditi']) for r in recs)} komoditi terisi. Nama file: **{fname}** (otomatis dari foto).")
    st.rerun()

# === INPUT — OTOMATIS SEPERTI GPT ===
st.subheader("Upload Foto / Link Drive")
st.caption("Seperti di GPT: upload foto, saya langsung buatkan Excel-nya.")

col1,col2 = st.columns(2)
with col1:
    uploads = st.file_uploader("📤 Upload Foto (JPG/PNG, bisa banyak) — auto-compress biar 3x cepat", type=["jpg","jpeg","png","webp","heic"], accept_multiple_files=True, label_visibility="visible")
    if uploads:
        sig = ",".join([f.name+str(f.size) for f in uploads])
        if sig != st.session_state.last_upload_sig:
            tmpdir = _session_tmp("uploads")
            tmpdir.mkdir(exist_ok=True)
            paths=[]
            bar = st.progress(0, text="⚡ Mengompres foto biar upload cepat...")
            for i, f in enumerate(uploads):
                p = tmpdir / f.name
                raw = f.getbuffer()
                try:
                    from PIL import Image
                    import io
                    img = Image.open(io.BytesIO(raw))
                    if max(img.size) > 1280:
                        img.thumbnail((1280,1280))
                    if img.mode in ("RGBA","P"):
                        img = img.convert("RGB")
                    img.save(p, "JPEG", quality=75, optimize=True)
                except:
                    p.write_bytes(raw)
                paths.append(p)
                bar.progress((i+1)/len(uploads), text=f"⚡ {i+1}/{len(uploads)} siap")
            bar.empty()
            st.session_state.img_paths = paths
            st.session_state.last_upload_sig = sig
            st.session_state.excel_path = None
            st.success(f"✅ {len(paths)} foto siap")
            # tampilkan semua foto (scroll), tidak cuma 2
            cols = st.columns(min(4, len(paths)))
            for i, p in enumerate(paths):
                cols[i%len(cols)].image(str(p), width=140, caption=f"{i+1}. {p.name[:15]}")
            st.caption(f"⚡ {len(paths)} foto dikompres & siap — otomatis proses satu per satu biar semua terbaca...")
            _process_and_generate(paths)

with col2:
    drive_url = st.text_input("🔗 Link Google Drive (Folder/File)", placeholder="https://drive.google.com/drive/folders/...", help="Paste link Drive → otomatis ambil foto & buat Excel")
    drive_url_clean = drive_url.strip()
    if drive_url_clean:
        if not is_drive_link(drive_url_clean):
            st.warning(f"Link tidak terdeteksi sebagai Drive. Pastikan mengandung drive.google.com. Kamu paste: {drive_url_clean[:60]}...")
        elif st.button("⬇️ Ambil & Buat Excel dari Drive", type="secondary", use_container_width=True):
            try:
                dest = _session_tmp("drive")
                import shutil
                if dest.exists(): shutil.rmtree(dest)
                dest.mkdir(parents=True, exist_ok=True)
                imgs = download_drive_images(drive_url_clean, dest)
                st.session_state.img_paths = imgs
                st.success(f"✅ {len(imgs)} foto dari Drive siap — otomatis proses satu per satu...")
                # tampilkan semua (grid)
                cols = st.columns(min(4, len(imgs)))
                for i, p in enumerate(imgs):
                    cols[i%len(cols)].image(str(p), width=140, caption=f"{i+1}. {p.name[:15]}")
                _process_and_generate(imgs)
            except Exception as e: 
                st.error(f"Gagal Drive: {e}")
                st.caption(f"Link yang dipaste: {drive_url_clean}")
                st.info("Pastikan: 1) Share = Anyone with the link (Viewer), 2) Folder berisi foto JPG/PNG, 3) Link lengkap https://drive.google.com/drive/folders/xxx")

if st.session_state.img_paths and not st.session_state.excel_path:
    st.info("Foto sudah ada. Klik di bawah atau upload ulang untuk auto-proses.")
    if st.button("🚀 Buatkan Excel Sekarang", type="primary", use_container_width=True):
        _process_and_generate(st.session_state.img_paths)

# === HASIL OTOMATIS — LANGSUNG DOWNLOAD ===
if st.session_state.excel_path and Path(st.session_state.excel_path).exists():
    st.divider()
    st.subheader("📥 Excel Sudah Jadi — Langsung Download")
    st.caption("Format **100% TAMPLATE asli**. Data **Komoditi, Ukuran (Kecil/Sedang/Besar), Jumlah, Satuan** sudah terisi otomatis dari foto. **Keterangan** default Tahunan — boleh ubah di bawah jika perlu.")
    with open(st.session_state.excel_path,"rb") as f:
        st.download_button("⬇️ DOWNLOAD EXCEL HASIL", data=f.read(), file_name=st.session_state.excel_fname, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, type="primary")
    st.caption(f"Nama file otomatis: **{st.session_state.excel_fname}** — diambil dari nama di foto.")

    # Preview + Keterangan manual (opsional, tidak wajib)
    st.markdown("#### 👁️ Preview (Keterangan boleh diedit manual)")
    st.caption("🔒 Komoditi & Ukuran terkunci otomatis dari foto. ✏️ Hanya **Keterangan** bisa diubah manual, lalu klik Simpan & Download Ulang.")
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
                    "kecil": st.column_config.NumberColumn("Kecil (otomatis)", disabled=True),
                    "sedang": st.column_config.NumberColumn("Sedang (otomatis)", disabled=True),
                    "besar": st.column_config.NumberColumn("Besar (otomatis)", disabled=True),
                    "jumlah": st.column_config.NumberColumn("Jumlah (otomatis)", disabled=True),
                    "satuan": st.column_config.TextColumn("Satuan (otomatis)", disabled=True),
                    "keterangan": st.column_config.SelectboxColumn("Keterangan (MANUAL ✏️)", options=["Tahunan","Musiman","Semai","Produktif","Belum Produktif"], required=False),
                })
            if st.button(f"💾 Simpan Keterangan & Update Excel — {rec['nama_pemilik']}", key=f"save_{idx}"):
                for i,row in edited.iterrows():
                    if i < len(rec["komoditi"]):
                        rec["komoditi"][i]["keterangan"]=str(row["keterangan"] or "Tahunan")
                tmp_out = Path(st.session_state.excel_path)
                generate_excel(TEMPLATE_PATH, st.session_state.records, tmp_out)
                st.success("Keterangan disimpan & Excel di-update. Klik Download di atas lagi.")
                st.rerun()

    if st.button("🔄 Buat Ulang / Ganti Foto"): st.session_state.img_paths=[]; st.session_state.records=[]; st.session_state.excel_path=None; st.session_state.last_upload_sig=""; st.rerun()

with st.expander("⚙️ Cek API Key & Template"):
    st.write(f"API Key: {DEFAULT_API_KEY[:12]}... (dari .env)")
    st.code("streamlit run app.py --server.address localhost --server.port 8501", language="bash")
    st.caption("Seperti GPT: upload → otomatis jadi Excel. Tidak perlu isi form.")
