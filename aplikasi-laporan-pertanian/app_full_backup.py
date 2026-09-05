import streamlit as st
import pandas as pd
from pathlib import Path
import tempfile
import os
import json
import sys

# pastikan extractor & generator bisa diimport
sys.path.insert(0, str(Path(__file__).parent))
from extractor import (
    is_drive_link, download_drive_images, extract_with_openai, extract_with_gemini,
    extract_offline_fallback, get_sample_records, VISION_PROMPT
)
try:
    from extractor_local import extract_with_ollama, extract_with_tesseract, extract_local_auto
    HAS_LOCAL = True
except ImportError:
    HAS_LOCAL = False
from excel_generator import generate_excel, TEMPLATE_PATH_DEFAULT

st.set_page_config(page_title="Laporan Pertanian — Foto → Excel", layout="wide", page_icon="🌾")

TEMPLATE_PATH = Path(__file__).parent.parent / "sample" / "TAMPLATE DATA .xlsx"
if not TEMPLATE_PATH.exists():
    TEMPLATE_PATH = TEMPLATE_PATH_DEFAULT

st.markdown("""
<style>
.small {font-size:0.85rem; color:#555}
</style>
""", unsafe_allow_html=True)

st.title("🌾 Aplikasi Laporan Pertanian — Foto / Drive → Excel TAMPLATE")
st.caption("Axpert Data Entry • Presisi 100% • Zero Data Loss • Format TAMPLATE DATA .xlsx dipertahankan 100% (merge, border, font, formula)")

with st.sidebar:
    st.header("⚙️ Mode Kerja")
    st.success("🏠 **Localhost — Tanpa API Key**\nAplikasi jalan 100% di laptop kamu. Tidak butuh internet setelah install.")
    provider = st.selectbox("Provider", [
        "✅ Localhost Offline (Default, Tanpa API Key) — Direkomendasikan",
        "🖥️ Ollama Lokal (llava/qwen2-vl) — Vision 100% Offline",
        "🔤 Tesseract OCR Lokal — Offline",
        "☁️ OpenAI GPT-4o (butuh API Key)",
        "☁️ Gemini 1.5 Pro (butuh API Key)",
        "Otomatis (Coba Online → Fallback Offline)"
    ], index=0)

    show_api = provider.startswith("☁️") or provider.startswith("Otomatis")
    if show_api:
        st.text_input("OpenAI API Key (opsional)", type="password", key="openai_key", help="Jika kosong akan pakai ENV OPENAI_API_KEY")
        st.text_input("Gemini API Key (opsional)", type="password", key="gemini_key", help="Jika kosong akan pakai ENV GEMINI_API_KEY")
    else:
        st.info("Mode localhost aktif — **tidak perlu API key**. Cukup upload foto → Preview → Download Excel.")

    if provider.startswith("🖥️"):
        st.text_input("Ollama Host", value="http://localhost:11434", key="ollama_host")
        st.selectbox("Ollama Model", ["llava", "llava:13b", "qwen2-vl", "bakllava", "llava-phi3"], key="ollama_model")
        if not HAS_LOCAL:
            st.error("extractor_local.py tidak ditemukan")
        else:
            st.caption("Install Ollama dulu: `brew install ollama && ollama pull llava && ollama serve`")

    st.divider()
    st.markdown("**Template yang dipakai:**")
    st.code(str(TEMPLATE_PATH), language="text")
    if TEMPLATE_PATH.exists():
        st.success("Template ditemukan ✓")
    else:
        st.error("Template tidak ditemukan! Letakkan TAMPLATE DATA .xlsx di sample/")
    st.divider()
    st.markdown("**Jalankan di Localhost:**")
    st.code("streamlit run app.py --server.port 8501 --server.address localhost", language="bash")

tab1, tab2, tab3 = st.tabs(["📤 1. Upload Foto / Drive", "🔍 2. Preview & Edit (Axpert Verify)", "📥 3. Download Excel"])

