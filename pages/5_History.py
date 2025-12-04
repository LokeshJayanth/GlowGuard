import os
import sqlite3
import streamlit as st
from PIL import Image

from lib import DB_PATH, UPLOAD_DIR

st.set_page_config(page_title="GlowGuard+ • History", page_icon="📚")

st.title("📚 History")
st.caption("Browse saved analyses")

if not os.path.exists(DB_PATH):
    st.info("No database found yet. Run an analysis to create history.")
    st.stop()

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
cur.execute("SELECT id, name, initial_skin, predicted_skin, city, region, lat, lon, created_at FROM sessions ORDER BY created_at DESC")
rows = cur.fetchall()

if not rows:
    st.info("No sessions saved yet.")
    st.stop()

selected = st.selectbox("Select a session", [f"{r[8]} • {r[1]} • {r[3]} ({r[0][:8]})" for r in rows])
idx = [f"{r[8]} • {r[1]} • {r[3]} ({r[0][:8]})" for r in rows].index(selected)
session = rows[idx]
session_id = session[0]

st.subheader("Session Summary")
col1, col2 = st.columns([2,1])
with col1:
    st.write({
        "id": session_id,
        "name": session[1],
        "initial_skin": session[2],
        "predicted_skin": session[3],
        "location": {"city": session[4], "region": session[5], "lat": session[6], "lon": session[7]},
        "created_at": session[8],
    })

with col2:
    img_path = os.path.join(UPLOAD_DIR, f"{session_id}.png")
    if os.path.exists(img_path):
        st.image(Image.open(img_path), caption="Uploaded Selfie", use_column_width=True)
    else:
        st.caption("No image saved for this session.")

cur.execute("SELECT temperature, uv_index, humidity, pm25 FROM environment WHERE session_id=?", (session_id,))
env = cur.fetchone()
cur.execute("SELECT stress, glow FROM scores WHERE session_id=?", (session_id,))
scores = cur.fetchone()
cur.execute("SELECT question, answer FROM responses WHERE session_id=?", (session_id,))
qa = cur.fetchall()
conn.close()

st.subheader("Environment & Scores")
c1, c2, c3, c4 = st.columns(4)
if env:
    c1.metric("🌡 Temp (°C)", env[0])
    c2.metric("☀️ UV Index", int(env[1]))
    c3.metric("💧 Humidity (%)", int(env[2]))
    c4.metric("🌫 PM2.5", int(env[3]))
else:
    st.caption("No environment data stored.")

if scores:
    s1, s2 = st.columns(2)
    s1.metric("Stress", int(scores[0]))
    s2.metric("Glow", int(scores[1]))

st.subheader("Responses")
if qa:
    for q, a in qa:
        st.write(f"- **{q}**: {a}")
else:
    st.caption("No responses saved.")
