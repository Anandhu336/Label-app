#!/usr/bin/env python3
# main_label_app.py  (local version with printing + ZIP download)

import io
import os
import zipfile

import streamlit as st
import pandas as pd

from po_processing import build_po_table
from label_calculation import apply_default_case_size, compute_final_labels
from label_batch_generator import (
    generate_labels_from_table,
    prepare_label_folder,
    CURRENT_RUN_DIR,
)
from label_printer import list_label_files, open_label_externally, print_all_labels


st.set_page_config(
    page_title="Label Printing App",
    layout="wide",
)

st.title("📦 → 🏷 Label Printing App")
st.caption(
    "Upload a PO, review/edit quantities and case sizes, generate labels, "
    "preview them, print locally, or download them as a ZIP file."
)


# ---------- Upload ----------
uploaded = st.file_uploader(
    "Upload PO file (CSV / XLSX / PDF)",
    type=["csv", "xlsx", "pdf"],
)

if not uploaded:
    st.info("Drag and drop your PO file above to start.")
    st.stop()

# ---------- Build base table ----------
base_table = build_po_table(uploaded)

if base_table is None or base_table.empty:
    st.error("No usable data found in the uploaded file.")
    st.stop()

st.subheader("Step 1 – Review raw table")
st.dataframe(base_table, use_container_width=True, height=400)


# ---------- Default Case Size ----------
st.subheader("Step 2 – Set Case Size and edit rows")

col1, col2 = st.columns([2, 3])
with col1:
    default_cs = st.number_input(
        "Default Case Size ",
        min_value=1,
        value=60,
        step=1,
    )


# apply default case size where missing
table_with_cs = apply_default_case_size(base_table, default_cs)

# let the user edit Outstanding & Case_Size
edit_cols = ["Sku", "Product", "Flavour", "Strength", "Outstanding", "Case_Size"]
editable_view = table_with_cs[edit_cols].copy()

edited = st.data_editor(
    editable_view,
    use_container_width=True,
    height=500,
    num_rows="dynamic",
    key="po_editor",
)

# ---------- Compute Final_Labels ----------
st.subheader("Step 3 – Final labels preview")

final_table = compute_final_labels(edited)

st.dataframe(
    final_table,
    use_container_width=True,
    height=400,
)

total_labels = int(final_table["Final_Labels"].fillna(0).sum())
st.markdown(f"**Total labels planned:** `{total_labels}`")


# ---------- Generate Labels ----------
st.subheader("Step 4 – Generate label images")

if st.button("🎨 Generate Labels"):
    if total_labels <= 0:
        st.warning("All Final_Labels are zero – nothing to generate.")
    else:
        # clean previous labels and create fresh folder
        label_dir = prepare_label_folder()

        with st.spinner("Generating label images…"):
            paths = generate_labels_from_table(final_table, label_dir=label_dir)

        if not paths:
            st.warning("No labels were generated.")
        else:
            st.success(f"Generated {len(paths)} label images in `{label_dir}`.")

            

            # store for later preview/print/download
            st.session_state["label_dir"] = label_dir
            st.session_state["label_paths"] = paths

            # ---- ZIP download button right after generation ----
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for p in paths:
                    filename = os.path.basename(p)
                    with open(p, "rb") as f:
                        zf.writestr(filename, f.read())
            zip_buffer.seek(0)

            st.download_button(
                label="⬇️ Download ALL labels as ZIP",
                data=zip_buffer,
                file_name="labels.zip",
                mime="application/zip",
            )


# ---------- Preview, Print, and ZIP (can be used after rerun) ----------
st.subheader("Step 5 – Preview, Print, and Download labels")

label_dir = st.session_state.get("label_dir", CURRENT_RUN_DIR)
label_files = list_label_files(label_dir)

if not label_files:
    st.info("No labels found yet. Generate labels in Step 4 first.")
else:
    # Show dropdown of all label files (1.png, 2.png, 3.png, ...)
    file_names = [os.path.basename(p) for p in label_files]
    selected_name = st.selectbox(
        "Choose a label to preview and print",
        options=file_names,
    )

    # map back to full path
    selected_path = label_files[file_names.index(selected_name)]

    # preview selected label (small)
    st.image(selected_path, caption=selected_name, width=200)

    col_a, col_b, col_c = st.columns(3)

    with col_a:
        if st.button("🖼 Open selected in viewer"):
            ok, err = open_label_externally(selected_path)
            if ok:
                st.success(
                    "Opened in your system's default image viewer. "
                    "Use the viewer's Print option (e.g. Cmd+P or Ctrl+P)."
                )
            else:
                st.error(f"Could not open image: {err}")

    with col_b:
        if st.button("🖨 Print ALL labels"):
            success_count, fail_count, errors = print_all_labels(label_dir)

            if success_count > 0:
                st.success(f"Sent {success_count} label(s) to the default printer.")
            if fail_count > 0:
                st.error(f"Failed to print {fail_count} label(s).")
                if errors:
                    with st.expander("Show print errors"):
                        for e in errors:
                            st.write(e)

    with col_c:
        # build ZIP on demand for download
        zip_buffer2 = io.BytesIO()
        with zipfile.ZipFile(zip_buffer2, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in label_files:
                filename = os.path.basename(p)
                with open(p, "rb") as f:
                    zf.writestr(filename, f.read())
        zip_buffer2.seek(0)

        st.download_button(
            label="⬇️ Download ALL labels as ZIP",
            data=zip_buffer2,
            file_name="labels.zip",
            mime="application/zip",
            key="zip_download_step5",
        )