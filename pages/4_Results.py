import streamlit as st
from lib import save_session, save_image, safe_int, inject_css, render_brand_header, render_footer, render_sidebar_brand

st.set_page_config(page_title="GlowGuard+ • Results", page_icon="✅")

st.title("✅ Results & Save")
st.caption("Step 4 of 4")

inject_css()
render_sidebar_brand()
render_brand_header(
    title="Step 4 — Results",
    subtitle="Review your recommendations, scores, and save your analysis.",
    emoji="✅",
)

with st.sidebar:
    st.subheader("Session")
    name = st.text_input("Name", value=st.session_state.get("name", "User"))
    st.session_state["name"] = name

predicted_skin = st.session_state.get("predicted_skin", st.session_state.get("skin_type_initial", "Normal"))
metrics = st.session_state.get("metrics", {})
responses = st.session_state.get("responses", {})
lat = st.session_state.get("lat")
lon = st.session_state.get("lon")
location_data = st.session_state.get("location_data", {})
city = location_data.get("city", "Unknown")
region = location_data.get("region", "")

if not metrics:
    st.warning("Please complete 'Environment' to fetch metrics.")
    st.stop()

uv_index = float(metrics.get("uv_index", 0))
humidity = float(metrics.get("humidity", 0))
pm25 = float(metrics.get("pm25", 0))

# Recommendations
recs = []
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
for r in recs:
    st.write(f"- {r}")

# Scores
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
col1, col2 = st.columns(2)
col1.metric("Stress Score", int(stress_score))
col2.metric("Glow Score", int(glow_score))

# Product details summary
details = responses.get("regular_products_details", {}) if isinstance(responses.get("regular_products_details"), dict) else {}
if details:
    st.subheader("🧴 Product Details (Summary)")
    # Build a small table
    try:
        import pandas as pd
        rows = []
        for k, v in details.items():
            rows.append({"Product": k, "Name": v.get("name", ""), "Brand": v.get("brand", ""), "Type": v.get("type", "")})
        df = pd.DataFrame(rows, columns=["Product", "Name", "Brand", "Type"])
        st.table(df)
    except Exception:
        for k, v in details.items():
            st.write(f"- {k}: Name={v.get('name','')}, Brand={v.get('brand','')}, Type={v.get('type','')}")

# Save
if st.button("💾 Save to Database", type="primary"):
    session_id = st.session_state.get("session_id")
    if not session_id:
        import uuid
        session_id = str(uuid.uuid4())
        st.session_state["session_id"] = session_id
    image_bytes = st.session_state.get("uploaded_image")
    image_info = save_image(session_id, image_bytes)
    try:
        save_session(
            session_id=session_id,
            name=name,
            initial_skin=st.session_state.get("skin_type_initial", "Normal"),
            predicted_skin=predicted_skin,
            city=city,
            region=region,
            lat=float(lat or 0.0),
            lon=float(lon or 0.0),
            metrics={
                "temperature": metrics.get("temperature", 25),
                "uv_index": uv_index,
                "humidity": humidity,
                "pm25": pm25,
            },
            scores={"stress": int(stress_score), "glow": int(glow_score)},
            responses=responses,
            image_info=image_info,
        )
        st.success("Saved! You can review it in the History page.")
        st.balloons()
    except Exception as e:
        st.error(f"Failed to save: {e}")

with st.expander("Summary"):
    st.write({
        "name": name,
        "predicted_skin": predicted_skin,
        "location": {"city": city, "region": region, "lat": lat, "lon": lon},
        "metrics": metrics,
        "sleep_hours": sleep_hours,
        "activity_hours": activity_hours,
        "workload_level": workload_level,
        "scores": {"stress": int(stress_score), "glow": int(glow_score)},
    })

render_footer()