# Session state
if "records" not in st.session_state:
    st.session_state.records = []
if "uploaded_image_paths" not in st.session_state:
    st.session_state.uploaded_image_paths = []

with tab1:
    st.subheader("Upload Foto Buku / Link Google Drive")
    st.markdown('<p class="small">Bisa upload banyak foto sekaligus. Jika foto dari Drive, paste link folder/file Drive (pastikan link share = Anyone with the link). Aplikasi akan bekerja sedetail mungkin: B=Kecil, S=Sedang, K/Besar dihitung dengan penjumlahan "1+2+3" tanpa kehilangan data.</p>', unsafe_allow_html=True)

    colA, colB = st.columns([1,1])
    with colA:
        uploads = st.file_uploader("Upload foto (JPG/PNG) — bisa multiple", type=["jpg","jpeg","png","webp","heic"], accept_multiple_files=True)
        if uploads:
            tmpdir = Path(tempfile.gettempdir()) / "pertanian_uploads"
            tmpdir.mkdir(exist_ok=True)
            paths = []
            for f in uploads:
                p = tmpdir / f.name
                p.write_bytes(f.getbuffer())
                paths.append(p)
            st.session_state.uploaded_image_paths = paths
            st.success(f"{len(paths)} foto disimpan")
            for p in paths:
                st.image(str(p), caption=p.name, width=300)

        if st.session_state.uploaded_image_paths:
            if st.button("🧹 Hapus foto upload"):
                st.session_state.uploaded_image_paths = []
                st.rerun()

    with colB:
        drive_url = st.text_input("Atau paste Link Google Drive (folder/file berisi foto)", placeholder="https://drive.google.com/drive/folders/... atau https://drive.google.com/file/d/...")
        if drive_url.strip() and is_drive_link(drive_url):
            st.info("Link Drive terdeteksi. Klik Download.")
            if st.button("⬇️ Download dari Drive"):
                try:
                    dest = Path(tempfile.gettempdir()) / "pertanian_drive"
                    imgs = download_drive_images(drive_url.strip(), dest)
                    st.session_state.uploaded_image_paths = imgs
                    st.success(f"Berhasil download {len(imgs)} file dari Drive")
                    for p in imgs[:5]:
                        if p.suffix.lower() in {".jpg",".jpeg",".png",".webp"}:
                            st.image(str(p), width=300)
                except Exception as e:
                    st.error(f"Gagal download Drive: {e}")
        elif drive_url.strip():
            st.warning("Bukan link Drive yang valid")

    st.divider()
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🚀 Ekstrak (Localhost, Tanpa API Key)", type="primary", use_container_width=True):
            if not st.session_state.uploaded_image_paths and not drive_url.strip():
                st.warning("Tidak ada foto upload — memakai data SAMPLE (foto WhatsApp sample) untuk demo.")
                recs = get_sample_records()
                st.session_state.records = recs
                st.success(f"Demo: {len(recs)} pemilik terdeteksi (RIDWAN & SAHARIA). Buka tab Preview.")
            else:
                paths = st.session_state.uploaded_image_paths
                if not paths:
                    st.error("Upload foto dulu atau isi Drive link.")
                else:
                    with st.spinner("Axpert localhost sedang membaca tulisan tangan... (offline, tanpa API key)"):
                        recs = None
                        err_msgs = []
                        # mapping provider baru
                        try_order = []
                        if provider.startswith("✅"):
                            try_order = ["offline_paste"]  # langsung minta paste manual, tanpa API
                        elif provider.startswith("🖥️"):
                            try_order = ["ollama"]
                        elif provider.startswith("🔤"):
                            try_order = ["tesseract"]
                        elif provider.startswith("☁️ OpenAI"):
                            try_order = ["openai"]
                        elif provider.startswith("☁️ Gemini"):
                            try_order = ["gemini"]
                        else:
                            try_order = ["openai","gemini","ollama","tesseract","offline_paste"]

                        for prov in try_order:
                            try:
                                if prov == "openai":
                                    key = st.session_state.get("openai_key") or os.getenv("OPENAI_API_KEY")
                                    if not key:
                                        raise RuntimeError("API Key OpenAI kosong")
                                    recs = extract_with_openai(paths, api_key=key)
                                    st.success(f"Berhasil via OpenAI: {len(recs)} record")
                                    break
                                elif prov == "gemini":
                                    key = st.session_state.get("gemini_key") or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
                                    if not key:
                                        raise RuntimeError("API Key Gemini kosong")
                                    recs = extract_with_gemini(paths, api_key=key)
                                    st.success(f"Berhasil via Gemini: {len(recs)} record")
                                    break
                                elif prov == "ollama":
                                    if not HAS_LOCAL:
                                        raise RuntimeError("extractor_local tidak tersedia")
                                    host = st.session_state.get("ollama_host", "http://localhost:11434")
                                    model = st.session_state.get("ollama_model", "llava")
                                    recs = extract_with_ollama(paths, model=model, host=host)
                                    st.success(f"Berhasil via Ollama lokal ({model}): {len(recs)} record — 100% offline")
                                    break
                                elif prov == "tesseract":
                                    if not HAS_LOCAL:
                                        raise RuntimeError("extractor_local tidak tersedia")
                                    raw = extract_with_tesseract(paths)
                                    st.info(f"OCR Tesseract (offline) hasil:\n{raw[:300]}...")
                                    recs = extract_offline_fallback(raw)
                                    st.success(f"Tesseract offline: {len(recs)} record. Cek Tab Preview & koreksi jika perlu.")
                                    break
                                elif prov == "offline_paste":
                                    st.warning("Mode Localhost Offline: upload foto sudah tersimpan. Untuk akurasi 100% tanpa API, paste transkrip manual di bawah lalu klik Parse — atau pilih Ollama/Tesseract jika sudah install.")
                                    recs = None
                                    break
                            except Exception as e:
                                err_msgs.append(f"{prov}: {e}")
                        if recs is not None:
                            st.session_state.records = recs
                        else:
                            if err_msgs:
                                st.error("Info:\n" + "\n".join(err_msgs))
                            st.info("Pakai 'Paste Transkrip Manual' di bawah — ini 100% localhost tanpa API key, paling akurat untuk tulisan tangan." )

    with col2:
        if st.button("📋 Pakai Data Sample (RIDWAN & SAHARIA)", use_container_width=True):
            recs = get_sample_records()
            st.session_state.records = recs
            st.success(f"Sample loaded: {len(recs)} record, buka tab Preview untuk verifikasi.")

    with col3:
        if st.button("🗑️ Reset Records", use_container_width=True):
            st.session_state.records = []
            st.rerun()

    st.markdown("---")
    st.subheader("Fallback Axpert: Paste Transkrip Manual (jika AI belum yakin)")
    st.markdown('<p class="small">Jika tulisan tangan sangat sulit, paste transkrip mentah di sini (copy semua tulisan dari foto, termasuk "B 1+2+3 S 1+1 K ..."). Parser akan hitung B/S/K otomatis tanpa kehilangan data.</p>', unsafe_allow_html=True)
    manual_text = st.text_area("Transkrip mentah (format bebas, contoh ada di placeholder)", height=200, placeholder="Contoh:\nNAMA = RIDWAN\nJATI PUTIH B 1+1+1 S 1+1 K 1+2+0+1\nNENAS = 10+5+5+10+10\n...")
    if st.button("🔧 Parse Transkrip Manual"):
        if not manual_text.strip():
            st.error("Isi transkrip dulu")
        else:
            recs = extract_offline_fallback(manual_text)
            st.session_state.records = recs
            st.success(f"Parsed {len(recs)} record, {sum(len(r['komoditi']) for r in recs)} komoditi. Cek tab Preview.")

    with st.expander("Lihat Prompt AI Vision (Axpert)"):
        st.code(VISION_PROMPT, language="markdown")

