# GlowGuard+ Dashboard

A neat, light-themed Streamlit dashboard that guides users through selfie upload, AI (simulated) skin analysis, adaptive follow-up questions, automatic location detection, environment insights (UV, humidity, PM2.5), personalized recommendations, and Glow/Stress scoring.

## Quickstart

1. Create and activate a virtual environment (optional but recommended).
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run the app:

```bash
streamlit run app.py
```

The app opens at http://localhost:8501

## Features

- Light theme via `.streamlit/config.toml`
- Sidebar profile, selfie upload, and a single "Run Analysis" button
- Simulated AI skin prediction with consistent randomness per image
- Adaptive follow-up questions (skin-type, product, and lifestyle)
- Automatic location via IP with manual override
- Environment data via Open-Meteo (with graceful fallbacks)
- Personalized recommendations based on skin type and environment
- Stress and Glow scores with intuitive metrics
- Clean layout with cards and sections; responsive on wide layout

## Notes
- No API keys required. IP info uses `ipinfo.io` free endpoint; Open-Meteo requires none.
- If network calls fail, the app falls back to sensible mock values and shows a notice.
