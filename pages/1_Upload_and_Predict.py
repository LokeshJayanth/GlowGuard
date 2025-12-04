import io
import uuid
import streamlit as st
from PIL import Image

from lib import (
    init_db,
    predict_skin_type,
    predict_skin_type_smart,
    inject_css,
    render_brand_header,
    render_footer,
    render_sidebar_brand,
    try_switch_page,
)
import os
from lib import DEFAULT_ONNX_MODEL

st.set_page_config(page_title="GlowGuard+ • Upload & Predict", page_icon="📤")
init_db()

inject_css()
render_sidebar_brand()

st.title("📤 Upload & Predict")
st.caption("Step 1 of 4")

render_brand_header(
    title="Step 1 — Upload & Predict",
    subtitle="Upload your selfie and run a simulated AI prediction to unlock tailored questions.",
    emoji="📤",
)

with st.sidebar:
    st.subheader("Session")
    name = st.text_input("Name", value=st.session_state.get("name", "User"))
    st.session_state["name"] = name
    st.divider()
    st.subheader("Prediction")
    mode_label = st.selectbox(
        "Prediction Mode",
        ["Auto (ONNX > Heuristic > Simulated)", "ONNX (pretrained)", "Heuristic (no-ML)", "Simulated"],
        index=0,
        help="Use a pretrained ONNX model if available; otherwise try a simple heuristic or simulated baseline.",
    )
    mode_map = {
        "Auto (ONNX > Heuristic > Simulated)": "auto",
        "ONNX (pretrained)": "onnx",
        "Heuristic (no-ML)": "heuristic",
        "Simulated": "simulated",
    }
    pred_mode = mode_map.get(mode_label, "auto")
    st.session_state["pred_mode"] = pred_mode
    # Show model availability hint
    model_exists = os.path.exists(DEFAULT_ONNX_MODEL)
    st.caption(f"Model file: {'Found ✅' if model_exists else 'Missing ⚠️'} — {DEFAULT_ONNX_MODEL}")
    if not model_exists:
        st.info("No model file found. For better results without a model, choose 'Heuristic (no-ML)'.")

st.markdown("Upload a clear, front-facing selfie or use your camera. Supported formats: JPG/PNG.")

# Persistent mode selector so reruns don't jump between sections
if "upload_mode" not in st.session_state:
    st.session_state["upload_mode"] = "Upload"

mode = st.radio("Mode", ["Upload", "Camera"], index=0 if st.session_state["upload_mode"] == "Upload" else 1, horizontal=True, key="upload_mode")

uploaded_file = None
cam_file = None

if mode == "Upload":
    uploaded_file = st.file_uploader(
        "Choose a selfie image...",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=False,
        help="Select an image from your device."
    )
elif mode == "Camera":
    # Initialize camera toggle
    if "camera_enabled" not in st.session_state:
        st.session_state["camera_enabled"] = False

    # Two explicit buttons: Start and Stop
    col_b1, col_b2 = st.columns([1, 1])
    with col_b1:
        start_pressed = st.button("▶️ Start Camera", key="btn_start_cam", disabled=st.session_state["camera_enabled"])
    with col_b2:
        stop_pressed = st.button("⏹ Stop Camera", key="btn_stop_cam", disabled=not st.session_state["camera_enabled"])

    if start_pressed:
        st.session_state["camera_enabled"] = True
        st.rerun()
    if stop_pressed:
        st.session_state["camera_enabled"] = False
        st.rerun()

    if st.session_state["camera_enabled"]:
        cam_file = st.camera_input("Take a photo", help="Allow camera access to capture an image.")
    else:
        cam_file = None

image_bytes = st.session_state.get("uploaded_image")
if uploaded_file is not None:
    img = Image.open(uploaded_file)
    st.image(img, caption="Uploaded Selfie", use_column_width=True)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    image_bytes = buf.getvalue()
    st.session_state["uploaded_image"] = image_bytes
elif cam_file is not None:
    # camera_input returns a file-like object; we can read bytes directly
    image_bytes = cam_file.getvalue()
    try:
        img = Image.open(io.BytesIO(image_bytes))
        st.image(img, caption="Captured Selfie", use_column_width=True)
    except Exception:
        st.warning("Could not read camera image. Please try again or use Upload.")
    st.session_state["uploaded_image"] = image_bytes

predict_clicked = st.button("🔍 Predict Skin", disabled=(image_bytes is None))
if predict_clicked:
    # Use selected predictor
    predicted_skin = predict_skin_type_smart(image_bytes, name_seed=name or "User", mode=st.session_state.get("pred_mode", "auto"))
    st.session_state["predicted_skin"] = predicted_skin
    st.session_state["predicted_skin_from_ai"] = True
    st.session_state["session_id"] = st.session_state.get("session_id") or str(uuid.uuid4())

predicted_skin = st.session_state.get("predicted_skin")
if predicted_skin:
    st.success(f"Predicted Skin Type: {predicted_skin}")
else:
    st.info("Upload or capture a selfie, then click Predict to continue.")

st.session_state["session_id"] = st.session_state.get("session_id") or str(uuid.uuid4())

predicted_skin = st.session_state.get("predicted_skin")
if predicted_skin:
    st.success(f"Predicted Skin Type: {predicted_skin}")
else:
    st.info("Upload or capture a selfie, then click Predict to continue.")

# Navigation control: Next button (gated)
st.markdown("<div class='fade-in'>", unsafe_allow_html=True)
col_next1, col_next2 = st.columns([1, 4])
with col_next1:
    next_clicked = st.button("Next →", key="next_to_details")
st.markdown("</div>", unsafe_allow_html=True)

if next_clicked:
    if st.session_state.get("predicted_skin_from_ai"):
        if not try_switch_page("pages/2_Details.py"):
            st.info("Use the sidebar to open 'Details' if automatic navigation fails.")
    else:
        st.warning("Please predict your skin type first before moving to the next step.")

render_footer()
