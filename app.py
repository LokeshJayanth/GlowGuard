import io
import hashlib
import random
from typing import Dict, List, Optional, Tuple

import requests
import streamlit as st
from PIL import Image
from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file

from lib import inject_css, render_brand_header, render_footer, init_db
import os
import sqlite3
import json
import uuid
from datetime import datetime

# -----------------------------
# Page configuration & Styling
# -----------------------------
st.set_page_config(
    page_title="GlowGuard+ Dashboard",
    layout="wide",
    page_icon="🌍",
)

# Subtle CSS for card-like sections and cleaner visuals
CUSTOM_CSS = """
<style>
/***** General tweaks *****/
.block-container {padding-top: 1.5rem; padding-bottom: 2rem;}
h1, h2, h3 { letter-spacing: 0.2px; }

/***** Cards *****/
.card {
  background: var(--secondary-background-color, #f6f8fa);
  padding: 1rem 1.25rem;
  border-radius: 12px;
  border: 1px solid rgba(0,0,0,0.05);
}
.card + .card { margin-top: 1rem; }

/***** Metrics tweaks *****/
[data-testid="stMetricValue"] { font-weight: 700; }

/***** File uploader width fix *****/
[data-testid="stFileUploader"] { max-width: 540px; }

/***** Buttons *****/
.stButton > button {
  border-radius: 10px; padding: 0.5rem 1rem; font-weight: 600;
}

.small-note { color: #64748b; font-size: 0.9rem; }

/* Hero header */
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

/* Stepper */
.stepper { display: flex; gap: 12px; align-items: center; margin: 12px 0 20px; flex-wrap: wrap; }
.step {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 10px; border-radius: 999px;
  background: #eef2ff; color: #1e3a8a; border: 1px solid #dbeafe;
  font-weight: 600; font-size: 0.9rem;
}
.step.active { background: #dbeafe; color: #1d4ed8; border-color: #bfdbfe; }
.step.done { background: #dcfce7; color: #166534; border-color: #bbf7d0; }
.step .num { background: white; color: inherit; border-radius: 999px; padding: 2px 8px; border: 1px solid rgba(0,0,0,0.05); }

/* Footer */
.footer { color: #64748b; text-align: center; margin-top: 28px; font-size: 0.9rem; }
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
inject_css()

# -----------------------------
# Helpers & Caching
# -----------------------------
DATA_DIR = "data"
UPLOAD_DIR = "uploads"
DB_PATH = os.path.join(DATA_DIR, "glowguard.db")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

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
    # responses
    for q, a in (responses or {}).items():
        cur.execute(
            "INSERT INTO responses (session_id, question, answer) VALUES (?,?,?)",
            (session_id, q, a),
        )
    # files
    path, sha = image_info
    if path or sha:
        cur.execute(
            "INSERT INTO files (session_id, image_path, image_sha256) VALUES (?,?,?)",
            (session_id, path, sha),
        )
    conn.commit()
    conn.close()
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

SKIN_TYPES = ["Normal", "Dry", "Oily", "Sensitive"]

# Deterministic simulated prediction based on image content
# Falls back to random with a name-based seed if no image

def predict_skin_type(image_bytes: Optional[bytes], name_seed: str) -> str:
    rng = random.Random()
    if image_bytes:
        digest = hashlib.sha256(image_bytes).digest()
        seed_int = int.from_bytes(digest[:8], "big")
        rng.seed(seed_int)
    else:
        rng.seed(hash(name_seed))
    return rng.choice(SKIN_TYPES)


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


# -----------------------------
# Sidebar: User Profile & Controls
# -----------------------------
from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file

from lib import inject_css, render_brand_header, render_footer
inject_css()
st.title("🌍 GlowGuard+ Dashboard")

# Hero header
render_brand_header(
    title="GlowGuard+ — Smart Skin & Environment Insights",
    subtitle="Upload your selfie, answer a few tailored questions, and get personalized care tips powered by your local environment.",
    emoji="✨",
)

init_db()

# Home landing for multipage navigation
with st.container():
    st.markdown("## Welcome 👋")
    st.write("Use the steps below to complete your analysis. You can also use the sidebar 'Pages' menu.")
    st.divider()
    st.markdown("### Get Started")
    st.page_link("pages/1_Upload_and_Predict.py", label="Step 1: Upload & Predict", icon="📤")
    st.page_link("pages/2_Details.py", label="Step 2: Details", icon="📝")
    st.page_link("pages/3_Environment.py", label="Step 3: Environment", icon="🌍")
    st.page_link("pages/4_Results.py", label="Step 4: Results", icon="✅")
    st.page_link("pages/5_History.py", label="History", icon="📚")
    st.page_link("pages/7_Route_Weather.py", label="Route • Weather • Recs", icon="🧭")

render_footer()
st.stop()

# -----------------------------
# Section 1: Upload Selfie & Prediction
# -----------------------------
st.subheader("1️⃣ Upload Selfie for AI Skin Analysis")
# Stepper state
active_step = 1
if st.session_state.get("uploaded_image"):
    active_step = 2
if st.session_state.get("predicted_skin_from_ai"):
    active_step = 3
if st.session_state.get("analyzed"):
    active_step = 4

def render_stepper(active: int):
    steps = [
        (1, "Upload"),
        (2, "Predict"),
        (3, "Details"),
        (4, "Analyze & Save"),
    ]
    html = ['<div class="stepper">']
    for num, label in steps:
        cls = "step"
        if st.session_state.get("analyzed") and num <= 4:
            cls += " done"
        elif num == active:
            cls += " active"
        elif num < active:
            cls += " done"
        html.append(f'<div class="{cls}"><span class="num">{num}</span> {label}</div>')
    html.append('</div>')
    st.markdown("\n".join(html), unsafe_allow_html=True)

render_stepper(active_step)
col_u1, col_u2 = st.columns([1, 2])
with col_u1:
    uploaded_file = st.file_uploader("Choose a selfie image...", type=["jpg", "jpeg", "png"], accept_multiple_files=False)
with col_u2:
    st.markdown("<div class='card'>Upload a clear, front-facing image in good lighting for best results. Supported formats: JPG/PNG.</div>", unsafe_allow_html=True)

image_bytes: Optional[bytes] = None
if uploaded_file is not None:
    img = Image.open(uploaded_file)
    st.image(img, caption="Uploaded Selfie", use_column_width=True)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    image_bytes = buf.getvalue()
    st.session_state["uploaded_image"] = image_bytes
else:
    image_bytes = st.session_state.get("uploaded_image")

# Predict skin type (simulated) when user clicks button below (requires image)
predict_col1, predict_col2 = st.columns([1,3])
with predict_col1:
    predict_clicked = st.button("🔍 Predict Skin", disabled=(image_bytes is None), help="Runs a simulated AI prediction.")
if predict_clicked:
    if image_bytes is None:
        st.warning("Please upload a selfie first.")
    else:
        predicted_skin = predict_skin_type(image_bytes, name_seed=name or "User")
        st.session_state["predicted_skin"] = predicted_skin
        st.session_state["predicted_skin_from_ai"] = True
        st.session_state["session_id"] = st.session_state.get("session_id") or str(uuid.uuid4())

predicted_skin = st.session_state.get("predicted_skin", st.session_state.get("skin_type_initial", "Normal"))
if st.session_state.get("predicted_skin_from_ai"):
    st.success(f"Predicted Skin Type: {predicted_skin}")
else:
    st.info("Upload a selfie and click 'Predict Skin' to proceed to detailed questions.")

# -----------------------------
# Section 2: Adaptive Follow-Up Questions
# -----------------------------
responses: Dict[str, str] = st.session_state.get("responses", {})
if st.session_state.get("predicted_skin_from_ai"):
    skin_qs, product_qs, lifestyle_qs = adaptive_questions_for(predicted_skin)
    all_qs = skin_qs + product_qs + lifestyle_qs
    if all_qs:
        st.subheader("2️⃣ Answer the Follow-Up Questions")
        with st.container():
            cols = st.columns(2)
            for idx, q in enumerate(all_qs):
                default_val = responses.get(q, "")
                with cols[idx % 2]:
                    responses[q] = st.text_input(q, value=default_val, key=f"q_{idx}", help="Leave blank if not applicable.")
        st.session_state["responses"] = responses

# -----------------------------
# Section 3: Location Detection & Override
# -----------------------------
st.subheader("3️⃣ Environment & Recommendations")

if analyze_save and "location_data" not in st.session_state:
    st.session_state["location_data"] = get_ip_location()

location_data = st.session_state.get("location_data", {})
city = location_data.get("city", "Unknown")
region = location_data.get("region", "")

lat_default, lon_default = 28.6139, 77.2090  # Delhi defaults if IP lookup fails
try:
    if "loc" in location_data:
        lat_str, lon_str = location_data["loc"].split(",")
        lat_default, lon_default = float(lat_str), float(lon_str)
except Exception:
    pass

lat = st.number_input("Latitude:", value=float(st.session_state.get("lat", lat_default)), format="%.6f", help="You can override detected latitude.")
lon = st.number_input("Longitude:", value=float(st.session_state.get("lon", lon_default)), format="%.6f", help="You can override detected longitude.")

st.session_state["lat"], st.session_state["lon"] = lat, lon
st.write(f"📍 Location detected: {city}, {region}")

# -----------------------------
# Section 4: Environment Data
# -----------------------------
if analyze_save:
    st.session_state["env_data"] = get_environment(lat, lon)

env_data = st.session_state.get("env_data", {})

# Extract metrics with fallbacks
current_weather = env_data.get("current_weather", {})

def _extract_hourly_latest(env: Dict, key: str) -> Optional[float]:
    try:
        times = env.get("hourly", {}).get("time", [])
        series = env.get("hourly", {}).get(key, [])
        if times and series:
            return float(series[-1])
    except Exception:
        pass
    return None

uv_index = _extract_hourly_latest(env_data, "uv_index_10m")
humidity = _extract_hourly_latest(env_data, "relative_humidity_2m")
pm25 = _extract_hourly_latest(env_data, "pm2_5")

fallback_used = False
if uv_index is None:
    uv_index = random.randint(0, 11)
    fallback_used = True
if humidity is None:
    humidity = random.randint(20, 80)
    fallback_used = True
if pm25 is None:
    pm25 = random.randint(10, 150)
    fallback_used = True

if analyze_save:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🌡 Temperature (°C)", current_weather.get("temperature", 25))
    c2.metric("☀️ UV Index", int(uv_index))
    c3.metric("💧 Humidity (%)", int(humidity))
    c4.metric("🌫 PM2.5", int(pm25))

    if fallback_used:
        st.caption("Some environment values use smart fallbacks due to network/API limits.")

# -----------------------------
# Section 5: Recommendations
# -----------------------------
recs: List[str] = []
if uv_index > 6:
    recs.append("☀️ High UV! Apply SPF 50+ sunscreen.")
elif uv_index > 3:
    recs.append("☀️ Moderate UV. Apply SPF 30+ if outdoors.")

if humidity < 30:
    recs.append("💧 Low humidity, hydrate your skin well.")
elif humidity > 70:
    recs.append("💧 High humidity, use oil-free products.")

if pm25 > 50:
    recs.append("🌫 Poor air quality, apply anti-pollution serum.")

if predicted_skin == "Oily":
    recs.append("✅ Oily skin detected. Use lightweight moisturizers.")
elif predicted_skin == "Dry":
    recs.append("✅ Dry skin detected. Apply rich hydrating creams.")
elif predicted_skin == "Sensitive":
    recs.append("⚠️ Sensitive skin, avoid harsh products.")

st.subheader("💡 Personalized Recommendations")
if analyze_save:
    if recs:
        for r in recs:
            st.write(f"- {r}")
    else:
        st.write("No recommendations were generated.")
else:
    st.info("Recommendations will appear after you click 'Analyze & Save'.")

# -----------------------------
# Section 6: Stress & Glow Scores
# -----------------------------
def safe_int(val: Optional[str], default: int) -> int:
    try:
        return int(str(val).strip())
    except Exception:
        return default

sleep_hours = safe_int(responses.get("Hours of sleep per night?", "7"), 7)
activity_hours = safe_int(responses.get("Hours of exercise per week?", "2"), 2)
workload_level = (responses.get("Stress level (Low/Medium/High)?", "Medium") or "Medium").strip()

stress_score = 50
if sleep_hours < 6:
    stress_score += 20
if activity_hours > 8:
    stress_score += 10
if workload_level.lower() == "high":
    stress_score += 20
stress_score = min(stress_score, 100)

glow_score = max(0, int(100 - stress_score - uv_index * 5 - pm25 * 0.5))

st.subheader("📊 Stress & Glow Score")
if analyze_save:
    sc1, sc2 = st.columns(2)
    sc1.metric("Stress Score", int(stress_score))
    sc2.metric("Glow Score", int(glow_score))

st.session_state["metrics"] = {
    "uv_index": uv_index,
    "humidity": humidity,
    "pm25": pm25,
    "temperature": current_weather.get("temperature", 25),
}
st.session_state["recs"] = recs
st.session_state["scores"] = {"stress": int(stress_score), "glow": int(glow_score)}

# -----------------------------
# Save to DB when analysis runs
# -----------------------------
if analyze_save:
    session_id = st.session_state.get("session_id") or str(uuid.uuid4())
    st.session_state["session_id"] = session_id
    # Save image (if any)
    image_info = save_image(session_id, image_bytes)
    try:
        save_session(
            session_id=session_id,
            name=name,
            initial_skin=skin_type_initial,
            predicted_skin=predicted_skin,
            city=city,
            region=region,
            lat=lat,
            lon=lon,
            metrics=st.session_state.get("metrics", {}),
            scores=st.session_state.get("scores", {}),
            responses=st.session_state.get("responses", {}),
            image_info=image_info,
        )
        st.success(f"Saved analysis to local database: {DB_PATH}")
        st.session_state["analyzed"] = True
    except Exception as e:
        st.warning(f"Could not save to database: {e}")

# -----------------------------
# Section 7: Summary & Finish
# -----------------------------
st.divider()
st.subheader("✅ Summary")

with st.expander("View captured data"):
    st.write({
        "name": name,
        "initial_skin": skin_type_initial,
        "predicted_skin": predicted_skin,
        "location": {"city": city, "region": region, "lat": lat, "lon": lon},
        "metrics": st.session_state.get("metrics", {}),
        "scores": st.session_state.get("scores", {}),
        "answers_count": len(responses),
    })

if analyze_save:
    st.balloons()
    st.success("Analysis saved! Scroll up for details or explore the summary above.")

# Footer
st.markdown(
    """
    <div class="footer">Made with ❤️ for a cleaner, brighter skin journey — GlowGuard+</div>
    """,
    unsafe_allow_html=True,
)
