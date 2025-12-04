import os
import math
import time
import requests
import streamlit as st
import folium
from streamlit_folium import st_folium
import streamlit.components.v1 as components

from lib import (
    inject_css,
    render_brand_header,
    render_footer,
    get_google_api_key,
    get_openweather_api_key,
    geocode_with_google,
    get_ip_location,
)

st.set_page_config(page_title="GlowGuard+ • Route & Weather", page_icon="🧭")

inject_css()
render_brand_header(
    title="Route • Weather • Recommendations",
    subtitle="Plan a trip, see ETA, weather along the way, and get smart tips.",
    emoji="🧭",
)

# Keys
# IMPORTANT: Per user request, applying Google API key directly in code (not recommended for production)
GOOGLE_KEY = "AIzaSyBKBhoqZacP4x1i5lZ49Lq5yi0joxN5nVQ"
OW_KEY = get_openweather_api_key()

with st.sidebar:
    st.subheader("API Keys Status")
    st.write("Google Key: ✅ (code-applied)")
    st.write(f"OpenWeather Key: {'✅' if OW_KEY else '❌'}")

st.markdown("Enter a start and destination. We'll fetch route, ETA, weather along the path, and recommendations.")

col1, col2 = st.columns(2)
with col1:
    start_text = st.text_input("Start", value=st.session_state.get("route_start", "Cuddalore"))
with col2:
    dest_text = st.text_input("Destination", value=st.session_state.get("route_dest", "Coimbatore"))

col_a, col_b, col_c, col_d, col_e = st.columns([1,1,1,1,1])
with col_a:
    auto_update = st.checkbox("Auto update", value=st.session_state.get("route_auto", True), help="Fetch route automatically when inputs change")
    st.session_state["route_auto"] = auto_update
with col_b:
    sample_every_km = st.number_input("Sample every (km)", min_value=10, max_value=200, value=50, step=10, help="Weather checkpoints spacing along the route")
with col_c:
    units_metric = st.selectbox("Units", ["metric", "imperial"], index=0)
with col_d:
    refresh_btn = st.button("🔄 Refresh")
with col_e:
    use_ip_btn = st.button("📍 Use My Location (IP)", help="Detect approximate location via IP for Start and get weather")

# If user clicks 'Use My Location', set Start from IP city/coords and fetch weather there
current_place_weather = None
if use_ip_btn:
    ip = get_ip_location() or {}
    city = ip.get("city")
    region = ip.get("region") or ""
    loc = ip.get("loc")
    if city:
        st.session_state["route_start"] = city
        start_text = city
    if loc:
        try:
            lat_s, lon_s = [float(x) for x in loc.split(",")]
            current_place_weather = fetch_openweather(lat_s, lon_s, units=units_metric)
        except Exception:
            pass
    refresh_btn = True  # trigger fetching route on this run

# Utility: decode Google encoded polyline
# Source: public domain implementation adapted for clarity
# https://developers.google.com/maps/documentation/utilities/polylinealgorithm

def decode_polyline(polyline_str):
    index, lat, lng = 0, 0, 0
    coordinates = []
    changes = {'lat': 0, 'lng': 0}

    while index < len(polyline_str):
        for key in ['lat', 'lng']:
            shift = 0
            result = 0
            while True:
                b = ord(polyline_str[index]) - 63
                index += 1
                result |= (b & 0x1f) << shift
                shift += 5
                if b < 0x20:
                    break
            if (result & 1):
                changes[key] = ~(result >> 1)
            else:
                changes[key] = (result >> 1)
        lat += changes['lat']
        lng += changes['lng']
        coordinates.append((lat / 1e5, lng / 1e5))
    return coordinates


def haversine_km(a, b):
    R = 6371.0088
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def sample_points_along_path(points, every_km=50.0):
    if not points:
        return []
    sampled = [points[0]]
    dist_since = 0.0
    for i in range(1, len(points)):
        seg = haversine_km(points[i-1], points[i])
        dist_since += seg
        if dist_since >= every_km:
            sampled.append(points[i])
            dist_since = 0.0
    if sampled[-1] != points[-1]:
        sampled.append(points[-1])
    return sampled


