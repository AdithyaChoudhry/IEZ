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
    process_iodb_validation,
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
    "🔍  IODB Validation",
]

with st.sidebar:
    st.image("https://img.icons8.com/fluency/48/settings.png", width=48)
    st.markdown("## Instrumentation EZ")
    st.markdown("---")

    st.markdown("### � Module")
    selected_module = st.radio(
        "Select a module:",
        MODULES,
        index=0,
        label_visibility="collapsed",
    )
    st.markdown("---")

    # Summary of files currently cached in session state
    _cache_labels = {
        "iodb_upload":        "IODB Source",
        "loop_input_upload":  "Loop Wiring Input",
        "ds_template_upload": "DS Template",
        "cs_template_upload": "CS Template",
        "lw_template_upload": "LW Template",
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
    st.markdown('<div class="section-title">🗂️ Instrument List Generator</div>', unsafe_allow_html=True)
    st.markdown(
        "Select columns from the IODB and export them as a clean **Instrument List** Excel file."
    )

    iodb_raw = _file_section(
        "📊 Upload IODB Source File", "iodb_upload",
        "Main IODB source Excel file (sheet name: IODB)",
    )
    if iodb_raw is None:
        return

    iodb_bytes = iodb_raw
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
            iodb_snap = io.BytesIO(iodb_raw)
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

    iodb_raw = _file_section(
        "📊 Upload IODB Source File", "iodb_upload",
        "Main IODB source Excel file (sheet name: IODB)",
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
            iodb_snap = io.BytesIO(iodb_raw)
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
        iodb_raw = _file_section(
            "📊 Upload IODB Source File", "iodb_upload",
            "Main IODB source Excel file (sheet name: IODB)",
        )
    with col_right:
        tmpl_raw = _file_section(
            "📎 Datasheet Template", "ds_template_upload",
            "Template must contain a sheet named 'Annexure'.",
        )

    if iodb_raw is None or tmpl_raw is None:
        return

    iodb_bytes = iodb_raw
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

        iodb_snap = io.BytesIO(iodb_raw)
        tmpl_snap = io.BytesIO(tmpl_raw)
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
    st.markdown('<div class="section-title">🔄 Loop Wiring Generator</div>', unsafe_allow_html=True)
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
    st.markdown("## 🔍 IODB Validation")
    st.markdown(
        "Upload your IODB Excel file to run 12 automated validation rules. "
        "Download a colour-coded highlighted file and a full error log."
    )

    with st.expander("📋 Validation Rules Applied", expanded=False):
        st.markdown(
            """
| Rule | Description |
|------|-------------|
| 1    | All non-status/remarks cells must be filled |
| 2    | Hazardous area → IS type; Safe area → NIS type |
| 3    | Non-WABAG scope must have a Vendor Package name |
| 4    | TAG NO keyword must match Instrument Type |
| 4B   | TAG NO must be fully uppercase |
| 5    | Non-24V-DC power + not 4-wire → mismatch error |
| 6    | AI signals → AJB; DI/DO signals → DJB |
| 7    | Calibration range max must not exceed Instrument range max |
| 8    | Calibration unit must match Instrument range unit |
| 9    | Fail Action must be FO, FC, or LAST POS |
| 10   | Alarm setpoints must follow LL < L < H < HH |
| 11   | S.NO must be strictly ascending |
| 12   | Spelling check on free-text columns |
"""
        )

    iodb_file = st.file_uploader(
        "Upload IODB Excel",
        type=["xlsx", "xls"],
        key="iodb_upload",
        help="Row 1 must be column headers; Row 2 onwards are data rows.",
    )

    auto_correct = st.checkbox(
        "Auto-correct spelling in highlighted output",
        value=False,
        help="When enabled, likely misspelled words are replaced and highlighted green.",
    )

    if st.button("🔍 Run Validation", type="primary", disabled=(iodb_file is None)):
        with st.spinner("Running validation…"):
            raw_bytes = iodb_file.getvalue()
            log_bytes, hl_bytes, errs, err_msg = process_iodb_validation(
                raw_bytes, auto_correct_spelling=auto_correct
            )
        if err_msg:
            st.error(f"Validation error: {err_msg}")
        else:
            st.session_state["_val_errors"]      = errs
            st.session_state["_val_err_log"]     = log_bytes
            st.session_state["_val_highlighted"] = hl_bytes

    errors    = st.session_state.get("_val_errors")
    log_bytes = st.session_state.get("_val_err_log")
    hl_bytes  = st.session_state.get("_val_highlighted")

    if errors is not None:
        if not errors:
            st.success("✅ No validation errors found — IODB looks good!")
        else:
            r1    = [e for e in errors if e["rule"] == 1]
            r2_10 = [e for e in errors if 2 <= e["rule"] <= 10]
            r11   = [e for e in errors if e["rule"] == 11]
            r12   = [e for e in errors if e["rule"] == 12]

            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Total Errors", len(errors))
            c2.metric("Empty Cells",  len(r1),    delta_color="off")
            c3.metric("Logic Errors", len(r2_10), delta_color="off")
            c4.metric("Order Errors", len(r11),   delta_color="off")
            c5.metric("Spelling",     len(r12),   delta_color="off")

            st.markdown("---")

            from collections import defaultdict
            by_row: dict = defaultdict(list)
            for e in errors:
                by_row[e["row"]].append(e)

            st.markdown(f"### Errors by Row ({len(by_row)} rows affected)")
            for row_num in sorted(by_row):
                row_errs = by_row[row_num]
                first    = row_errs[0]
                label = (
                    f"Row {row_num}  |  S.NO: {first['sno']}  "
                    f"|  TAG: {first['tag']}  "
                    f"|  {len(row_errs)} error(s)"
                )
                with st.expander(label, expanded=False):
                    for e in row_errs:
                        badge = (
                            "🔴" if e["rule"] == 1
                            else "🔵" if e["rule"] == 12
                            else "🟡"
                        )
                        st.markdown(
                            f"`[Row {e['row']} | S.NO: {e['sno']} | TAG: {e['tag']} "
                            f"| Column: {e['column']} | Cell: {e['cell']}]`  \n"
                            f"{badge} **Rule {e['rule']}** — {e['message']}"
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
    elif MODULES[5] in selected_module:
        render_iodb_validation()

    st.markdown("</div>", unsafe_allow_html=True)
