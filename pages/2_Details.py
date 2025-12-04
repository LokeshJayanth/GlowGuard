import streamlit as st
from lib import (
    adaptive_questions_for,
    SKIN_TYPES,
    inject_css,
    render_brand_header,
    render_footer,
    render_sidebar_brand,
    try_switch_page,
)

st.set_page_config(page_title="GlowGuard+ • Details", page_icon="📝")

st.title("📝 Details")
st.caption("Step 2 of 4")

inject_css()
render_sidebar_brand()
render_brand_header(
    title="Step 2 — Details",
    subtitle="Answer adaptive questions to personalize your recommendations and scores.",
    emoji="📝",
)

with st.sidebar:
    st.subheader("Session")
    name = st.text_input("Name", value=st.session_state.get("name", "User"))
    st.session_state["name"] = name
    predicted_skin = st.session_state.get("predicted_skin", st.session_state.get("skin_type_initial", "Normal"))
    st.write(f"Predicted: {predicted_skin}")

if not st.session_state.get("predicted_skin_from_ai"):
    st.warning("Please complete 'Upload & Predict' first.")
    st.stop()

predicted_skin = st.session_state.get("predicted_skin", "Normal")
responses = st.session_state.get("responses", {})

st.markdown("### Phase 1.5 – Smart Dashboard Questions")

def radio_with_other(label: str, options: list, key: str):
    """Single-choice control that does NOT auto-select. Includes placeholder and 'Other'."""
    placeholder = "— Select —"
    opts = [placeholder] + options + ["Other"]
    existing = responses.get(key, "")
    # Determine default index from existing value
    if isinstance(existing, str) and existing in options:
        default_index = opts.index(existing)
        other_prefill = ""
    elif isinstance(existing, str) and existing and existing not in options:
        # Previously entered custom
        default_index = opts.index("Other")
        other_prefill = existing
    else:
        default_index = 0
        other_prefill = ""
    choice = st.selectbox(label, opts, index=default_index, key=key)
    if choice == "Other":
        return st.text_input("Add details", value=other_prefill, key=f"{key}_other")
    if choice == placeholder:
        return ""
    return choice

def multiselect_with_other(label: str, options: list, key: str):
    prev = responses.get(key, {})
    prev_selected = prev.get("selected", []) if isinstance(prev, dict) else (prev if isinstance(prev, list) else [])
    selected = st.multiselect(label, options + ["Other"], default=prev_selected)
    custom = ""
    if "Other" in selected:
        prev_other = prev.get("other", "") if isinstance(prev, dict) else ""
        custom = st.text_input("Add details", value=prev_other, key=f"{key}_other")
    # Store both selections and custom
    return {"selected": [o for o in selected if o != "Other"], "other": custom}