def fetch_openweather(lat, lon, units="metric"):
    if not OW_KEY:
        return None
    try:
        url = (
            "http://api.openweathermap.org/data/2.5/weather"
            f"?lat={lat}&lon={lon}&appid={OW_KEY}&units={units}"
        )
        r = requests.get(url, timeout=8)
        if r.ok:
            return r.json()
    except Exception:
        pass
    return None


def get_directions(start_text, dest_text):
    """Fetch directions using Google Directions API.
    Strategy:
      1) Try with raw text origin/destination (lets Directions do geocoding).
      2) If that fails, geocode to coordinates and retry with lat/lon.
    Returns dict or None. Sets st.session_state["route_error"] with details on failure.
    """
    if not GOOGLE_KEY:
        st.session_state["route_error"] = "Missing GOOGLE_API_KEY"
        return None
    try:
        # First try: text origin/destination
        url1 = (
            "https://maps.googleapis.com/maps/api/directions/json"
            f"?origin={requests.utils.quote(start_text)}&destination={requests.utils.quote(dest_text)}&mode=driving&key={GOOGLE_KEY}"
        )
        r1 = requests.get(url1, timeout=12)
        if r1.ok:
            d1 = r1.json()
            if d1.get("status") == "OK":
                # Extract start/end from response
                try:
                    leg = d1["routes"][0]["legs"][0]
                    s_loc = leg["start_location"]; e_loc = leg["end_location"]
                    return {"start": (s_loc["lat"], s_loc["lng"]), "end": (e_loc["lat"], e_loc["lng"]), "routes": d1.get("routes", [])}
                except Exception:
                    return {"start": None, "end": None, "routes": d1.get("routes", [])}
            else:
                st.session_state["route_error"] = f"Directions(text) status={d1.get('status')} msg={d1.get('error_message','')}"
        else:
            st.session_state["route_error"] = f"HTTP {r1.status_code} from Directions(text)"

        # Fallback: explicit geocoding then coordinates
        start_geo = geocode_with_google(start_text)
        dest_geo = geocode_with_google(dest_text)
        if not start_geo or not dest_geo:
            if not st.session_state.get("route_error"):
                st.session_state["route_error"] = "Geocoding failed for start or destination"
            return None
        s_lat, s_lng = start_geo["lat"], start_geo["lon"]
        d_lat, d_lng = dest_geo["lat"], dest_geo["lon"]

        url2 = (
            "https://maps.googleapis.com/maps/api/directions/json"
            f"?origin={s_lat},{s_lng}&destination={d_lat},{d_lng}&mode=driving&key={GOOGLE_KEY}"
        )
        r2 = requests.get(url2, timeout=12)
        if r2.ok:
            d2 = r2.json()
            if d2.get("status") == "OK":
                return {"start": (s_lat, s_lng), "end": (d_lat, d_lng), "routes": d2.get("routes", [])}
            else:
                st.session_state["route_error"] = f"Directions(coords) status={d2.get('status')} msg={d2.get('error_message','')}"
        else:
            st.session_state["route_error"] = f"HTTP {r2.status_code} from Directions(coords)"
    except Exception as e:
        st.session_state["route_error"] = f"Exception: {e}"
    return None


route_info = st.session_state.get("route_info")

should_fetch = False
if refresh_btn:
    should_fetch = True
elif auto_update and GOOGLE_KEY and start_text.strip() and dest_text.strip():
    prev_s = st.session_state.get("route_start")
    prev_d = st.session_state.get("route_dest")
    if start_text != prev_s or dest_text != prev_d or route_info is None:
        should_fetch = True

if should_fetch:
    st.session_state["route_start"] = start_text
    st.session_state["route_dest"] = dest_text
    with st.spinner("Fetching route..."):
        route_info = get_directions(start_text, dest_text)
    if not route_info:
        err = st.session_state.get("route_error") or "Could not get directions. Check API key, billing, and place names."
        st.warning(err)
    else:
        st.session_state["route_info"] = route_info

