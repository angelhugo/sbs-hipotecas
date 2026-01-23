import os
import re
import sys
import requests
import pandas as pd
from datetime import date, timedelta

SBS_URL = "https://www.sbs.gob.pe/app/pp/EstadisticasSAEEPortal/Paginas/TIActivaTipoCreditoEmpresa.aspx?tip=B"
CSV_PATH = "data/rates.csv"

# Mapeo flexible de cómo puede aparecer cada entidad en columnas
SERIES = {
    "promedio": ["Promedio"],
    "bcp": ["Bancom", "BCP", "Banco de Crédito", "Banco de Credito"],
    "bbva": ["BBVA"],
    "interbank": ["Interbank"],
    "scotiabank": ["Scotiabank"],
}

def ensure_csv_exists():
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    if not os.path.exists(CSV_PATH):
        with open(CSV_PATH, "w", encoding="utf-8") as f:
            f.write("date,series,rate\n")

def load_csv() -> pd.DataFrame:
    ensure_csv_exists()
    df = pd.read_csv(CSV_PATH)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df

def save_csv(df: pd.DataFrame):
    out = df.copy()
    out["date"] = out["date"].astype(str)
    out.to_csv(CSV_PATH, index=False)

def send_telegram(text: str):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