with st.container():
    st.markdown("#### 1) Dryness / Oiliness")
    res = multiselect_with_other(
        "Any dryness or oiliness in certain areas of your face?",
        ["Forehead", "Nose / T-zone", "Cheeks", "Chin / Jawline"],
        key="areas_oil_dry",
    )
    responses["areas_oil_dry"] = res

    st.markdown("#### 2) Pigmentation Spots")
    responses["pigmentation_spots"] = radio_with_other(
        "Do you have any pigmentation spots?",
        ["Yes, light pigmentation", "Yes, dark pigmentation", "No"],
        key="pigmentation_spots",
    )

    st.markdown("#### 3) Sunscreen Usage")
    responses["sunscreen_usage"] = radio_with_other(
        "What sunscreen do you use?",
        ["SPF 15", "SPF 30", "SPF 50", "I don’t use sunscreen"],
        key="sunscreen_usage",
    )

    st.markdown("#### 4) Treatments")
    responses["treatments"] = multiselect_with_other(
        "Are you using any acne, pigmentation, or anti-aging treatments?",
        ["Acne treatment", "Pigmentation treatment", "Anti-aging treatment", "None"],
        key="treatments",
    )

    st.markdown("#### 5) Time Spent Outdoors Daily")
    responses["time_outdoors_daily"] = radio_with_other(
        "How many hours do you spend outdoors daily (college/gym/work/other)?",
        ["<1 hour", "1–3 hours", "3–6 hours", ">6 hours"],
        key="time_outdoors_daily",
    )

    st.markdown("#### 6) Hours of Sleep Per Night")
    responses["sleep_hours"] = radio_with_other(
        "How many hours do you sleep on average per night?",
        ["<5 hours", "5–6 hours", "6–7 hours", "7–8 hours", ">8 hours"],
        key="sleep_hours",
    )

    st.markdown("#### 7) Water Intake Per Day")
    responses["water_intake"] = radio_with_other(
        "How much water do you drink daily?",
        ["<1 liter", "1–2 liters", "2–3 liters", ">3 liters"],
        key="water_intake",
    )

    st.markdown("#### 8) Regular Skincare Products")
    responses["regular_products"] = multiselect_with_other(
        "What skincare products do you regularly use? (Name/brand/type)",
        ["Moisturizer", "Sunscreen", "Serum", "Cleanser", "Toner", "Face Mask", "Eye Cream"],
        key="regular_products",
    )
    # Structured fields for key items
    structured_keys = ["Serum", "Sunscreen", "Moisturizer"]
    prev_details = responses.get("regular_products_details", {}) if isinstance(responses.get("regular_products_details"), dict) else {}
    details_out = {}
    # Only show forms for selected structured items
    selected_items = responses["regular_products"].get("selected", []) if isinstance(responses["regular_products"], dict) else []
    if any(item in selected_items for item in structured_keys):
        st.markdown("<div class='card'>Provide details for selected products.</div>", unsafe_allow_html=True)
    for item in structured_keys:
        if item in selected_items:
            st.markdown(f"##### {item} details")
            cols = st.columns(3)
            with cols[0]:
                name_val = st.text_input("Name", value=(prev_details.get(item, {}).get("name", "")), key=f"prod_{item}_name")
            with cols[1]:
                brand_val = st.text_input("Brand", value=(prev_details.get(item, {}).get("brand", "")), key=f"prod_{item}_brand")
            with cols[2]:
                type_val = st.text_input("Type", value=(prev_details.get(item, {}).get("type", "")), key=f"prod_{item}_type")
            details_out[item] = {"name": name_val, "brand": brand_val, "type": type_val}
    if details_out:
        responses["regular_products_details"] = details_out

    st.markdown("#### 9) Stress / Activity")
    responses["daily_activities"] = multiselect_with_other(
        "What activities do you do daily? (Select all that apply)",
        ["College / School", "Gym / Workout", "Work / Office", "Outdoor sports", "Meditation / Yoga"],
        key="daily_activities",
    )
    responses["stress_level"] = radio_with_other(
        "How stressed do you feel daily?",
        ["Low", "Moderate", "High", "Very High"],
        key="stress_level",
    )

st.session_state["responses"] = responses

st.success("Responses saved in session.")

col_next1, col_next2 = st.columns([1, 3])
with col_next1:
    if st.button("Save & Next →", type="primary"):
        # Validate required fields for structured products
        selected_items = responses.get("regular_products", {}).get("selected", []) if isinstance(responses.get("regular_products"), dict) else []
        details = responses.get("regular_products_details", {}) if isinstance(responses.get("regular_products_details"), dict) else {}
        required = ["Serum", "Sunscreen", "Moisturizer"]
        missing_msgs = []
        for item in required:
            if item in selected_items:
                d = details.get(item, {})
                if not d.get("name") or not d.get("brand") or not d.get("type"):
                    missing_msgs.append(f"- {item}: please fill Name, Brand, and Type")
        if missing_msgs:
            st.error("Please complete the following before continuing:\n" + "\n".join(missing_msgs))
        else:
            if not try_switch_page("pages/3_Environment.py"):
                st.info("Use the sidebar to open 'Environment' if automatic navigation fails.")

render_footer()

render_footer()
