# Keystroke Dynamics Authentication System

This project implements a **Python-based keystroke dynamics authentication system**, designed to verify a user's identity based on their typing rhythm when entering a fixed passphrase.  
It includes data collection, feature extraction, and Siamese neural network–based model training — all in Python.

---

## 🚀 Features
- Real-time **keystroke data collection** using the `keyboard` module  
- Fixed passphrase repeated entry to capture typing behavior  
- Automatic feature extraction (hold time, latency, flight time)  
- **Siamese Neural Network** for verification (same/different user)  
- Works fully offline and stores data locally as `.csv` files

---

## 🧩 Project Structure

ECE-Project-1/
│
├── KEYLOGGER_keyboard.py # Record keystrokes and save to CSV
├── LOGGER.py # Alternate logger with cleaner timestamps
├── Siamese_Keystroke_seen_users.ipynb # Jupyter notebook for model training
├── utils/ # (Optional) helper functions for feature extraction
├── data/
│ ├── raw/ # Raw CSV logs (per attempt)
│ └── processed/ # Feature-extracted data ready for training
└── requirements.txt # Python dependencies


## 🛠️ Installation

### 1. Clone the Repository
bash
git clone https://github.com/Eric-Gellasch/ECE-Project-1.git
cd ECE-Project-1
python -m venv venv
source venv/bin/activate    # (Linux/macOS)
venv\Scripts\activate       # (Windows)
pip install -r requirements.txt

Typical required packages:
keyboard
numpy
pandas
torch
scikit-learn
matplotlib


## ⌨️ Step 1 — Collect Typing Data
- Run the logger to capture key press and release events: python KEYLOGGER_keyboard.py or python LOGGER.py

## Notes
- Default passphrase: "Football123$"
- The script will record multiple attempts (e.g., 5–10).
- Each attempt’s data is saved as a CSV file under data/raw/.
- Make sure to run it in a terminal with keyboard focus (no background interruptions).

---


## 🧠 Step 2 — Preprocess the Data
- You can use Python or Jupyter Notebook to clean and align your data:
- import pandas as pd
- from utils import extract_features
 
- df = pd.read_csv('data/raw/sample.csv')
- features = extract_features(df)
- features.to_csv('data/processed/features.csv', index=False)

## Typical features:
- Hold Time: release_time - press_time
- Down–Down Latency: time between consecutive key presses
- Up–Down Latency: gap between key releases and next key presses

---


## 🤖 Step 3 — Train the Siamese Neural Network

Open and run the notebook:
Siamese_Keystroke_seen_users.ipynb

---

It will:
- Load processed feature vectors
- Create positive (same user) and negative (different user) pairs
- Train a Siamese network to learn a similarity metric
- Save the trained model as model.pth
