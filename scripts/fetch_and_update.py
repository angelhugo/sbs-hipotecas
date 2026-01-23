import os
import re
import sys
import json
import requests
import pandas as pd
from datetime import datetime, timedelta, date
from playwright.sync_api import sync_playwright

SBS_URL = "https://www.sbs.gob.pe/app/pp/EstadisticasSAEEPortal/Paginas/TIActivaTipoCreditoEmpresa.aspx?tip=B"

# Mapeo “nombre en SBS” -> “nombre interno”
# En la tabla suele aparecer “Bancom” para BCP (Banco de Crédito). :contentReference[oaicite:1]{index=1}
SERIES = {
    "Promedio": "promedio",
    "Bancom": "bcp",
    "BBVA": "bbva",
    "Interbank": "interbank",
    "Scotiabank": "scotiabank",
}

CSV_PATH = "data/rates.csv"

def send_telegram(text: str):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Telegram secrets missing; skipping telegram.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(url, json={
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": False
    }, timeout=30)
    r.raise_for_status()

def ensure_csv_exists():
    if not os.path.exists(CSV_PATH):
        os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
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
    df2 = df.copy()
    df2["date"] = df2["date"].astype(str)
    df2.to_csv(CSV_PATH, index=False)

def three_day_down(points):
    # points: list of (date, rate) sorted asc
    if len(points) < 4:
        return False
    last4 = points[-4:]
    r0, r1, r2, r3 = [x[1] for x in last4]
    return (r1 < r0) and (r2 < r1) and (r3 < r2)

def build_dashboard_url(base_url: str, series: str, days: int = 90):
    to_d = date.today()
    from_d = to_d - timedelta(days=days)
    return f"{base_url}/?series={series}&from={from_d.isoformat()}&to={to_d.isoformat()}"

def parse_rate(text: str) -> float:
    # Ej: "7.45%" o "7,45%" (por si cambia)
    t = text.strip().replace("%", "").replace(",", ".")
    return float(t)

def fetch_for_date(target_date: date):
    """
    Abre SBS, selecciona fecha, y lee la fila Hipotecarios -> Préstamos hipotecarios para vivienda.
    Devuelve: {"date": YYYY-MM-DD, "rates": {"promedio": 7.1, "bcp": 7.2, ...}}
    """
    target_str = target_date.strftime("%d/%m/%Y")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(SBS_URL, wait_until="domcontentloaded")

        # 1) Setear fecha en el input del RadDatePicker (hay varias variantes; intentamos las comunes)
        # Buscamos un input con placeholder dd/mm/aaaa o similar.
        # Si el selector cambia, esto es lo único que normalmente hay que ajustar.
        date_inputs = page.locator("input").filter(has_text=re.compile("")).all()
        date_input = None
        for i in range(len(date_inputs)):
            el = date_inputs[i]
            try:
                placeholder = (el.get_attribute("placeholder") or "").lower()
                if "dd" in placeholder and "mm" in placeholder and "aaaa" in placeholder:
                    date_input = el
                    break
            except:
                continue

        # fallback: primer input visible tipo texto
        if date_input is None:
            candidates = page.locator("input[type='text']").all()
            for el in candidates:
                try:
                    if el.is_visible():
                        date_input = el
                        break
                except:
                    pass

        if date_input is None:
            browser.close()
            raise RuntimeError("No pude ubicar el input de fecha en la página SBS.")

        # Escribimos la fecha y enviamos ENTER para disparar el postback
        date_input.click()
        date_input.fill(target_str)
        page.keyboard.press("Enter")

        # Esperamos a que cambie el encabezado “... al DD/MM/AAAA”
        page.wait_for_timeout(1200)

        html = page.content()
        browser.close()

    # 2) Validar que la página refleje la fecha
    if target_str not in html:
        # a veces no hay dato para ese día (fin de semana/feriado), o no tomó el postback
        return None

    # 3) Extraer la tabla de “Hipotecarios” y “Préstamos hipotecarios para vivienda”
    # Leemos todas las tablas y buscamos la que contenga esas palabras.
    tables = pd.read_html(html)
    target_table = None

    for t in tables:
        joined = " ".join([str(x) for x in t.values.flatten().tolist()])
        if ("Hipotecarios" in joined) and ("Préstamos hipotecarios para vivienda" in joined):
            target_table = t
            break

    if target_table is None:
        return None

    # La tabla suele venir con primera columna tipo crédito y luego bancos.
    # Normalizamos nombres de columnas.
    cols = [str(c).strip() for c in target_table.columns]
    target_table.columns = cols

    # Encontrar la fila exacta
    row_idx = None
    for i in range(len(target_table)):
        first = str(target_table.iloc[i, 0])
        if "Préstamos hipotecarios para vivienda" in first:
            row_idx = i
            break

    if row_idx is None:
        return None

    row = target_table.iloc[row_idx]

    rates = {}
    for col_name, internal in SERIES.items():
        # Buscamos columna que contenga ese nombre
        matched_col = None
        for c in cols:
            if col_name.lower() in c.lower():
                matched_col = c
                break
        if matched_col is None:
            continue

        raw = str(row[matched_col]).strip()
        if raw in ("-", "nan", "NaN", ""):
            continue

        try:
            rates[internal] = parse_rate(raw)
        except:
            continue

    if not rates:
        return None

    return {"date": target_date, "rates": rates}

