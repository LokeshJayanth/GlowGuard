import os
import io
import time
from typing import List, Tuple
import zipfile

import numpy as np
import streamlit as st
from PIL import Image

from lib import (
    inject_css,
    render_brand_header,
    render_footer,
    render_sidebar_brand,
    predict_skin_type_smart,
    DEFAULT_ONNX_MODEL,
    SKIN_TYPES,
)

st.set_page_config(page_title="GlowGuard+ • Evaluate Model", page_icon="🧪")

inject_css()
render_sidebar_brand()

st.title("🧪 Evaluate Model")
st.caption("Run batch inference on a labeled folder to compute accuracy and a confusion matrix.")

render_brand_header(
    title="Evaluate ONNX Model",
    subtitle="Point to a test dataset organized as data/test/<ClassName>/*.jpg and compute metrics.",
    emoji="🧪",
)

st.markdown("""
Provide the path to a local folder with this structure:
- data/test/Normal/*.jpg
- data/test/Dry/*.jpg
- data/test/Oily/*.jpg
- data/test/Sensitive/*.jpg

Notes:
- The ONNX model path is expected at: `models/skin_type.onnx`.
- Prediction uses the current Upload & Predict settings: Auto (ONNX > Simulated), ONNX, or Simulated.
""")

with st.expander("Model & Dataset Setup", expanded=True):
    # Model uploader
    st.subheader("Model File (ONNX)")
    model_exists = os.path.exists(DEFAULT_ONNX_MODEL)
    st.caption(f"Current: {'Found ✅' if model_exists else 'Missing ⚠️'} — {DEFAULT_ONNX_MODEL}")
    uploaded_model = st.file_uploader("Upload ONNX model", type=["onnx"], key="onnx_upload")
    if uploaded_model is not None:
        os.makedirs(os.path.dirname(DEFAULT_ONNX_MODEL), exist_ok=True)
        with open(DEFAULT_ONNX_MODEL, "wb") as f:
            f.write(uploaded_model.read())
        st.success("Model uploaded to models/skin_type.onnx")
        model_exists = True

    # Dataset zip uploader
    st.subheader("Test Dataset (ZIP)")
    st.caption("Upload a ZIP containing class folders: Normal, Dry, Oily, Sensitive")
    zip_file = st.file_uploader("Upload test set ZIP", type=["zip"], key="zip_upload")
    if zip_file is not None:
        os.makedirs("data/test", exist_ok=True)
        with zipfile.ZipFile(zip_file) as zf:
            zf.extractall("data/test")
        st.success("Extracted test set into data/test")

    # Quick create folders
    if st.button("Create empty class folders", key="mk_classes"):
        for cls in SKIN_TYPES:
            os.makedirs(os.path.join("data/test", cls), exist_ok=True)
        st.success("Created data/test/Normal|Dry|Oily|Sensitive")

st.markdown("---")
st.subheader("Evaluation Settings")
single_class_mode = st.checkbox("Single-class evaluation (use only one class folder)", value=False)
target_class = None
single_root = None
if single_class_mode:
    target_class = st.selectbox("Target class", SKIN_TYPES, index=0)
    single_root = st.text_input(
        "Folder for selected class",
        value=os.path.join("data", "test", target_class),
        help="Path that contains only images of the selected class.",
    )
else:
    root_dir = st.text_input("Test dataset root directory", value="data/test")
mode_label = st.selectbox(
    "Prediction Mode",
    ["Auto (ONNX > Simulated)", "ONNX (pretrained)", "Simulated"],
    index=0,
)
mode_map = {
    "Auto (ONNX > Simulated)": "auto",
    "ONNX (pretrained)": "onnx",
    "Simulated": "simulated",
}
pred_mode = mode_map.get(mode_label, "auto")

model_exists = os.path.exists(DEFAULT_ONNX_MODEL)
st.caption(f"Model file: {'Found ✅' if model_exists else 'Missing ⚠️'} — {DEFAULT_ONNX_MODEL}")

start = st.button("▶️ Run Evaluation", type="primary")

if start:
    if single_class_mode:
        # Validate single-class directory
        if not single_root or not os.path.isdir(single_root):
            st.error("Folder not found. Please provide a valid class folder path.")
            st.stop()
    else:
        if not os.path.isdir(root_dir):
            st.error("Directory not found. Please provide a valid path.")
            st.stop()

    # Collect (path, label)
    samples: List[Tuple[str, str]] = []
    if single_class_mode:
        # Only collect samples from the selected class folder
        for fname in os.listdir(single_root):
            fpath = os.path.join(single_root, fname)
            if os.path.isfile(fpath) and fname.lower().endswith((".jpg", ".jpeg", ".png")):
                samples.append((fpath, target_class))
    else:
        # Multi-class: gather from each class subfolder
        for cls in SKIN_TYPES:
            cls_dir = os.path.join(root_dir, cls)
            if not os.path.isdir(cls_dir):
                st.warning(f"Missing class folder: {cls_dir}")
                continue
            for fname in os.listdir(cls_dir):
                fpath = os.path.join(cls_dir, fname)
                if os.path.isfile(fpath) and fname.lower().endswith((".jpg", ".jpeg", ".png")):
                    samples.append((fpath, cls))

    if not samples:
        st.error("No images found. Ensure your folder has class subfolders with images.")
        st.stop()

    if single_class_mode:
        st.info(f"Found {len(samples)} images in '{target_class}' class. Starting...")
    else:
        st.info(f"Found {len(samples)} images across {len(SKIN_TYPES)} classes. Starting...")

    y_true = []
    y_pred = []

    progress = st.progress(0)
    status = st.empty()
    results_rows = []

    for i, (img_path, true_label) in enumerate(samples, start=1):
        try:
            with open(img_path, "rb") as f:
                img_bytes = f.read()
            pred = predict_skin_type_smart(img_bytes, name_seed=os.path.basename(img_path), mode=pred_mode)
        except Exception as e:
            pred = "ERROR"

        y_true.append(true_label)
        y_pred.append(pred)
        results_rows.append({"path": img_path, "true": true_label, "pred": pred})

        progress.progress(i / len(samples))
        status.text(f"Processed {i}/{len(samples)}")

    # Compute metrics
    labels = SKIN_TYPES
    label_to_idx = {c: idx for idx, c in enumerate(labels)}
    cm = np.zeros((len(labels), len(labels)), dtype=int)
    correct = 0
    total = 0

    for t, p in zip(y_true, y_pred):
        if p == "ERROR" or t not in label_to_idx or p not in label_to_idx:
            continue
        total += 1
        if t == p:
            correct += 1
        cm[label_to_idx[t], label_to_idx[p]] += 1

    acc = (correct / total) * 100 if total else 0.0

    st.subheader("Results")
    if single_class_mode:
        st.metric(f"Accuracy for '{target_class}'", f"{acc:.2f}%")
    else:
        st.metric("Overall Accuracy", f"{acc:.2f}%")

    st.write("Confusion Matrix (rows=true, cols=pred)")
    cm_df = None
    try:
        import pandas as pd
        cm_df = pd.DataFrame(cm, index=labels, columns=labels)
        st.dataframe(cm_df)
    except Exception:
        st.write(cm.tolist())

    # Download predictions CSV
    try:
        import pandas as pd
        out_df = pd.DataFrame(results_rows)
        csv_buf = io.StringIO()
        out_df.to_csv(csv_buf, index=False)
        st.download_button("Download Predictions CSV", csv_buf.getvalue(), file_name="predictions.csv", mime="text/csv")
    except Exception:
        pass

render_footer()