if route_info:
    st.session_state["route_info"] = route_info
    routes = route_info["routes"]
    if not routes:
        st.info("No route found.")
    else:
        r0 = routes[0]
        leg0 = r0["legs"][0] if r0.get("legs") else None
        eta_text = leg0.get("duration", {}).get("text") if leg0 else ""
        eta_val = leg0.get("duration", {}).get("value") if leg0 else None
        dist_text = leg0.get("distance", {}).get("text") if leg0 else ""

        st.markdown("### Route Summary")
        c1, c2, c3 = st.columns(3)
        c1.metric("ETA", eta_text or "-")
        c2.metric("Distance", dist_text or "-")
        c3.metric("Waypoints", len(leg0.get("steps", [])) if leg0 else 0)

        # Decode overview polyline
        poly = r0.get("overview_polyline", {}).get("points")
        decoded = decode_polyline(poly) if poly else []
        sampled = sample_points_along_path(decoded, every_km=float(sample_every_km)) if decoded else []

        # Fetch weather at sampled points (limit to 12 to keep it quick)
        weather_points = []
        if sampled:
            limit = min(12, len(sampled))
            idxs = [round(i * (len(sampled)-1) / (limit-1)) for i in range(limit)] if limit > 1 else [0]
            for i in idxs:
                lat, lon = sampled[i]
                w = fetch_openweather(lat, lon, units=units_metric)
                weather_points.append({"lat": lat, "lon": lon, "weather": w})
                time.sleep(0.1)  # be kind to API

        # Recommendations
        recs = []
        if eta_val and eta_val > 5 * 3600:
            recs.append("Long drive ahead (>5h). Plan hydrating breaks and consider protective skincare.")
        if weather_points:
            any_rain = any((p["weather"] or {}).get("weather", [{}])[0].get("main", "").lower().find("rain") != -1 for p in weather_points)
            if any_rain:
                recs.append("Rain expected along the route. Carry water-resistant sunscreen and protective gear.")
            hot = any(((p["weather"] or {}).get("main", {}) or {}).get("temp", 0) for p in weather_points)
        
        # Full Google Map (JavaScript API) — interactive fallback/alternative
        if GOOGLE_KEY and start_text and dest_text:
            st.markdown("### Full Google Map (JavaScript API)")
            origin_js = requests.utils.quote(start_text)
            dest_js = requests.utils.quote(dest_text)
            html = f"""
            <div id="map" style="height:480px;width:100%;"></div>
            <script>
              function initMap() {{
                const directionsService = new google.maps.DirectionsService();
                const directionsRenderer = new google.maps.DirectionsRenderer();
                const map = new google.maps.Map(document.getElementById("map"), {{
                  zoom: 7,
                  center: {{ lat: 12.9716, lng: 77.5946 }}
                }});
                directionsRenderer.setMap(map);
                directionsService.route(
                  {{
                    origin: decodeURIComponent("{origin_js}"),
                    destination: decodeURIComponent("{dest_js}"),
                    travelMode: google.maps.TravelMode.DRIVING,
                  }},
                  (response, status) => {{
                    if (status === "OK") {{
                      directionsRenderer.setDirections(response);
                    }} else {{
                      const el = document.getElementById('map');
                      el.innerHTML = '<div style="padding:12px;color:#b91c1c;">Directions request failed: ' + status + '</div>';
                    }}
                  }}
                );
              }}
            </script>
            <script async defer src="https://maps.googleapis.com/maps/api/js?key={GOOGLE_KEY}&callback=initMap"></script>
            """
            components.html(html, height=520)


        # Current place weather (if obtained via IP)
        if current_place_weather:
            w = current_place_weather
            desc = (w.get("weather", [{}])[0].get("description") or "").title()
            temp = w.get("main", {}).get("temp")
            hum = w.get("main", {}).get("humidity")
            st.markdown("### Current Place Weather")
            cwx1, cwx2, cwx3 = st.columns(3)
            cwx1.metric("Condition", desc or "-")
            cwx2.metric("Temp", f"{temp}°{'C' if units_metric=='metric' else 'F'}" if temp is not None else "-")
            cwx3.metric("Humidity", f"{hum}%" if hum is not None else "-")

        # Recommendations display
        st.markdown("### Recommendations")
        if recs:
            for r in recs:
                st.write(f"- {r}")
        else:
            st.write("No special recommendations for this trip.")

render_footer()