with tab2:
    st.subheader("Preview & Edit — Verifikasi Axpert (Wajib cek sebelum Download)")
    if not st.session_state.records:
        st.info("Belum ada data. Upload & ekstrak di Tab 1 dulu.")
    else:
        st.markdown(f"**{len(st.session_state.records)} pemilik lahan terdeteksi.** Edit langsung di tabel — pastikan tidak ada yang hilang.")
        # Pilih record untuk edit
        names = [f"{i+1}. {r['nama_pemilik']} ({r.get('hari_tanggal','')}) — {len(r['komoditi'])} komoditi" for i,r in enumerate(st.session_state.records)]
        sel_idx = st.selectbox("Pilih pemilik untuk diedit", range(len(names)), format_func=lambda i: names[i])
        rec = st.session_state.records[sel_idx]

        colH1, colH2, colH3, colH4 = st.columns(4)
        with colH1:
            rec["nama_pemilik"] = st.text_input("Nama Pemilik Lahan", value=rec.get("nama_pemilik",""))
        with colH2:
            rec["nama_penggarap"] = st.text_input("Nama Penggarap", value=rec.get("nama_penggarap",""))
        with colH3:
            rec["hari_tanggal"] = st.text_input("Hari/Tanggal", value=rec.get("hari_tanggal",""))
        with colH4:
            rec["nub"] = st.text_input("NUB (opsional)", value=rec.get("nub",""))

        c1, c2 = st.columns(2)
        with c1:
            rec["luas_lahan"] = st.text_input("Luas Lahan", value=rec.get("luas_lahan",""), placeholder="misal: 500 M²")
            st.text_input("Lokasi (Pattallirang/Pinggir Sawa)", value=rec.get("lokasi",""), key=f"lokasi_{sel_idx}", disabled=True)
        with c2:
            st.markdown("**Batas-batas**")
            batas = rec.get("batas", {})
            cc = st.columns(2)
            with cc[0]:
                batas["utara"] = st.text_input("Utara", value=batas.get("utara",""), key=f"utara_{sel_idx}")
                batas["selatan"] = st.text_input("Selatan", value=batas.get("selatan",""), key=f"selatan_{sel_idx}")
            with cc[1]:
                batas["timur"] = st.text_input("Timur", value=batas.get("timur",""), key=f"timur_{sel_idx}")
                batas["barat"] = st.text_input("Barat", value=batas.get("barat",""), key=f"barat_{sel_idx}")
            rec["batas"] = batas

        st.markdown("**Tabel Komoditi — edit angka Kecil/Sedang/Besar langsung. Klik + untuk tambah baris, pilih baris + Delete untuk hapus.**")
        st.markdown('<p class="small">Axpert rule: B=Besar, S=Sedang, K=Kecil. Jumlah = Kecil+Sedang+Besar otomatis di Excel (formula). Satuan default Pohon, kecuali Bambu=Rumpun.</p>', unsafe_allow_html=True)

        df = pd.DataFrame(rec["komoditi"])
        # ensure columns
        for col in ["nama","kecil","sedang","besar","satuan","keterangan"]:
            if col not in df.columns:
                df[col] = 0 if col in ["kecil","sedang","besar"] else ""
        df = df[["nama","kecil","sedang","besar","satuan","keterangan"]]
        # add computed Jumlah for preview only
        df["jumlah_preview"] = df["kecil"].fillna(0).astype(int) + df["sedang"].fillna(0).astype(int) + df["besar"].fillna(0).astype(int)

        edited = st.data_editor(
            df,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "nama": st.column_config.TextColumn("Komoditi", required=True),
                "kecil": st.column_config.NumberColumn("Kecil", min_value=0, step=1),
                "sedang": st.column_config.NumberColumn("Sedang", min_value=0, step=1),
                "besar": st.column_config.NumberColumn("Besar/Produktif", min_value=0, step=1),
                "satuan": st.column_config.SelectboxColumn("Satuan", options=["Pohon","Rumpun","Batang","Ruas"]),
                "keterangan": st.column_config.TextColumn("Keterangan"),
                "jumlah_preview": st.column_config.NumberColumn("Jumlah (preview)", disabled=True),
            },
            key=f"editor_{sel_idx}"
        )
        # persist back (tanpa jumlah_preview)
        if st.button("💾 Simpan Edit Tabel", type="primary"):
            # drop preview col
            cols = ["nama","kecil","sedang","besar","satuan","keterangan"]
            # filter empty rows
            cleaned = []
            for _, row in edited.iterrows():
                if not str(row["nama"]).strip():
                    continue
                cleaned.append({
                    "nama": str(row["nama"]).strip().title(),
                    "kecil": int(row["kecil"] or 0),
                    "sedang": int(row["sedang"] or 0),
                    "besar": int(row["besar"] or 0),
                    "satuan": str(row["satuan"] or "Pohon"),
                    "keterangan": str(row["keterangan"] or "Tahunan"),
                })
            rec["komoditi"] = cleaned
            # recompute preview
            st.success(f"Tersimpan: {len(cleaned)} komoditi. Total pohon = {sum(c['kecil']+c['sedang']+c['besar'] for c in cleaned)}")
            st.rerun()

        # Ringkasan
        total_k = sum(int(k.get("kecil",0) or 0) for k in rec["komoditi"])
        total_s = sum(int(k.get("sedang",0) or 0) for k in rec["komoditi"])
        total_b = sum(int(k.get("besar",0) or 0) for k in rec["komoditi"])
        st.metric("Ringkasan pemilik ini", f"{len(rec['komoditi'])} komoditi", f"Kecil {total_k} | Sedang {total_s} | Besar {total_b} | TOTAL {total_k+total_s+total_b}")

        st.divider()
        st.subheader("Semua Records — JSON (untuk audit tanpa kehilangan data)")
        st.json(st.session_state.records)

        # Tambah pemilik baru
        with st.expander("➕ Tambah Pemilik Baru"):
            new_name = st.text_input("Nama pemilik baru")
            if st.button("Tambah"):
                if new_name.strip():
                    st.session_state.records.append({
                        "nama_pemilik": new_name.strip().title(),
                        "nama_penggarap": new_name.strip().title(),
                        "hari_tanggal": "",
                        "nub": "",
                        "luas_lahan": "",
                        "komoditi": [],
                        "batas": {},
                        "raw_text": ""
                    })
                    st.success("Ditambahkan")
                    st.rerun()

