# GlowGuard

GlowGuard is an AI-assisted skincare analysis system that processes user images, captures profile details, analyzes environmental conditions (UV, humidity, AQI), and provides personalized skincare recommendations.  
The project includes both a Streamlit-based dashboard prototype and a backend/API workflow.

---

## 🌟 Features

### 🔹 Streamlit Dashboard (Prototype)
- Light-themed UI powered by `.streamlit/config.toml`
- Selfie upload with simulated AI skin analysis
- Adaptive follow-up questions (skin type, products, lifestyle)
- Automatic location detection via IP
- Environment insights using Open-Meteo API  
  (UV, humidity, PM2.5 — with safe fallback values)
- Personalized skincare recommendations
- Glow & Stress scoring system
- Clean card-based layout with responsive design

### 🔹 Backend (FastAPI)
- Processes uploaded user images
- Extracts skin-type indicators
- Handles user profile & condition data
- Integrates environment-based recommendation logic

### 🔹 Frontend (React + Tailwind)
- Clean, responsive dashboard for insights
- Charts, cards, and metrics to display skincare results
- Seamless API integration with FastAPI backend

---

## 🚀 Quickstart

### 1️⃣ Install dependencies
```bash
pip install -r requirements.txt
