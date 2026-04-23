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
    process_datasheets_v2,
    get_ai_tags_from_iodb,
    process_cable_schedule,
    process_loop_wiring,
    process_iodb_validation,
)

# ─────────────────────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="iEZ",
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
    /* Main background (light blue) */
    .main { background-color: #e6f7ff; }

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

    /* Small badge for the word 'Generator' */
    .gen-word {
        color: #ffffff;
        background-color: #2563a8;
        padding: 2px 8px;
        border-radius: 6px;
        font-weight: 600;
        margin-left: 6px;
        font-size: 0.95rem;
    }

    /* Full title white variant */
    .title-white {
        color: #ffffff !important;
        background: linear-gradient(90deg, #2563a8 0%, #1a3a5c 100%);
        padding: 6px 12px;
        border-radius: 8px;
        display: inline-block;
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
        <h1>⚙️ iEZ</h1>
        <p>Automated Engineering Document Generator — Upload your source files and generate documents in seconds.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar — Navigation + Global File Uploads
# ─────────────────────────────────────────────────────────────────────────────
MODULES = [
    "🔍  IODB Validator",
    "🗂️  Instrument List",
    "🔌  I/O List",
    "📄  Data Sheet",
    "🔗  Cable Schedule",
    "🔄  Loop Wiring",
]

with st.sidebar:
    st.image("https://img.icons8.com/fluency/48/settings.png", width=48)
    st.markdown("## iEZ")
    st.markdown("---")
    
    st.markdown("### iEZ Modules")
    selected_module = st.radio(
        "Select a module:",
        MODULES,
        index=0,
        label_visibility="collapsed",
    )
    st.markdown("---")

    # Summary of files currently cached in session state
    _cache_labels = {
        "iodb_upload":         "IODB Source",
        "loop_input_upload":   "Loop Wiring Input",
        "inst_template_upload":"Instrument List Template",
        "io_template_upload":  "I/O List Template",
        "ds_template_upload":  "DS Template",
        "cs_template_upload":  "CS Template",
        "lw_template_upload":  "LW Template",
    }
    _any_loaded = False
    for _wk, _label in _cache_labels.items():
        if f"_fc_{_wk}" in st.session_state:
            if not _any_loaded:
                st.markdown("**📂 Loaded Files**")
                _any_loaded = True
            _fname = st.session_state.get(f"_fn_{_wk}", _label)
            st.caption(f"✅ {_label}: {_fname}")
    st.markdown("---")
    st.caption("built by Akash B , Version iEz 1.0")


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
    """Return the cached bytes of the IODB file from session state, or None."""
    return st.session_state.get("_fc_iodb_upload")


def _file_section(label: str, widget_key: str, help_text: str = "") -> bytes | None:
    """
    Render a file_uploader whose bytes are persisted in st.session_state.
    Uploaded files survive module switches.  A Clear button resets them.
    Returns raw bytes when a file is available, otherwise None.
    """
    cache_key = f"_fc_{widget_key}"
    name_key  = f"_fn_{widget_key}"

    uploaded = st.file_uploader(label, type=["xlsx", "xls"], key=widget_key, help=help_text)
    if uploaded is not None:
        uploaded.seek(0)
        st.session_state[cache_key] = uploaded.read()
        st.session_state[name_key]  = uploaded.name

    cached = st.session_state.get(cache_key)
    if cached is not None:
        if uploaded is None:
            col_a, col_b = st.columns([5, 1])
            col_a.caption(f"✅ Using: **{st.session_state.get(name_key, 'cached file')}**")
            if col_b.button("✕", key=f"_clr_{widget_key}", help="Clear this file"):
                st.session_state.pop(cache_key, None)
                st.session_state.pop(name_key,  None)
                st.rerun()
        return cached
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Module 1: Instrument List
# ─────────────────────────────────────────────────────────────────────────────
def render_instrument_list():
    st.markdown('<div class="section-title"><span class="title-white">🗂️ Instrument List <span class="gen-word">Generator</span></span></div>', unsafe_allow_html=True)
    st.markdown(
        "Select columns, apply per-column filters, and export as a clean **Instrument List** Excel file."
    )

    col_left, col_right = st.columns(2)
    with col_left:
        iodb_raw = _file_section(
            "📊 Upload IODB Source File", "iodb_upload",
            "Main IODB source Excel file (sheet name: IODB)",
        )
    with col_right:
        tmpl_raw = _file_section(
            "📎 Upload Template (optional)", "inst_template_upload",
            "If provided, the output will be appended as a new sheet to this workbook.",
        )

    if iodb_raw is None:
        return

    iodb_bytes = iodb_raw
    with st.spinner("Reading IODB columns…"):
        columns, err = cached_iodb_columns(iodb_bytes)

    if err:
        st.error(f"Failed to read IODB: {err}")
        return

    # ── Column selection ──────────────────────────────────────────────────────
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

    # ── Per-column filters ────────────────────────────────────────────────────
    inst_filters: dict = {}
    if selected:
        iodb_bytes2 = get_iodb_bytes()
        df_full, err2 = cached_iodb_df(iodb_bytes2)
        if not err2 and df_full is not None:
            with st.expander("🔽 Column Filters", expanded=False):
                st.caption("Select one or more values to keep (leave empty = no filter on that column).")
                filter_cols = st.columns(min(len(selected), 3))
                for i, col_name in enumerate(selected):
                    if col_name in df_full.columns:
                        unique_vals = sorted(
                            df_full[col_name].dropna().astype(str).unique().tolist()
                        )
                        if unique_vals:
                            chosen = filter_cols[i % 3].multiselect(
                                col_name,
                                options=unique_vals,
                                default=[],
                                key=f"inst_filter_{col_name}",
                            )
                            if chosen:
                                inst_filters[col_name] = chosen

    # ── Preview ───────────────────────────────────────────────────────────────
    if selected:
        with st.expander("👁️ Preview (first 20 rows)", expanded=False):
            iodb_bytes3 = get_iodb_bytes()
            df_prev, err3 = cached_iodb_df(iodb_bytes3)
            if not err3 and df_prev is not None:
                avail = [c for c in selected if c in df_prev.columns]
                if avail:
                    preview = df_prev[avail].copy()
                    for col_name, vals in inst_filters.items():
                        if col_name in preview.columns:
                            preview = preview[preview[col_name].astype(str).isin(vals)]
                    st.dataframe(preview.head(20), use_container_width=True)

    st.markdown("---")
    if st.button("⚡ Generate Instrument List", key="gen_inst", type="primary"):
        if not selected:
            st.warning("Please select at least one column.")
            return
        with st.spinner("Generating…"):
            iodb_snap = io.BytesIO(iodb_raw)
            tmpl_snap = io.BytesIO(tmpl_raw) if tmpl_raw is not None else None
            out_bytes, filename, err = process_instrument_list(
                iodb_snap, selected,
                filters=inst_filters if inst_filters else None,
                template_file=tmpl_snap,
            )
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
    st.markdown('<div class="section-title"><span class="title-white">🔌 Input / Output List <span class="gen-word">Generator</span></span></div>', unsafe_allow_html=True)
    st.markdown(
        "Select columns, apply per-column filters, and export as an **I/O List** Excel file."
    )

    col_left, col_right = st.columns(2)
    with col_left:
        iodb_raw = _file_section(
            "📊 Upload IODB Source File", "iodb_upload",
            "Main IODB source Excel file (sheet name: IODB)",
        )
    with col_right:
        tmpl_raw = _file_section(
            "📎 Upload Template (optional)", "io_template_upload",
            "If provided, the output will be appended as a new sheet to this workbook.",
        )

    if iodb_raw is None:
        return

    iodb_bytes = iodb_raw
    with st.spinner("Reading IODB columns…"):
        columns, err = cached_iodb_columns(iodb_bytes)

    if err:
        st.error(f"Failed to read IODB: {err}")
        return

    # Suggest I/O relevant columns by default
    io_keywords = ["signal", "i/o", "io", "type", "tag", "loop", "rack", "slot", "channel", "panel"]
    suggested = [c for c in columns if any(k in c.lower() for k in io_keywords)]

    # ── Column selection ──────────────────────────────────────────────────────
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

    # ── Per-column filters ────────────────────────────────────────────────────
    io_filters: dict = {}
    if selected:
        iodb_bytes2 = get_iodb_bytes()
        df_full, err2 = cached_iodb_df(iodb_bytes2)
        if not err2 and df_full is not None:
            with st.expander("🔽 Column Filters", expanded=False):
                st.caption("Select one or more values to keep (leave empty = no filter on that column).")
                filter_cols = st.columns(min(len(selected), 3))
                for i, col_name in enumerate(selected):
                    if col_name in df_full.columns:
                        unique_vals = sorted(
                            df_full[col_name].dropna().astype(str).unique().tolist()
                        )
                        if unique_vals:
                            chosen = filter_cols[i % 3].multiselect(
                                col_name,
                                options=unique_vals,
                                default=[],
                                key=f"io_filter_{col_name}",
                            )
                            if chosen:
                                io_filters[col_name] = chosen

    # ── Preview ───────────────────────────────────────────────────────────────
    if selected:
        with st.expander("👁️ Preview (first 20 rows)", expanded=False):
            iodb_bytes3 = get_iodb_bytes()
            df_prev, err3 = cached_iodb_df(iodb_bytes3)
            if not err3 and df_prev is not None:
                avail = [c for c in selected if c in df_prev.columns]
                if avail:
                    preview = df_prev[avail].copy()
                    for col_name, vals in io_filters.items():
                        if col_name in preview.columns:
                            preview = preview[preview[col_name].astype(str).isin(vals)]
                    st.dataframe(preview.head(20), use_container_width=True)

    st.markdown("---")
    if st.button("⚡ Generate I/O List", key="gen_io", type="primary"):
        if not selected:
            st.warning("Please select at least one column.")
            return
        with st.spinner("Generating…"):
            iodb_snap = io.BytesIO(iodb_raw)
            tmpl_snap = io.BytesIO(tmpl_raw) if tmpl_raw is not None else None
            out_bytes, filename, err = process_io_list(
                iodb_snap, selected,
                filters=io_filters if io_filters else None,
                template_file=tmpl_snap,
            )
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
    st.markdown('<div class="section-title"><span class="title-white">📄 Data Sheet <span class="gen-word">Generator</span></span></div>', unsafe_allow_html=True)
    st.markdown(
        "Generate individual **Datasheet Excel files** per instrument. "
        "The IODB is read with a two-row combined header; only **AI signal** tags "
        "are shown by default. Column D headings in the template are matched to "
        "IODB columns using **fuzzy matching** (rapidfuzz)."
    )

    col_left, col_right = st.columns(2)
    with col_left:
        iodb_raw = _file_section(
            "📊 Upload IODB Source File", "iodb_upload",
            "IODB Excel file — first two rows treated as a combined header.",
        )
    with col_right:
        tmpl_raw = _file_section(
            "📎 Datasheet Template", "ds_template_upload",
            "Template must contain a sheet named 'Datasheet' (Sheet 2). "
            "Column D = headings, adjacent column = values/placeholders.",
        )

    if iodb_raw is None or tmpl_raw is None:
        return

    # ── Advanced settings ────────────────────────────────────────────────────
    with st.expander("⚙️ Advanced Settings", expanded=False):
        a1, a2 = st.columns(2)
        with a1:
            two_row = st.checkbox(
                "Two-row combined header",
                value=True,
                key="ds_two_row",
                help="Check when rows 1 + 2 of the IODB together form the column names.",
            )
        with a2:
            threshold = st.slider(
                "Fuzzy match threshold",
                min_value=30, max_value=100, value=70, step=5,
                key="ds_threshold",
                help="Minimum score (0-100) for a heading to be matched to an IODB column.",
            )

    # ── Tag loading + filtering ───────────────────────────────────────────────
    iodb_snap_for_tags = io.BytesIO(iodb_raw)
    with st.spinner("Reading AI tags from IODB…"):
        ai_tags, tag_err = get_ai_tags_from_iodb(iodb_snap_for_tags, two_row_header=two_row)

    if tag_err:
        st.error(f"Failed to read tags: {tag_err}")
        return

    if not ai_tags:
        st.warning("No AI-type tags found in the IODB. Check the 'SIGNAL I/O TYPE' column.")
        return

    with st.expander("🏷️ Tag Selection", expanded=True):
        col1, col2 = st.columns([3, 1])
        with col2:
            select_all = st.checkbox("Select all", value=False, key="ds_sel_all")
        default_tags = ai_tags if select_all else []
        selected_tags = st.multiselect(
            f"AI tags ({len(ai_tags)} found) — choose tags to generate datasheets for:",
            options=ai_tags,
            default=default_tags,
            key="ds_tag_select",
        )

    st.markdown(
        f"**{len(selected_tags)}** tag(s) selected → "
        f"will generate **{len(selected_tags)}** datasheet(s), packaged as a ZIP."
    )

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

        iodb_snap = io.BytesIO(iodb_raw)
        tmpl_snap = io.BytesIO(tmpl_raw)

        out_bytes, filename, err, mapping_logs = process_datasheets_v2(
            iodb_file=iodb_snap,
            template_file=tmpl_snap,
            selected_tags=selected_tags,
            two_row_header=two_row,
            fuzzy_threshold=threshold,
            progress_callback=progress_cb,
        )

        progress_bar.empty()

        if err:
            st.error(f"Error: {err}")
            return

        st.success(f"✅ **{len(selected_tags)} datasheets** generated → **{filename}**")
        st.download_button(
            label=f"⬇️ Download {filename}",
            data=out_bytes,
            file_name=filename,
            mime="application/zip",
            key="dl_ds",
        )

        # ── Mapping log ───────────────────────────────────────────────────────
        if mapping_logs:
            with st.expander("🔍 Heading Mapping Log", expanded=False):
                log_df = pd.DataFrame(mapping_logs)
                # Reorder columns for readability
                for col in ("tag", "heading", "iodb_col", "score", "value", "status"):
                    if col not in log_df.columns:
                        log_df[col] = ""
                display_cols = [c for c in ("tag", "heading", "iodb_col", "score", "value", "status") if c in log_df.columns]
                matched   = log_df[log_df["status"] == "MATCHED"]
                unmatched = log_df[log_df["status"] == "UNMATCHED"]
                st.markdown(
                    f"**{len(matched)}** headings matched · **{len(unmatched)}** unmatched"
                )
                st.dataframe(log_df[display_cols], use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# Module 4: Cable Schedule
# ─────────────────────────────────────────────────────────────────────────────
def render_cable_schedule():
    st.markdown('<div class="section-title"><span class="title-white">🔗 Cable Schedule <span class="gen-word">Generator</span></span></div>', unsafe_allow_html=True)
    st.markdown(
        "Group IODB rows by **Junction Box**, sort ascending, pad to 12 tags with SPARE, "
        "and fill the cable schedule template."
    )

    col_left, col_right = st.columns(2)
    with col_left:
        iodb_raw = _file_section(
            "📊 Upload IODB Source File", "iodb_upload",
            "Main IODB source Excel file (sheet name: IODB)",
        )
    with col_right:
        cs_tmpl_raw = _file_section(
            "📎 Cable Schedule Template", "cs_template_upload",
            "Template must contain a 'Cable Schedule -INST' sheet.",
        )

    if iodb_raw is None or cs_tmpl_raw is None:
        return

    # Show column pickers for JB and Tag columns
    iodb_bytes = iodb_raw
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

        iodb_snap = io.BytesIO(iodb_raw)
        cs_snap = io.BytesIO(cs_tmpl_raw)
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
    st.markdown('<div class="section-title"><span class="title-white">🔄 Loop Wiring <span class="gen-word">Generator</span></span></div>', unsafe_allow_html=True)
    st.markdown(
        "For each tag in the Loop Wiring Input file, duplicate the **AI - INST** template sheet "
        "and fill data — preserving all formulas and shapes."
    )

    col_left, col_right = st.columns(2)
    with col_left:
        lw_input_raw = _file_section(
            "📊 Loop Wiring Input File", "loop_input_upload",
            "Loop Wiring Input Excel file (must contain a 'Tag Number' column)",
        )
    with col_right:
        lw_tmpl_raw = _file_section(
            "📎 Loop Wiring Template", "lw_template_upload",
            "Template must contain a sheet named 'AI - INST'.",
        )

    if lw_input_raw is None or lw_tmpl_raw is None:
        return

    # Preview input tags
    with st.expander("👁️ Loop Wiring Input Preview", expanded=False):
        from utils.file_handler import read_loop_wiring_input
        lw_df, lw_err = read_loop_wiring_input(io.BytesIO(lw_input_raw))
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

        lw_input_snap = io.BytesIO(lw_input_raw)
        lw_tmpl_snap = io.BytesIO(lw_tmpl_raw)
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
# 6. IODB Validation
# ─────────────────────────────────────────────────────────────────────────────

def render_iodb_validation():
    from utils.dynamic_rules import (
        PREDEFINED_RULES_META, OPERATORS, OPERATOR_LABELS,
        RULE_TYPES, LOGICAL_OPERATORS,
        DynamicRule, load_rules, add_rule, delete_rule, update_rule,
    )

    st.markdown("## 🔍 IODB Validator")
    st.markdown(
        "Upload your IODB Excel file to run **predefined** and **user-defined** validation rules. "
        "Download a colour-coded highlighted file and a full error log."
    )

    # ── SECTION 1: Predefined rules (read-only) ───────────────────────────────
    with st.expander("📋 Predefined Validation Rules (System — Read Only)", expanded=False):
        for r in PREDEFINED_RULES_META:
            st.markdown(
                f"**Rule {r['rule']} — {r['name']}**  \n"
                f"<span style='color:#555;font-size:0.9em'>{r['description']}</span>",
                unsafe_allow_html=True,
            )
        st.caption("These system rules always run and cannot be modified.")

    # ── SECTION 2: Dynamic (user) rules manager ───────────────────────────────
    with st.expander("⚙️ Rule Configuration — User-Defined Rules", expanded=True):

        user_rules = load_rules()

        # ── 2a: Display existing rules ────────────────────────────────────────
        if user_rules:
            st.markdown("#### 📝 Your Rules")
            for rule in user_rules:
                # Build condition summary string
                if rule.rule_type == "DUPLICATE":
                    dup_c = rule.conditions[0].get("column", "?") if rule.conditions else "?"
                    cond_str = f"Check `{dup_c}` for duplicate values across all rows"
                else:
                    cond_parts = []
                    for ci, cond in enumerate(rule.conditions):
                        logic = cond.get("logical_operator", "AND")
                        prefix = f" **{logic}** " if ci > 0 else ""
                        cond_parts.append(
                            f"{prefix}`{cond.get('column','')}` "
                            f"**{cond.get('operator','')}** "
                            f"`{cond.get('value','')}`"
                        )
                    cond_str = "".join(cond_parts) or "_no conditions_"

                _rt = rule.rule_type
                if _rt == "ROW":
                    type_badge = ("<span style='background:#d0f0c0;color:#2d6a2d;border-radius:4px;"
                                  "padding:1px 6px;font-size:0.78em;margin-right:4px'>ROW</span>")
                elif _rt == "DUPLICATE":
                    type_badge = ("<span style='background:#fff3cd;color:#7d5b00;border-radius:4px;"
                                  "padding:1px 6px;font-size:0.78em;margin-right:4px'>DUPLICATE</span>")
                else:
                    type_badge = ("<span style='background:#dce8ff;color:#1a3a8f;border-radius:4px;"
                                  "padding:1px 6px;font-size:0.78em;margin-right:4px'>COLUMN</span>")

                c1, c2, c3, c4 = st.columns([3.5, 1.5, 0.8, 0.5])
                c1.markdown(
                    f"{type_badge}**{rule.name}**  \n"
                    f"{cond_str}  \n"
                    f"<span style='color:#c00;font-size:0.85em'>{rule.error_message}</span>"
                    + (f"  \n<span style='color:#888;font-size:0.8em'>→ anchor: "
                       f"{rule.target_column}</span>" if rule.target_column else ""),
                    unsafe_allow_html=True,
                )
                c2.markdown(
                    f"<span style='font-size:0.82em'>Priority: {rule.priority} | "
                    f"Case: {'yes' if rule.case_sensitive else 'no'}</span>",
                    unsafe_allow_html=True,
                )
                new_active = c3.checkbox("Active", value=rule.is_active, key=f"rule_active_{rule.id}")
                if new_active != rule.is_active:
                    update_rule(rule.id, is_active=new_active)
                    st.rerun()
                if c4.button("🗑️", key=f"del_rule_{rule.id}", help="Delete this rule"):
                    delete_rule(rule.id)
                    st.rerun()

            st.markdown("---")
        else:
            st.info("No user-defined rules yet. Add one below.")

        # ── 2b: Add new rule form ─────────────────────────────────────────────
        st.markdown("#### ➕ Add New Rule")

        # Rule Type selector is OUTSIDE the form so changing it re-renders
        # the form content immediately (Streamlit re-runs on selectbox change).
        _new_rt = st.selectbox(
            "Rule Type",
            options=RULE_TYPES,
            key="_new_rule_type",
            help=(
                "**COLUMN** — check a single column's cell value per row.  "
                "**ROW** — check multiple columns together using AND/OR logic.  "
                "**DUPLICATE** — fire an error on every row where a column value "
                "appears more than once in the whole dataset."
            ),
        )

        n_extra = st.session_state.get("_rule_extra_conds", 0)

        with st.form("add_rule_form", clear_on_submit=False):
            rule_name = st.text_input("Rule Name *", placeholder="e.g. Repeat Tag Check")

            # ────────────────────────────────────────────────────────────────
            if _new_rt == "DUPLICATE":
                # Simplified form — only needs one column + error message
                st.info(
                    "**DUPLICATE** rule: fires on every row where the chosen column "
                    "value is found in more than one row.  "
                    "Enter the column name to scan (e.g. **TAG NO**) and the error message."
                )
                dup_col_inp = st.text_input(
                    "Column to check for duplicates *",
                    placeholder="e.g. TAG NO",
                )
                dup_msg = st.text_input(
                    "Error Message *",
                    placeholder="e.g. Repeated Tag Found in this row",
                )
                dp1, dp2 = st.columns(2)
                dup_prio = dp1.number_input("Priority", min_value=1, max_value=999, value=100)
                dup_case = dp2.checkbox("Case-sensitive", value=False)

                save_btn = st.form_submit_button("💾 Save Rule", type="primary")
                if save_btn:
                    if not rule_name.strip() or not dup_col_inp.strip() or not dup_msg.strip():
                        st.error("Rule Name, Column, and Error Message are required.")
                    else:
                        new_rule = DynamicRule(
                            name           = rule_name.strip(),
                            rule_type      = "DUPLICATE",
                            conditions     = [{
                                "column":           dup_col_inp.strip(),
                                "operator":         "==",
                                "value":            "",
                                "logical_operator": "AND",
                            }],
                            error_message  = dup_msg.strip(),
                            case_sensitive = dup_case,
                            priority       = int(dup_prio),
                            is_active      = True,
                        )
                        add_rule(new_rule)
                        st.success(f"✅ Rule '{rule_name.strip()}' saved!")
                        st.rerun()

            # ────────────────────────────────────────────────────────────────
            else:  # COLUMN or ROW
                st.caption(
                    "**COLUMN rule**: define one primary column condition + optional AND/OR extras.  \n"
                    "**ROW rule**: define all conditions across different columns with AND/OR logic."
                )

                # ── Condition 0 (always shown) ────────────────────────────────
                st.markdown("**Condition 1** (primary)")
                r0c1, r0c2, r0c3 = st.columns(3)
                c0_col = r0c1.text_input("Column *", key="c0_col", placeholder="e.g. AREA CLASSIFICATION")
                c0_op  = r0c2.selectbox("Operator *", options=OPERATORS,
                                        format_func=lambda o: OPERATOR_LABELS.get(o, o), key="c0_op")
                c0_val = r0c3.text_input("Value", key="c0_val",
                                         placeholder="literal, comma-list, or other column name")

                # ── Extra conditions ──────────────────────────────────────────
                extra_inputs: list[dict] = []
                for ei in range(n_extra):
                    st.markdown(f"**Condition {ei + 2}**")
                    ex1, ex2, ex3, ex4 = st.columns([1.2, 3, 2.2, 3])
                    e_logic = ex1.selectbox("Logic", options=LOGICAL_OPERATORS, key=f"ec_logic_{ei}")
                    e_col   = ex2.text_input("Column", key=f"ec_col_{ei}")
                    e_op    = ex3.selectbox("Operator", options=OPERATORS,
                                            format_func=lambda o: OPERATOR_LABELS.get(o, o),
                                            key=f"ec_op_{ei}")
                    e_val   = ex4.text_input("Value", key=f"ec_val_{ei}")
                    extra_inputs.append({"logic": e_logic, "col": e_col, "op": e_op, "val": e_val})

                # ── Rule settings row ─────────────────────────────────────────
                st.markdown("**Rule settings**")
                s1, s2, s3, s4 = st.columns([2.5, 1.2, 1, 0.8])
                rule_msg   = s1.text_input("Error Message *",
                                           placeholder="e.g. Hazardous instruments must use 24V DC")
                target_col = s2.text_input("Target Column (ROW rules)",
                                           placeholder="e.g. POWER SUPPLY",
                                           help="For ROW rules: column whose cell is flagged. Leave blank to use TAG NO.")
                rule_prio  = s3.number_input("Priority", min_value=1, max_value=999, value=100)
                case_s     = s4.checkbox("Case-sensitive", value=False)

                btn1, btn2 = st.columns(2)
                add_cond_btn = btn1.form_submit_button("➕ Add Condition")
                save_btn     = btn2.form_submit_button("💾 Save Rule", type="primary")

                if add_cond_btn:
                    st.session_state["_rule_extra_conds"] = n_extra + 1
                    st.rerun()

                if save_btn:
                    if not rule_name.strip() or not c0_col.strip() or not rule_msg.strip():
                        st.error("Rule Name, Condition 1 Column, and Error Message are required.")
                    else:
                        conditions: list[dict] = [{
                            "column":           c0_col.strip(),
                            "operator":         c0_op,
                            "value":            c0_val.strip(),
                            "logical_operator": "AND",
                        }]
                        for ei_data in extra_inputs:
                            if ei_data["col"].strip():
                                conditions.append({
                                    "column":           ei_data["col"].strip(),
                                    "operator":         ei_data["op"],
                                    "value":            ei_data["val"].strip(),
                                    "logical_operator": ei_data["logic"],
                                })

                        new_rule = DynamicRule(
                            name           = rule_name.strip(),
                            rule_type      = _new_rt,
                            conditions     = conditions,
                            target_column  = target_col.strip(),
                            error_message  = rule_msg.strip(),
                            case_sensitive = case_s,
                            priority       = int(rule_prio),
                            is_active      = True,
                        )
                        add_rule(new_rule)
                        st.session_state["_rule_extra_conds"] = 0
                        st.success(f"✅ Rule '{rule_name.strip()}' saved!")
                        st.rerun()

    st.markdown("---")

    # ── SECTION 3: Upload + run ───────────────────────────────────────────────
    iodb_file = st.file_uploader(
        "📊 Upload IODB Excel",
        type=["xlsx", "xls"],
        key="iodb_upload",
        help="Row 1 must be column headers; Row 2 onwards are data rows.",
    )

    auto_correct = st.checkbox(
        "Auto-correct spelling in highlighted output",
        value=False,
        help="When enabled, likely misspelled words are replaced and highlighted green.",
    )

    # Show how many dynamic rules will run
    active_rules = [r for r in load_rules() if r.is_active]
    if active_rules:
        st.info(
            f"ℹ️ **{len(active_rules)} user-defined rule(s)** will run alongside the 12 predefined rules: "
            + ", ".join(f"_{r.name}_" for r in active_rules)
        )

    if st.button("🔍 Run Validation", type="primary", disabled=(iodb_file is None)):
        with st.spinner("Running validation…"):
            raw_bytes    = iodb_file.getvalue()
            all_dyn      = load_rules()
            log_bytes, hl_bytes, tba_bytes, errs, err_msg = process_iodb_validation(
                raw_bytes,
                auto_correct_spelling=auto_correct,
                dynamic_rules=all_dyn if all_dyn else None,
            )
        if err_msg:
            st.error(f"Validation error: {err_msg}")
        else:
            st.session_state["_val_errors"]      = errs
            st.session_state["_val_err_log"]     = log_bytes
            st.session_state["_val_highlighted"] = hl_bytes
            st.session_state["_val_tba"]         = tba_bytes

    errors    = st.session_state.get("_val_errors")
    log_bytes = st.session_state.get("_val_err_log")
    hl_bytes  = st.session_state.get("_val_highlighted")
    tba_bytes = st.session_state.get("_val_tba")

    if errors is not None:
        if not errors:
            st.success("✅ No validation errors found — IODB looks good!")
        else:
            pred_errs = [e for e in errors if e.get("source") != "dynamic"]
            dyn_errs  = [e for e in errors if e.get("source") == "dynamic"]
            r1    = [e for e in pred_errs if e["rule"] == 1]
            r2_10 = [e for e in pred_errs if isinstance(e["rule"], int) and 2 <= e["rule"] <= 10]
            r11   = [e for e in pred_errs if e["rule"] == 11]
            r12   = [e for e in pred_errs if e["rule"] == 12]

            c1, c2, c3, c4, c5, c6 = st.columns(6)
            c1.metric("Total Errors",   len(errors))
            c2.metric("Empty Cells",    len(r1),       delta_color="off")
            c3.metric("Logic Errors",   len(r2_10),    delta_color="off")
            c4.metric("Order Errors",   len(r11),      delta_color="off")
            c5.metric("Spelling",       len(r12),      delta_color="off")
            c6.metric("Dynamic Rules",  len(dyn_errs), delta_color="off")

            st.markdown("---")

            from collections import defaultdict
            by_row: dict = defaultdict(list)
            for e in errors:
                by_row[e["row"]].append(e)

            st.markdown(f"### Errors by Row ({len(by_row)} rows affected)")
            for row_num in sorted(by_row):
                row_errs = by_row[row_num]
                first    = row_errs[0]
                has_dyn  = any(e.get("source") == "dynamic" for e in row_errs)
                badge    = " 🟡" if has_dyn else ""
                label = (
                    f"Row {row_num}  |  S.NO: {first['sno']}  "
                    f"|  TAG: {first['tag']}  "
                    f"|  {len(row_errs)} error(s){badge}"
                )
                with st.expander(label, expanded=False):
                    for e in row_errs:
                        is_dyn = e.get("source") == "dynamic"
                        if is_dyn:
                            rtype = e.get("rule_type", "COLUMN")
                            src_tag = (
                                f"<span style='background:#d0f0c0;color:#2d6a2d;"
                                f"border-radius:4px;padding:1px 5px;font-size:0.78em;"
                                f"margin-right:4px'>{rtype}</span>"
                                f"<span style='background:#e0f3ff;color:#1565c0;"
                                f"border-radius:4px;padding:1px 5px;font-size:0.78em;"
                                f"margin-right:6px'>Dynamic</span>"
                            )
                        else:
                            src_tag = ""
                        rule_label = (
                            e.get("rule_name", e["rule"])
                            if is_dyn
                            else f"Rule {e['rule']}"
                        )
                        st.markdown(
                            f"{src_tag}"
                            f"`[Row {e['row']} | S.NO: {e['sno']} | TAG: {e['tag']} "
                            f"| Column: {e['column']} | Cell: {e['cell']}]`  \n"
                            f"<div style=\"text-align:center; margin-top:6px;\">"
                            f"→ {e['message']}</div>",
                            unsafe_allow_html=True,
                        )

            st.markdown("---")
            col_dl1, col_dl2 = st.columns(2)
            if log_bytes:
                col_dl1.download_button(
                    label="📥 Download Error Log (Excel)",
                    data=log_bytes,
                    file_name="IODB_Validation_Report.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dl_val_log",
                )
            if hl_bytes:
                col_dl2.download_button(
                    label="📥 Download Highlighted Excel",
                    data=hl_bytes,
                    file_name="IODB_Highlighted.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dl_val_hl",
                )

    # TBA download is always shown once validation has run (independent of errors)
    if tba_bytes:
        st.markdown("---")
        st.download_button(
            label="📥 Download TBA Details (Excel)",
            data=tba_bytes,
            file_name="TBA details.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_val_tba",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Main router
# ─────────────────────────────────────────────────────────────────────────────
with st.container():
    st.markdown('<div class="module-card">', unsafe_allow_html=True)

    if MODULES[0] in selected_module:
        render_iodb_validation()
    elif MODULES[1] in selected_module:
        render_instrument_list()
    elif MODULES[2] in selected_module:
        render_io_list()
    elif MODULES[3] in selected_module:
        render_datasheet()
    elif MODULES[4] in selected_module:
        render_cable_schedule()
    elif MODULES[5] in selected_module:
        render_loop_wiring()

    st.markdown("</div>", unsafe_allow_html=True)