with tab3:
    st.subheader("Download Excel — Format TAMPLATE 100% Identik")
    if not st.session_state.records:
        st.warning("Belum ada data untuk diekspor.")
    else:
        st.markdown(f"Akan generate **{len(st.session_state.records)} sheet** (1 sheet per pemilik) dari template.")
        out_name = st.text_input("Nama file output", value="LAPORAN_PERTANIAN_PATTALLIRANG.xlsx")
        if not out_name.lower().endswith(".xlsx"):
            out_name += ".xlsx"

        if st.button("📥 Generate & Download Excel", type="primary", use_container_width=True):
            try:
                tmp_out = Path(tempfile.gettempdir()) / out_name
                generate_excel(TEMPLATE_PATH, st.session_state.records, tmp_out)
                st.success(f"Excel berhasil dibuat: {tmp_out}")
                with open(tmp_out, "rb") as f:
                    st.download_button("⬇️ Klik untuk Download", data=f.read(), file_name=out_name, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
                st.balloons()
                # preview jumlah
                st.markdown("**Preview:** buka file Excel untuk cek formula Jumlah (=SUM) dan border sudah identik template.")
            except Exception as e:
                st.error(f"Gagal generate Excel: {e}")
                import traceback
                st.code(traceback.format_exc())

st.divider()
st.caption("Made with ❤️ Axpert Data Entry — Detail is everything. Jika butuh bantuan API key, lihat README.md")