def upsert_rates(df: pd.DataFrame, target_date: date, rates: dict) -> pd.DataFrame:
    rows = []
    for series, rate in rates.items():
        rows.append({"date": target_date, "series": series, "rate": float(rate)})

    new = pd.DataFrame(rows)
    if df.empty:
        out = new
    else:
        out = pd.concat([df, new], ignore_index=True)
        out = out.drop_duplicates(subset=["date", "series"], keep="last")

    out = out.sort_values(["series", "date"]).reset_index(drop=True)
    return out

def summarize_last_3_days(points):
    # points: list of (date, rate) sorted asc
    if len(points) < 3:
        return None
    last3 = points[-3:]
    d0, r0 = last3[0]
    d2, r2 = last3[-1]
    delta = r2 - r0
    arrow = "↓" if delta < 0 else ("↑" if delta > 0 else "→")
    return f"Últimos 3 datos: {d0.isoformat()} {r0:.2f}% → {d2.isoformat()} {r2:.2f}% ({arrow} {delta:+.2f} pp)"

def main():
    base_url = os.environ.get("PUBLIC_BASE_URL", "https://angelhugo.github.io/sbs-hipotecas").rstrip("/")

    df = load_csv()

    # Intento principal: HOY. Si HOY no tiene dato, probamos AYER, etc. (hasta 5 días atrás).
    fetched = None
    for back in range(0, 6):
        d = date.today() - timedelta(days=back)
        try:
            fetched = fetch_for_date(d)
        except Exception as e:
            print("Error fetching:", e)
            fetched = None
        if fetched is not None:
            break

    if fetched is None:
        print("No se pudo obtener datos recientes desde SBS.")
        sys.exit(0)

    df = upsert_rates(df, fetched["date"], fetched["rates"])

    # Mantener al menos 400 días para “último año” con colchón
    cutoff = date.today() - timedelta(days=400)
    df = df[df["date"] >= cutoff].reset_index(drop=True)

    save_csv(df)

    # Evaluar alertas (promedio y 4 bancos)
    targets = ["promedio", "bcp", "bbva", "interbank", "scotiabank"]
alerts = []

for s in targets:
    sdf = df[df["series"] == s].sort_values("date")
    pts = list(zip(sdf["date"].tolist(), sdf["rate"].tolist()))

    if three_day_down(pts):
        last_rate = pts[-1][1]
        summary = summarize_last_3(pts)
        alerts.append((s, last_rate, summary))
