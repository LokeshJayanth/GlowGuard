# environment_page.py
import random
import streamlit as st
from lib import (
    init_db,
    get_ip_location,
    get_environment,
    inject_css,
    render_brand_header,
    render_footer,
    render_sidebar_brand,
    geocode_with_google,
    air_quality_with_google,
    get_google_api_key,
    get_openweather_api_key,
)
import requests
import folium
from streamlit_folium import st_folium
import streamlit.components.v1 as components

st.set_page_config(page_title="GlowGuard+ • Environment", page_icon="🌍")
init_db()

st.title("🌍 Environment")
st.caption("Step 3 of 4")

inject_css()
render_sidebar_brand()
render_brand_header(
    title="Step 3 — Environment",
    subtitle="Detect your location and fetch UV, humidity, PM2.5, and temperature.",
    emoji="🌍",
)

# Sidebar session info
with st.sidebar:
    st.subheader("Session")
    name = st.text_input("Name", value=st.session_state.get("name", "User"))
    st.session_state["name"] = name

st.markdown("Auto-detect your location or enter it manually, then fetch environment data.")

# Optional: API keys from environment or secrets (handled inside helpers)
google_key = get_google_api_key()
openweather_key = get_openweather_api_key()

addr = st.text_input("Address/Place (optional)", value=st.session_state.get("address", ""), help="Geocode to precise coordinates if Google API key is configured.")
col_geo1, col_geo2 = st.columns([1,1])
with col_geo1:
    geo_btn = st.button("📍 Detect Location via IP")
with col_geo2:
    geo_google_btn = st.button("🗺️ Geocode with Google", disabled=not bool(google_key))

if not google_key:
    st.caption(
        "Tip: Provide GOOGLE_API_KEY in .streamlit/secrets.toml or as environment variable to enable Google geocoding and Google air-quality."
    )

# Detect location via IP
if geo_btn:
    st.session_state["location_data"] = get_ip_location()

# Geocode with Google if address provided
if geo_google_btn and addr:
    g = geocode_with_google(addr) if google_key else None
    if g:
        st.session_state["lat"], st.session_state["lon"] = g["lat"], g["lon"]
        st.session_state["address"] = g.get("formatted_address", addr)
        st.success(f"Geocoded: {st.session_state['address']}")
    else:
        st.warning("Could not geocode the address. Check API key and address string.")

# Build defaults from IP location if available
location_data = st.session_state.get("location_data", {})
city = location_data.get("city", "Unknown")
region = location_data.get("region", "")

# Default to New Delhi coords if nothing detected
lat_default, lon_default = 28.6139, 77.2090
try:
    if "loc" in location_data:
        lat_str, lon_str = location_data["loc"].split(",")
        lat_default, lon_default = float(lat_str), float(lon_str)
except Exception:
    pass

# Let user fine-tune lat/lon
lat = st.number_input("Latitude", value=float(st.session_state.get("lat", lat_default)), format="%.6f")
lon = st.number_input("Longitude", value=float(st.session_state.get("lon", lon_default)), format="%.6f")

# Save in session
st.session_state["lat"], st.session_state["lon"] = lat, lon
detected_label = st.session_state.get("address") or f"{city}, {region}"
st.write(f"Detected: {detected_label}")

"""Render interactive map and handle click-to-select coordinates"""
st.subheader("📍 Location Map")
m = folium.Map(location=[lat, lon], zoom_start=12, tiles="OpenStreetMap")
folium.Marker([lat, lon], tooltip="Your Location", popup=detected_label).add_to(m)
folium.Circle(location=[lat, lon], radius=500, color="#3186cc", fill=True, fill_opacity=0.1).add_to(m)
map_data = st_folium(m, width="100%", height=400)

# If user clicks on the map, update both local and session lat/lon
try:
    if map_data and map_data.get("last_clicked"):
        lat = float(map_data["last_clicked"]["lat"])
        lon = float(map_data["last_clicked"]["lng"])
        st.session_state["lat"], st.session_state["lon"] = lat, lon
        st.info(f"Selected on map: {lat:.6f}, {lon:.6f}. Click '🔄 Fetch Environment & Weather' to refresh.")
except Exception:
    pass

# Fetch environment + optional Google AQ + OpenWeather
if st.button("🔄 Fetch Environment & Weather"):
    # Open-Meteo (no key needed)
    st.session_state["env_data"] = get_environment(lat, lon)
    # Google Air Quality (if key present)
    if google_key:
        st.session_state["google_aq"] = air_quality_with_google(lat, lon)
    
    # OpenWeather current weather (if key present)
    if openweather_key:
        try:
            ow_url = (
                "http://api.openweathermap.org/data/2.5/weather"
                f"?lat={lat}&lon={lon}&appid={openweather_key}&units=metric"
            )
            ow = requests.get(ow_url, timeout=8).json()
            st.session_state["openweather"] = ow
        except Exception as e:
            st.warning(f"OpenWeather fetch failed: {e}")

# Read back session data
env_data = st.session_state.get("env_data", {})
google_aq = st.session_state.get("google_aq")
ow = st.session_state.get("openweather")
current_weather = env_data.get("current_weather", {})

# Optional: Google Maps (Embed API) preview if key present
if google_key:
    st.subheader("🗺️ Google Map Preview")
    try:
        # Prefer coordinates; if address exists, you may also use the 'place' mode
        # View mode centered on lat/lon
        center = f"{lat:.6f},{lon:.6f}"
        gmap_url = (
            "https://www.google.com/maps/embed/v1/view"
            f"?key={google_key}&center={center}&zoom=12&maptype=roadmap"
        )
        components.iframe(gmap_url, height=400)
    except Exception:
        pass

