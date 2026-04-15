"""
main.py
Instrumentation EZ — Streamlit dashboard application.
Run with:  streamlit run main.py
"""

import io
import streamlit as st
import pandas as pd

from utils.template_processor import (
    get_iodb_columns,
    get_iodb_tags,
    get_iodb_dataframe,
    process_instrument_list,
    process_io_list,
    process_datasheets,
    process_cable_schedule,
    process_loop_wiring,
)

# ─────────────────────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Instrumentation EZ",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# Custom CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* Main background */
    .main { background-color: #f5f7fa; }

    /* Header bar */
    .iezheader {
        background: linear-gradient(90deg, #1a3a5c 0%, #2563a8 100%);
        padding: 18px 32px 12px 32px;
        border-radius: 10px;
        margin-bottom: 18px;
    }
    .iezheader h1 {
        color: #ffffff;
        font-size: 2.2rem;
        font-weight: 700;
        margin: 0;
        letter-spacing: 1px;
    }
    .iezheader p {
        color: #c5d8f0;
        margin: 4px 0 0 0;
        font-size: 0.95rem;
    }

    /* Module card */
    .module-card {
        background: #ffffff;
        border-radius: 10px;
        padding: 24px 28px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.07);
        margin-bottom: 10px;
    }

    /* Sidebar module buttons */
    div[data-testid="stSidebarContent"] .stButton>button {
        width: 100%;
        border-radius: 8px;
        margin-bottom: 4px;
        font-weight: 500;
    }

    /* Active module highlight */
    .active-module {
        border-left: 5px solid #2563a8;
        padding-left: 10px;
    }

    /* Section title */
    .section-title {
        font-size: 1.15rem;
        font-weight: 600;
        color: #1a3a5c;
        border-bottom: 2px solid #e0eaf5;
        padding-bottom: 6px;
        margin-bottom: 14px;
    }

    /* Success/error messages */
    div[data-testid="stAlert"] { border-radius: 8px; }

    /* Download button */
    div[data-testid="stDownloadButton"] > button {
        background-color: #2563a8;
        color: white;
        border-radius: 8px;
        font-weight: 600;
        width: 100%;
        margin-top: 10px;
    }
    div[data-testid="stDownloadButton"] > button:hover {
        background-color: #1a3a5c;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class="iezheader">
        <h1>⚙️ Instrumentation EZ</h1>
        <p>Automated Engineering Document Generator — Upload your source files and generate documents in seconds.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar — Navigation + Global File Uploads
# ─────────────────────────────────────────────────────────────────────────────
MODULES = [
    "🗂️  Instrument List",
    "🔌  I/O List",
    "📄  Data Sheet",
    "🔗  Cable Schedule",
    "🔄  Loop Wiring",
]

with st.sidebar:
    st.image("https://img.icons8.com/fluency/48/settings.png", width=48)
    st.markdown("## Instrumentation EZ")
    st.markdown("---")

    st.markdown("### 📁 Global File Uploads")
    iodb_file = st.file_uploader(
        "Upload IODB Source File",
        type=["xlsx", "xls"],
        key="iodb_upload",
        help="Main IODB source Excel file (sheet name: IODB)",
    )
    loop_input_file = st.file_uploader(
        "Upload Loop Wiring Input File",
        type=["xlsx", "xls"],
        key="loop_input_upload",
        help="Loop Wiring Input Excel file (must contain a 'Tag Number' column)",
    )

    st.markdown("---")
    st.markdown("### 📑 Module")
    selected_module = st.radio(
        "Select a module:",
        MODULES,
        index=0,
        label_visibility="collapsed",
    )
    st.markdown("---")
    st.caption("v1.0.0 · Built with Streamlit & openpyxl")


# ─────────────────────────────────────────────────────────────────────────────
# Helper: cached IODB read (avoids re-parsing on every widget interaction)
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def cached_iodb_columns(file_bytes: bytes) -> tuple[list[str] | None, str | None]:
    buf = io.BytesIO(file_bytes)
    return get_iodb_columns(buf)


@st.cache_data(show_spinner=False)
def cached_iodb_tags(file_bytes: bytes, tag_col: str) -> tuple[list[str] | None, str | None]:
    buf = io.BytesIO(file_bytes)
    return get_iodb_tags(buf, tag_col)


@st.cache_data(show_spinner=False)
def cached_iodb_df(file_bytes: bytes) -> tuple[pd.DataFrame | None, str | None]:
    buf = io.BytesIO(file_bytes)
    return get_iodb_dataframe(buf)


def get_iodb_bytes() -> bytes | None:
    """Return the raw bytes of the uploaded IODB file, or None."""
    if iodb_file is not None:
        iodb_file.seek(0)
        return iodb_file.read()
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Module 1: Instrument List
# ─────────────────────────────────────────────────────────────────────────────
def render_instrument_list():
    st.markdown('<div class="section-title">🗂️ Instrument List Generator</div>', unsafe_allow_html=True)
    st.markdown(
        "Select columns from the IODB and export them as a clean **Instrument List** Excel file."
    )

    if iodb_file is None:
        st.info("⬆️ Please upload the **IODB Source File** in the sidebar to continue.")
        return

    iodb_bytes = get_iodb_bytes()
    with st.spinner("Reading IODB columns…"):
        columns, err = cached_iodb_columns(iodb_bytes)

    if err:
        st.error(f"Failed to read IODB: {err}")
        return

    with st.expander("📋 Column Selection", expanded=True):
        col1, col2 = st.columns([3, 1])
        with col2:
            select_all = st.checkbox("Select all columns", value=False, key="inst_sel_all")
        default_cols = columns if select_all else []
        selected = st.multiselect(
            "Choose columns to include:",
            options=columns,
            default=default_cols,
            key="inst_col_select",
        )

    # Preview
    if selected:
        with st.expander("👁️ Preview (first 20 rows)", expanded=False):
            iodb_bytes2 = get_iodb_bytes()
            df, err2 = cached_iodb_df(iodb_bytes2)
            if not err2:
                avail = [c for c in selected if c in df.columns]
                if avail:
                    st.dataframe(df[avail].head(20), use_container_width=True)

    st.markdown("---")
    if st.button("⚡ Generate Instrument List", key="gen_inst", type="primary"):
        if not selected:
            st.warning("Please select at least one column.")
            return
        with st.spinner("Generating…"):
            iodb_file.seek(0)
            iodb_snap = io.BytesIO(iodb_file.read())
            out_bytes, filename, err = process_instrument_list(iodb_snap, selected)
        if err:
            st.error(f"Error: {err}")
        else:
            st.success(f"✅ **{filename}** generated successfully!")
            st.download_button(
                label=f"⬇️ Download {filename}",
                data=out_bytes,
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_inst",
            )


# ─────────────────────────────────────────────────────────────────────────────
# Module 2: I/O List
# ─────────────────────────────────────────────────────────────────────────────
def render_io_list():
    st.markdown('<div class="section-title">🔌 Input / Output List Generator</div>', unsafe_allow_html=True)
    st.markdown(
        "Select columns from the IODB and export them as an **I/O List** Excel file."
    )

    if iodb_file is None:
        st.info("⬆️ Please upload the **IODB Source File** in the sidebar to continue.")
        return

    iodb_bytes = get_iodb_bytes()
    with st.spinner("Reading IODB columns…"):
        columns, err = cached_iodb_columns(iodb_bytes)

    if err:
        st.error(f"Failed to read IODB: {err}")
        return

    # Suggest I/O relevant columns by default
    io_keywords = ["signal", "i/o", "io", "type", "tag", "loop", "rack", "slot", "channel", "panel"]
    suggested = [c for c in columns if any(k in c.lower() for k in io_keywords)]

    with st.expander("📋 Column Selection", expanded=True):
        col1, col2 = st.columns([3, 1])
        with col2:
            select_all = st.checkbox("Select all columns", value=False, key="io_sel_all")
        default_cols = columns if select_all else suggested
        selected = st.multiselect(
            "Choose columns to include:",
            options=columns,
            default=[c for c in default_cols if c in columns],
            key="io_col_select",
        )

    # Preview
    if selected:
        with st.expander("👁️ Preview (first 20 rows)", expanded=False):
            iodb_bytes2 = get_iodb_bytes()
            df, err2 = cached_iodb_df(iodb_bytes2)
            if not err2:
                avail = [c for c in selected if c in df.columns]
                if avail:
                    st.dataframe(df[avail].head(20), use_container_width=True)

    st.markdown("---")
    if st.button("⚡ Generate I/O List", key="gen_io", type="primary"):
        if not selected:
            st.warning("Please select at least one column.")
            return
        with st.spinner("Generating…"):
            iodb_file.seek(0)
            iodb_snap = io.BytesIO(iodb_file.read())
            out_bytes, filename, err = process_io_list(iodb_snap, selected)
        if err:
            st.error(f"Error: {err}")
        else:
            st.success(f"✅ **{filename}** generated successfully!")
            st.download_button(
                label=f"⬇️ Download {filename}",
                data=out_bytes,
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_io",
            )


# ─────────────────────────────────────────────────────────────────────────────
# Module 3: Data Sheet
# ─────────────────────────────────────────────────────────────────────────────
def render_datasheet():
    st.markdown('<div class="section-title">📄 Data Sheet Generator</div>', unsafe_allow_html=True)
    st.markdown(
        "Generate individual **Datasheet Excel files** per instrument, filled from the IODB into the template's **Annexure** sheet."
    )

    col_left, col_right = st.columns(2)
    with col_left:
        if iodb_file is None:
            st.info("⬆️ Upload **IODB Source File** in the sidebar.")
    with col_right:
        ds_template = st.file_uploader(
            "📎 Upload Datasheet Template (.xlsx)",
            type=["xlsx", "xls"],
            key="ds_template_upload",
            help="Template must contain a sheet named 'Annexure'.",
        )

    if iodb_file is None or ds_template is None:
        return

    iodb_bytes = get_iodb_bytes()
    with st.spinner("Reading IODB tags…"):
        tags, err = cached_iodb_tags(iodb_bytes, "TAG NO")

    if err:
        st.error(f"Failed to read tags: {err}")
        return

    with st.expander("🏷️ Tag Selection", expanded=True):
        col1, col2 = st.columns([3, 1])
        with col2:
            select_all = st.checkbox("Select all tags", value=False, key="ds_sel_all")
        default_tags = tags if select_all else []
        selected_tags = st.multiselect(
            "Choose tags to generate datasheets for:",
            options=tags,
            default=default_tags,
            key="ds_tag_select",
        )

    st.markdown(f"**{len(selected_tags)}** tag(s) selected → will generate **{len(selected_tags)}** datasheet(s), packaged as a ZIP.")

    st.markdown("---")
    if st.button("⚡ Generate Datasheets", key="gen_ds", type="primary"):
        if not selected_tags:
            st.warning("Please select at least one tag.")
            return
        progress_bar = st.progress(0, text="Generating datasheets…")

        def progress_cb(current, total):
            if total > 0:
                progress_bar.progress(
                    min(int((current / total) * 100), 100),
                    text=f"Processing tag {current}/{total}…",
                )

        iodb_file.seek(0)
        iodb_snap = io.BytesIO(iodb_file.read())
        ds_template.seek(0)
        tmpl_snap = io.BytesIO(ds_template.read())
        out_bytes, filename, err = process_datasheets(
            iodb_snap, tmpl_snap, "TAG NO", selected_tags, progress_callback=progress_cb
        )
        progress_bar.empty()
        if err:
            st.error(f"Error: {err}")
        else:
            st.success(f"✅ **{len(selected_tags)} datasheets** generated → **{filename}**")
            st.download_button(
                label=f"⬇️ Download {filename}",
                data=out_bytes,
                file_name=filename,
                mime="application/zip",
                key="dl_ds",
            )


# ─────────────────────────────────────────────────────────────────────────────
# Module 4: Cable Schedule
# ─────────────────────────────────────────────────────────────────────────────
def render_cable_schedule():
    st.markdown('<div class="section-title">🔗 Cable Schedule Generator</div>', unsafe_allow_html=True)
    st.markdown(
        "Group IODB rows by **Junction Box**, sort ascending, pad to 12 tags with SPARE, "
        "and fill the cable schedule template."
    )

    col_left, col_right = st.columns(2)
    with col_left:
        if iodb_file is None:
            st.info("⬆️ Upload **IODB Source File** in the sidebar.")
    with col_right:
        cs_template = st.file_uploader(
            "📎 Upload Cable Schedule Template (.xlsx)",
            type=["xlsx", "xls"],
            key="cs_template_upload",
            help="Template must contain a 'Cable Schedule -INST' sheet.",
        )

    if iodb_file is None or cs_template is None:
        return

    # Show column pickers for JB and Tag columns
    iodb_bytes = get_iodb_bytes()
    with st.spinner("Reading IODB columns…"):
        columns, err = cached_iodb_columns(iodb_bytes)
    if err:
        st.error(f"Failed to read IODB: {err}")
        return

    with st.expander("⚙️ Column Mapping", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            jb_col = st.selectbox(
                "Junction Box Column",
                options=columns,
                index=columns.index("JUNCTION BOX") if "JUNCTION BOX" in columns else 0,
                key="cs_jb_col",
            )
        with c2:
            tag_col = st.selectbox(
                "Tag Number Column",
                options=columns,
                index=columns.index("TAG NO") if "TAG NO" in columns else 0,
                key="cs_tag_col",
            )

    # Show JB summary preview
    with st.expander("👁️ JB Summary Preview", expanded=False):
        iodb_bytes2 = get_iodb_bytes()
        df, err2 = cached_iodb_df(iodb_bytes2)
        if not err2 and jb_col in df.columns:
            jb_summary = (
                df[df[jb_col].notna()]
                .groupby(jb_col)[tag_col]
                .count()
                .reset_index()
                .rename(columns={jb_col: "Junction Box", tag_col: "Tag Count"})
                .sort_values("Junction Box")
            )
            st.dataframe(jb_summary, use_container_width=True)

    st.markdown("---")
    if st.button("⚡ Generate Cable Schedule", key="gen_cs", type="primary"):
        progress_bar = st.progress(0, text="Generating cable schedule…")

        def progress_cb(current, total):
            if total > 0:
                progress_bar.progress(
                    min(int((current / total) * 100), 100),
                    text=f"Processing JB {current}/{total}…",
                )

        iodb_file.seek(0)
        iodb_snap = io.BytesIO(iodb_file.read())
        cs_template.seek(0)
        cs_snap = io.BytesIO(cs_template.read())
        out_bytes, filename, err = process_cable_schedule(
            iodb_snap, cs_snap, jb_col, tag_col, progress_callback=progress_cb
        )
        progress_bar.empty()
        if err:
            st.error(f"Error: {err}")
        else:
            st.success(f"✅ **{filename}** generated successfully!")
            st.download_button(
                label=f"⬇️ Download {filename}",
                data=out_bytes,
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_cs",
            )


# ─────────────────────────────────────────────────────────────────────────────
# Module 5: Loop Wiring
# ─────────────────────────────────────────────────────────────────────────────
def render_loop_wiring():
    st.markdown('<div class="section-title">🔄 Loop Wiring Generator</div>', unsafe_allow_html=True)
    st.markdown(
        "For each tag in the Loop Wiring Input file, duplicate the **AI - INST** template sheet "
        "and fill data — preserving all formulas and shapes."
    )

    col_left, col_right = st.columns(2)
    with col_left:
        if loop_input_file is None:
            st.info("⬆️ Upload **Loop Wiring Input File** in the sidebar.")
    with col_right:
        lw_template = st.file_uploader(
            "📎 Upload Loop Wiring Template (.xlsx)",
            type=["xlsx", "xls"],
            key="lw_template_upload",
            help="Template must contain a sheet named 'AI - INST'.",
        )

    if loop_input_file is None or lw_template is None:
        return

    # Preview input tags
    with st.expander("👁️ Loop Wiring Input Preview", expanded=False):
        from utils.file_handler import read_loop_wiring_input
        loop_input_file.seek(0)
        lw_df, lw_err = read_loop_wiring_input(loop_input_file)
        if lw_err:
            st.error(f"Could not read Loop Wiring Input: {lw_err}")
        else:
            st.dataframe(lw_df.head(20), use_container_width=True)
            tag_col = next(
                (c for c in lw_df.columns if c.strip().lower() == "tag number"), None
            )
            if tag_col:
                tags_found = lw_df[tag_col].dropna().astype(str).str.strip().unique().tolist()
                st.info(f"**{len(tags_found)} unique tags** found → will generate **{len(tags_found)} sheets**.")

    st.markdown("---")
    if st.button("⚡ Generate Loop Wiring", key="gen_lw", type="primary"):
        progress_bar = st.progress(0, text="Generating loop wiring…")

        def progress_cb(current, total):
            if total > 0:
                progress_bar.progress(
                    min(int((current / total) * 100), 100),
                    text=f"Processing tag {current}/{total}…",
                )

        loop_input_file.seek(0)
        lw_input_snap = io.BytesIO(loop_input_file.read())
        lw_template.seek(0)
        lw_tmpl_snap = io.BytesIO(lw_template.read())
        out_bytes, filename, err = process_loop_wiring(
            lw_input_snap, lw_tmpl_snap, progress_callback=progress_cb
        )
        progress_bar.empty()
        if err:
            st.error(f"Error: {err}")
        else:
            st.success(f"✅ **{filename}** generated successfully!")
            st.download_button(
                label=f"⬇️ Download {filename}",
                data=out_bytes,
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_lw",
            )


# ─────────────────────────────────────────────────────────────────────────────
# Main router
# ─────────────────────────────────────────────────────────────────────────────
with st.container():
    st.markdown('<div class="module-card">', unsafe_allow_html=True)

    if MODULES[0] in selected_module:
        render_instrument_list()
    elif MODULES[1] in selected_module:
        render_io_list()
    elif MODULES[2] in selected_module:
        render_datasheet()
    elif MODULES[3] in selected_module:
        render_cable_schedule()
    elif MODULES[4] in selected_module:
        render_loop_wiring()

    st.markdown("</div>", unsafe_allow_html=True)
