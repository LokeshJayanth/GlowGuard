import io
import os
import json
import uuid
import hashlib
import random
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import requests
from PIL import Image
import streamlit as st
import numpy as np

try:
    import onnxruntime as ort  # type: ignore
except Exception:  # pragma: no cover
    ort = None

DATA_DIR = "data"
UPLOAD_DIR = "uploads"
DB_PATH = os.path.join(DATA_DIR, "glowguard.db")
MODELS_DIR = "models"
DEFAULT_ONNX_MODEL = os.path.join(MODELS_DIR, "skin_type.onnx")

SKIN_TYPES = ["Normal", "Dry", "Oily", "Sensitive"]

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(MODELS_DIR, exist_ok=True)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            name TEXT,
            initial_skin TEXT,
            predicted_skin TEXT,
            city TEXT,
            region TEXT,
            lat REAL,
            lon REAL,
            created_at TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS environment (
            session_id TEXT,
            temperature REAL,
            uv_index REAL,
            humidity REAL,
            pm25 REAL,
            FOREIGN KEY(session_id) REFERENCES sessions(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS scores (
            session_id TEXT,
            stress INTEGER,
            glow INTEGER,
            FOREIGN KEY(session_id) REFERENCES sessions(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS responses (
            session_id TEXT,
            question TEXT,
            answer TEXT,
            FOREIGN KEY(session_id) REFERENCES sessions(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
            session_id TEXT,
            image_path TEXT,
            image_sha256 TEXT,
            FOREIGN KEY(session_id) REFERENCES sessions(id)
        )
        """
    )
    conn.commit()
    conn.close()


def _secrets_file_exists() -> bool:
    """Return True if a secrets.toml exists in user or project .streamlit dirs.
    This lets us avoid calling st.secrets when no file exists (prevents Streamlit warning).
    """
    try:
        home = os.path.expanduser("~")
        user_path = os.path.join(home, ".streamlit", "secrets.toml")
        proj_path = os.path.join(os.getcwd(), ".streamlit", "secrets.toml")
        return os.path.exists(user_path) or os.path.exists(proj_path)
    except Exception:
        return False

@st.cache_data(ttl=300)
def get_ip_location() -> Dict:
    try:
        r = requests.get("https://ipinfo.io", timeout=4)
        if r.ok:
            return r.json()
    except Exception:
        pass
    return {}


@st.cache_data(ttl=300)
def get_environment(lat: float, lon: float) -> Dict:
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            "&current_weather=true&hourly=uv_index_10m,relative_humidity_2m,pm2_5"
        )
        r = requests.get(url, timeout=6)
        if r.ok:
            return r.json()
    except Exception:
        pass
    return {}


def predict_skin_type(image_bytes: Optional[bytes], name_seed: str) -> str:
    rng = random.Random()
    if image_bytes:
        digest = hashlib.sha256(image_bytes).digest()
        seed_int = int.from_bytes(digest[:8], "big")
        rng.seed(seed_int)
    else:
        rng.seed(hash(name_seed))
    return rng.choice(SKIN_TYPES)


# -----------------------------
# Optional ONNX pretrained model support
# -----------------------------
def load_onnx_model(model_path: str = DEFAULT_ONNX_MODEL):
    """Load ONNX model if available. Returns (session, input_name, input_shape) or (None, None, None)."""
    if ort is None:
        return None, None, None
    try:
        if not os.path.exists(model_path):
            return None, None, None
        sess = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])  # type: ignore
        input_name = sess.get_inputs()[0].name
        input_shape = sess.get_inputs()[0].shape
        return sess, input_name, input_shape
    except Exception:
        return None, None, None


def preprocess_image_for_onnx(image_bytes: bytes, input_shape) -> Optional[np.ndarray]:
    """Preprocess image to NCHW/float32 according to model input. Assumes RGB 224x224 if unknown."""
    try:
        # Load image with PIL
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        # Determine target size
        if isinstance(input_shape, list) and len(input_shape) == 4 and input_shape[2] and input_shape[3]:
            target_h = int(input_shape[2])
            target_w = int(input_shape[3])
        else:
            target_h = target_w = 224
        img = img.resize((target_w, target_h))
        arr = np.array(img).astype(np.float32) / 255.0
        # NCHW
        arr = np.transpose(arr, (2, 0, 1))[None, ...]
        return arr
    except Exception:
        return None


def get_openweather_api_key() -> Optional[str]:
    """Return OpenWeather API key from Streamlit secrets or environment variable.
    Priority: st.secrets -> os.environ["OPENWEATHER_API_KEY"].
    """
    # Prefer environment first to avoid secrets warning when using env vars
    try:
        env_key = os.environ.get("OPENWEATHER_API_KEY")
        if env_key:
            return env_key
    except Exception:
        pass
    if _secrets_file_exists():
        try:
            key = st.secrets.get("OPENWEATHER_API_KEY")
            if key:
                return key
        except Exception:
            pass
    return None

def predict_skin_type_onnx(image_bytes: Optional[bytes]) -> Optional[str]:
    if image_bytes is None:
        return None
    sess, input_name, input_shape = load_onnx_model()
    if sess is None or input_name is None:
        return None
    arr = preprocess_image_for_onnx(image_bytes, input_shape)
    if arr is None:
        return None
    try:
        outputs = sess.run(None, {input_name: arr})  # type: ignore
        logits = outputs[0].squeeze()
        # Softmax to probabilities
        exp = np.exp(logits - np.max(logits))
        probs = exp / np.sum(exp)
        idx = int(np.argmax(probs))
        # Map index to SKIN_TYPES (assumes 4 classes)
        if idx >= 0 and idx < len(SKIN_TYPES):
            return SKIN_TYPES[idx]
        return SKIN_TYPES[0]
    except Exception:
        return predict_skin_type(image_bytes, "")


# -----------------------------
# Heuristic predictor (no-ML)
# -----------------------------
def predict_skin_type_heuristic(image_bytes: Optional[bytes]) -> Optional[str]:
    """Very lightweight heuristic using simple color statistics.
    - Sensitive: elevated redness (R - G mean > threshold)
    - Oily: higher highlights (top percentile in V channel) and higher brightness variance
    - Dry: low median saturation and slightly higher texture (S variance low, V median mid)
    - Normal: otherwise
    Returns one of SKIN_TYPES or None if image_bytes missing/invalid.
    """
    if image_bytes is None:
        return None
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        arr = np.array(img).astype(np.float32)
        # RGB stats
        r = arr[..., 0]; g = arr[..., 1]; b = arr[..., 2]
        red_minus_green = float(np.mean(r - g))
        # HSV stats
        import cv2  # lazy import
        hsv = cv2.cvtColor(arr.astype(np.uint8), cv2.COLOR_RGB2HSV)
        h, s, v = hsv[..., 0].astype(np.float32), hsv[..., 1].astype(np.float32), hsv[..., 2].astype(np.float32)
        sat_med = float(np.median(s))
        val_med = float(np.median(v))
        val_std = float(np.std(v))
        # highlights proportion (top 5% V)
        thresh = np.percentile(v, 95)
        highlights_ratio = float(np.mean(v >= thresh))

        # Simple rules (tunable)
        if red_minus_green > 12.0 and sat_med > 60:
            return "Sensitive"
        if highlights_ratio > 0.08 and val_std > 35:
            return "Oily"
        if sat_med < 40 and 90 < val_med < 180:
            return "Dry"
        return "Normal"
    except Exception:
        return None


def predict_skin_type_smart(image_bytes: Optional[bytes], name_seed: str, mode: str = "auto") -> str:
    """Dispatcher for skin prediction.
    mode: 'auto' | 'onnx' | 'heuristic' | 'simulated'
    - auto: try onnx, else heuristic, else simulated
    - onnx: only onnx (fallback to heuristic then simulated)
    - heuristic: color-statistics heuristic
    - simulated: legacy simulated baseline
    """
    if mode in ("auto", "onnx"):
        pred = predict_skin_type_onnx(image_bytes)
        if pred:
            return pred
        if mode == "onnx":
            # fallback path: heuristic -> simulated
            pred_h = predict_skin_type_heuristic(image_bytes)
            if pred_h:
                return pred_h
            return predict_skin_type(image_bytes, name_seed)
    if mode == "heuristic":
        pred_h = predict_skin_type_heuristic(image_bytes)
        if pred_h:
            return pred_h
        return predict_skin_type(image_bytes, name_seed)
    if mode == "auto":
        pred_h = predict_skin_type_heuristic(image_bytes)
        if pred_h:
            return pred_h
    # default simulated baseline
    return predict_skin_type(image_bytes, name_seed)


def adaptive_questions_for(skin: str) -> Tuple[List[str], List[str], List[str]]:
    questions = {
        "Dry": [
            "Do you feel flakiness?",
            "Do you use hydrating masks?",
            "Do you drink enough water daily?",
        ],
        "Oily": [
            "Do you get pimples often?",
            "Do you use oil-control products?",
            "Do you use mattifying sunscreen?",
        ],
        "Sensitive": [
            "Does your skin get red easily?",
            "Do you use fragrance-free products?",
            "Any reactions to new products?",
        ],
        "Normal": [
            "Any dryness or oiliness in certain areas?",
            "Do you use masks/exfoliators?",
            "Any pigmentation spots?",
        ],
    }

    product_questions = [
        "What moisturizer do you currently use?",
        "What sunscreen do you use?",
        "Any serums/facial oils?",
        "Any acne/pigmentation/anti-aging treatments?",
        "Do you use anti-pollution products?",
    ]

    lifestyle_questions = [
        "Time spent outdoors daily (College/Gym/Work/Other)?",
        "Hours of exercise per week?",
        "Hours of sleep per night?",
        "Stress level (Low/Medium/High)?",
        "Water intake per day (<1L,1-2L,2-3L,>3L)?",
    ]

    return questions.get(skin, []), product_questions, lifestyle_questions


def save_image(session_id: str, image_bytes: Optional[bytes]) -> Tuple[Optional[str], Optional[str]]:
    if not image_bytes:
        return None, None
    sha = hashlib.sha256(image_bytes).hexdigest()
    file_path = os.path.join(UPLOAD_DIR, f"{session_id}.png")
    try:
        with open(file_path, "wb") as f:
            f.write(image_bytes)
        return file_path, sha
    except Exception:
        return None, sha


def save_session(
    session_id: str,
    name: str,
    initial_skin: str,
    predicted_skin: str,
    city: str,
    region: str,
    lat: float,
    lon: float,
    metrics: Dict,
    scores: Dict,
    responses: Dict[str, str],
    image_info: Tuple[Optional[str], Optional[str]],
) -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO sessions (id, name, initial_skin, predicted_skin, city, region, lat, lon, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            session_id,
            name,
            initial_skin,
            predicted_skin,
            city,
            region,
            float(lat),
            float(lon),
            datetime.utcnow().isoformat(timespec="seconds") + "Z",
        ),
    )
    cur.execute(
        "INSERT INTO environment (session_id, temperature, uv_index, humidity, pm25) VALUES (?,?,?,?,?)",
        (
            session_id,
            float(metrics.get("temperature", 25)),
            float(metrics.get("uv_index", 0)),
            float(metrics.get("humidity", 0)),
            float(metrics.get("pm25", 0)),
        ),
    )
    cur.execute(
        "INSERT INTO scores (session_id, stress, glow) VALUES (?,?,?)",
        (
            session_id,
            int(scores.get("stress", 0)),
            int(scores.get("glow", 0)),
        ),
    )
    for q, a in (responses or {}).items():
        # Ensure answer is a string; serialize complex types to JSON
        if not isinstance(a, str):
            try:
                a_str = json.dumps(a, ensure_ascii=False)
            except Exception:
                a_str = str(a)
        else:
            a_str = a
        cur.execute(
            "INSERT INTO responses (session_id, question, answer) VALUES (?,?,?)",
            (session_id, str(q), a_str),
        )
    path, sha = image_info
    if path or sha:
        cur.execute(
            "INSERT INTO files (session_id, image_path, image_sha256) VALUES (?,?,?)",
            (session_id, path, sha),
        )
    conn.commit()
    conn.close()


def safe_int(val: Optional[str], default: int) -> int:
    try:
        return int(str(val).strip())
    except Exception:
        return default


# -----------------------------
# UI/UX Helpers (Shared)
# -----------------------------
CUSTOM_CSS = """
<style>
/* General */
.block-container {padding-top: 1.5rem; padding-bottom: 2rem;}
h1, h2, h3 { letter-spacing: 0.2px; }

/* Cards */
.card {
  background: var(--secondary-background-color, #f6f8fa);
  padding: 1rem 1.25rem;
  border-radius: 12px;
  border: 1px solid rgba(0,0,0,0.05);
}
.card + .card { margin-top: 1rem; }

/* Buttons */
.stButton > button {
  border-radius: 10px; padding: 0.5rem 1rem; font-weight: 600;
}

/* Animated primary button */
.btn-primary > button {
  background: #3b82f6 !important; color: white !important; border: none;
  transition: transform 0.08s ease-out, box-shadow 0.2s ease-in-out;
  box-shadow: 0 2px 6px rgba(59,130,246,0.25);
}
.btn-primary > button:hover { transform: translateY(-1px); box-shadow: 0 6px 14px rgba(59,130,246,0.35); }
.btn-primary > button:active { transform: translateY(0); }

/* Section fade-in */
.fade-in { animation: fadein 260ms ease-in 1; }
@keyframes fadein { from { opacity: 0; transform: translateY(4px);} to { opacity: 1; transform: translateY(0);} }

/* Metrics */
[data-testid="stMetricValue"] { font-weight: 700; }

/* File uploader width */
[data-testid="stFileUploader"] { max-width: 540px; }

/* Hero */
.hero {
  padding: 0.75rem 1rem;
  background: linear-gradient(180deg, rgba(59,130,246,0.06), rgba(255,255,255,0));
  border: 1px solid rgba(0,0,0,0.04);
  border-radius: 14px;
  display: flex; gap: 1rem; align-items: center;
}
.hero .emoji { font-size: 1.8rem; }
.hero h2 { margin: 0; }
.hero p { margin: 0.25rem 0 0; color: #475569; }

/* Footer */
.footer { color: #64748b; text-align: center; margin-top: 28px; font-size: 0.9rem; }
</style>
"""


def inject_css():
    """Inject shared CSS styles."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def render_brand_header(title: str, subtitle: str = "", emoji: str = "✨"):
    """Render a branded hero header."""
    st.markdown(
        f"""
        <div class=\"hero\">
          <div class=\"emoji\">{emoji}</div>
          <div>
            <h2>{title}</h2>
            {f'<p>{subtitle}</p>' if subtitle else ''}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_footer(text: str = "Made with ❤️ for a cleaner, brighter skin journey — GlowGuard+"):
    st.markdown(f"<div class=\"footer\">{text}</div>", unsafe_allow_html=True)


def render_sidebar_brand(brand: str = "GlowGuard+", emoji: str = "🌍"):
    st.sidebar.markdown(f"### {emoji} {brand}")
    st.sidebar.caption("Smart Skin & Environment Insights")


def try_switch_page(path: str) -> bool:
    """Attempt to switch page. Returns True if succeeded, else False (fallback to instructions)."""
    try:
        # Streamlit 1.22+ provides st.switch_page
        import streamlit as st
        st.switch_page(path)
        return True
    except Exception:
        return False


# -----------------------------
# Google APIs: Geocoding + Air Quality (optional)
# -----------------------------
def get_google_api_key() -> Optional[str]:
    """Return Google API key from environment variable or Streamlit secrets.
    Priority: os.environ["GOOGLE_API_KEY"] -> st.secrets.
    Preferring environment first avoids Streamlit's "No secrets file" notice when an env var is already set.
    """
    try:
        env_key = os.environ.get("GOOGLE_API_KEY")
        if env_key:
            return env_key
    except Exception:
        pass
    # Only access st.secrets if a secrets file actually exists
    if _secrets_file_exists():
        try:
            return st.secrets.get("GOOGLE_API_KEY")
        except Exception:
            return None
    return None


def geocode_with_google(address: str) -> Optional[Dict]:
    key = get_google_api_key()
    if not key or not address:
        return None
    try:
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        r = requests.get(url, params={"address": address, "key": key}, timeout=6)
        if r.ok:
            data = r.json()
            if data.get("status") == "OK" and data.get("results"):
                loc = data["results"][0]["geometry"]["location"]
                return {"lat": loc.get("lat"), "lon": loc.get("lng"), "formatted_address": data["results"][0].get("formatted_address")}
    except Exception:
        pass
    return None


def air_quality_with_google(lat: float, lon: float) -> Optional[Dict]:
    key = get_google_api_key()
    if not key:
        return None
    try:
        url = f"https://airquality.googleapis.com/v1/currentConditions:lookup?key={key}"
        payload = {
            "location": {"latitude": float(lat), "longitude": float(lon)},
            "extraComputations": ["POLLUTANT_CONCENTRATIONS", "HEALTH_RECOMMENDATIONS"],
            "languageCode": "en",
        }
        headers = {"Content-Type": "application/json"}
        r = requests.post(url, json=payload, headers=headers, timeout=8)
        if r.ok:
            data = r.json()
            return data
    except Exception:
        pass
    return None
