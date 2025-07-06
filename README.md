# 🏙️ CITYGPT: AI-Powered Urban Planning & Smart Mobility Simulator

“AI-powered traffic simulation tool for smart urban planning using NLP + A/B Street”

CITYGPT is an interactive, AI-powered traffic simulation platform that enables users to model and evaluate urban mobility scenarios using natural language. Designed for urban planners, researchers, and smart city stakeholders, it integrates NLP, geolocation, and traffic simulation to support data-driven decision-making.

---

## 🌟 Features

- 💬 Accepts trip requests in natural language using Gemini AI
- 📍 Converts place names to coordinates with OpenStreetMap’s Nominatim API
- 🚦 Simulates traffic and road closures using A/B Street
- 📊 Returns metrics like travel time, delay, and trip completion
- 🖥️ React-based chatbot UI with backend powered by FastAPI
- 🗃️ Saves scenario results to PostgreSQL for analysis and comparison

---

## 📸 Demo

> *(Screenshots coming soon)*  
> - Natural language input  
> - Road closure interface  
> - Simulation metrics dashboard  

---

## 🛠️ Installation

### 🔧 Backend (FastAPI)

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload

### Backend (FastAPI)
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```bash
cd frontend
npm install
npm start

```
🧠 Optional: A/B Street CLI
Download A/B Street from https://github.com/a-b-street/abstreet
Run the headless simulation engine:
```bash
./game --simulate &
```
▶️ Usage
Open the web app at http://localhost:3000
Enter a trip like:
"I want to bike from x to y for work."
Optionally block roads and rerun the simulation
View summary metrics: travel time, delays, and trip counts

⚙️ Technologies
-Python 3.9, FastAPI
-React.js, Axios
-Gemini AI (LLM API)
-OpenStreetMap Nominatim API
-A/B Street Simulation Engine
-PostgreSQL 13+
-Docker (optional)


👥 Contributors
-Mohamed Saber
-Omar Alaa
-Shahd Ahmed

Supervisor: Prof. Mohamed Taher Elrefaie
Mentor: TA Nadine Yousry