# Nearby Places (Google Places API) — optional
st.markdown("---")
st.subheader("📍 Search Nearby Places (Google Places API)")
col_np1, col_np2, col_np3 = st.columns([2,1,1])
with col_np1:
    places_query = st.text_input("What to search?", value=st.session_state.get("places_query", "dermatologist"), help="e.g., dermatologist, pharmacy, skin clinic")
with col_np2:
    radius_m = st.number_input("Radius (meters)", min_value=100, max_value=10000, value=int(st.session_state.get("places_radius", 2000)), step=100)
with col_np3:
    do_search = st.button("🔎 Search Nearby")

if do_search:
    st.session_state["places_query"] = places_query
    st.session_state["places_radius"] = int(radius_m)
    if not google_key:
        st.warning("Google key not found. Set GOOGLE_API_KEY to use Places API.")
    else:
        try:
            nearby_url = (
                "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
                f"?location={lat},{lon}&radius={int(radius_m)}&keyword={requests.utils.quote(places_query)}&key={google_key}"
            )
            resp = requests.get(nearby_url, timeout=10)
            data = resp.json() if resp.ok else {}
            st.session_state["places"] = data.get("results", [])
            if not st.session_state["places"]:
                st.info("No places found for this query/radius.")
        except Exception as e:
            st.warning(f"Places search failed: {e}")

places = st.session_state.get("places", [])
if places:
    st.caption(f"Found {len(places)} places")
    # Map with result markers
    m2 = folium.Map(location=[lat, lon], zoom_start=13, tiles="OpenStreetMap")
    folium.Marker([lat, lon], tooltip="You", icon=folium.Icon(color="blue")).add_to(m2)
    for p in places[:30]:
        try:
            gl = p.get("geometry", {}).get("location", {})
            plat, plon = gl.get("lat"), gl.get("lng")
            name = p.get("name", "Place")
            rating = p.get("rating")
            vicinity = p.get("vicinity") or p.get("formatted_address")
            popup = f"<b>{name}</b>" + (f"<br/>⭐ {rating}" if rating else "") + (f"<br/>{vicinity}" if vicinity else "")
            if plat is not None and plon is not None:
                folium.Marker([plat, plon], tooltip=name, popup=popup, icon=folium.Icon(color="green", icon="plus", prefix="fa")).add_to(m2)
        except Exception:
            pass
    st_folium(m2, width="100%", height=380)

    # Simple list of results
    for p in places[:20]:
        name = p.get("name", "Place")
        rating = p.get("rating")
        vicinity = p.get("vicinity") or p.get("formatted_address") or ""
        st.write(f"• {name}" + (f" — ⭐ {rating}" if rating else "") + (f" — {vicinity}" if vicinity else ""))

# Extract hourly values (Open-Meteo style) with fallbacks to random if missing
uv_index = None
humidity = None
pm25 = None
try:
    times = env_data.get("hourly", {}).get("time", [])
    uv_series = env_data.get("hourly", {}).get("uv_index_10m", [])
    rh_series = env_data.get("hourly", {}).get("relative_humidity_2m", [])
    pm_series = env_data.get("hourly", {}).get("pm2_5", [])
    if times and uv_series:
        uv_index = float(uv_series[-1])
    if times and rh_series:
        humidity = float(rh_series[-1])
    if times and pm_series:
        pm25 = float(pm_series[-1])
except Exception:
    pass

# Prefer Google AQ for PM2.5 and AQI if available
aqi = None
if google_aq:
    try:
        indexes = google_aq.get("indexes", []) or []
        if indexes:
            aqi = indexes[0].get("aqi") or indexes[0].get("aqiDisplay")
        pollutants = google_aq.get("pollutants", {}) or {}
        pm25_node = pollutants.get("pm25") or pollutants.get("PM25")
        if pm25_node and isinstance(pm25_node, dict):
            conc = pm25_node.get("concentration") or {}
            val = conc.get("value")
            if val is not None:
                pm25 = float(val)
    except Exception:
        pass

# If OpenWeather provides values, prefer them for temperature/humidity
if ow:
    try:
        ow_temp = ow.get("main", {}).get("temp")
        ow_hum = ow.get("main", {}).get("humidity")
        if ow_temp is not None:
            current_weather["temperature"] = ow_temp
        if ow_hum is not None:
            humidity = ow_hum
    except Exception:
        pass

# Final fallbacks
if uv_index is None:
    uv_index = random.randint(0, 11)
if humidity is None:
    humidity = random.randint(20, 80)
if pm25 is None:
    pm25 = random.randint(10, 150)

# Show metrics
c1, c2, c3, c4 = st.columns(4)
c1.metric("🌡 Temp (°C)", current_weather.get("temperature", 25))
c2.metric("☀️ UV Index", int(uv_index))
c3.metric("💧 Humidity (%)", int(humidity))
c4.metric("🌫 PM2.5 (µg/m³)", int(pm25))
if aqi is not None:
    st.metric("🧭 AQI (Google)", aqi)

# persist metrics in session for downstream pages
st.session_state["metrics"] = {
    "temperature": current_weather.get("temperature", 25),
    "uv_index": uv_index,
    "humidity": humidity,
    "pm25": pm25,
    "aqi": aqi,
}

st.info("Proceed to the 'Results' page to generate recommendations and save this session data.")
render_footer()
