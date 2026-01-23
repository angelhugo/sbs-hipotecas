import os
import re
import requests
import pandas as pd
from datetime import date, timedelta

SBS_URL = "https://www.sbs.gob.pe/app/pp/EstadisticasSAEEPortal/Paginas/TIActivaTipoCreditoEmpresa.aspx?tip=B"
CSV_PATH = "data/rates.csv"

# Cómo pueden aparecer las columnas en la tabla
SERIES_COLS = {
    "promedio": ["Promedio"],
    "bcp": ["Bancom", "BCP", "Banco de Crédito", "Banco de Credito"],
    "bbva": ["BBVA"],
    "interbank": ["Interbank"],
    "scotiabank": ["Scotiabank"],
}

TARGET_ROW_TEXT = "Préstamos hipotecarios para vivienda"

def send_telegram(text: str):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("No hay TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(
        url,
        json={"chat_id": chat_id, "text": text, "disable_web_page_preview": False},
        timeout=30
    )
    r.raise_for_status()

def ensure_csv():
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(CSV_PATH):
        with open(CSV_PATH, "w", encoding="utf-8") as f:
            f.write("date,series,rate\n")

def load_csv():
    ensure_csv()
    df = pd.read_csv(CSV_PATH)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df

def save_csv(df):
    out = df.copy()
    out["date"] = out["date"].astype(str)
    out.to_csv(CSV_PATH, index=False)

def parse_rate(x) -> float:
    s = str(x).strip().replace("%", "").replace(",", ".")
    return float(s)

def extract_date_from_html(html: str):
    # La página suele mostrar una fecha DD/MM/AAAA
    m = re.search(r"\b(\d{2})/(\d{2})/(\d{4})\b", html)
    if not m:
        return date.today()
    return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))

def fetch_latest_sbs():
    html = requests.get(SBS_URL, timeout=60).text
    d = extract_date_from_html(html)

    # Necesita lxml instalado en el workflow
    tables = pd.read_html(html)

    # Buscar tabla que contenga "Hipotecarios" y la fila target
    target = None
    for t in tables:
        flat = " ".join([str(v) for v in t.values.flatten().tolist()])
        if "Hipotecarios" in flat and TARGET_ROW_TEXT in flat:
            target = t
            break

    if target is None:
        return None

    cols = [str(c).strip() for c in target.columns]
    target.columns = cols

    # encontrar fila
    row = None
    for i in range(len(target)):
        first = str(target.iloc[i, 0])
        if TARGET_ROW_TEXT in first:
            row = target.iloc[i]
            break

    if row is None:
        return None

    rates = {}
    for series, candidates in SERIES_COLS.items():
        col = None
        for cand in candidates:
            for c in cols:
                if cand.lower() in c.lower():
                    col = c
                    break
            if col:
                break

        if not col:
            continue

        val = row[col]
        sval = str(val).strip()
        if sval in ("-", "nan", "NaN", ""):
            continue

        try:
            rates[series] = parse_rate(val)
        except:
            continue

    if not rates:
        return None

    return {"date": d, "rates": rates}

def upsert(df, d, rates: dict):
    new = pd.DataFrame([{"date": d, "series": s, "rate": float(r)} for s, r in rates.items()])
    if df.empty:
        out = new
    else:
        out = pd.concat([df, new], ignore_index=True)
        out = out.drop_duplicates(subset=["date", "series"], keep="last")
    out = out.sort_values(["series", "date"]).reset_index(drop=True)
    return out

def three_day_down(points):
    # points: [(date, rate)] asc
    if len(points) < 4:
        return False
    last4 = points[-4:]
    r0, r1, r2, r3 = [x[1] for x in last4]
    return (r1 < r0) and (r2 < r1) and (r3 < r2)

def summarize_last_3(points):
    if len(points) < 3:
        return "Aún no hay 3 datos."
    a = points[-3]
    b = points[-1]
    delta = b[1] - a[1]
    arrow = "↓" if delta < 0 else ("↑" if delta > 0 else "→")
    return f"Últimos 3 datos: {a[0]} {a[1]:.2f}% → {b[0]} {b[1]:.2f}% ({arrow} {delta:+.2f} pp)"

def build_dashboard_url(base_url: str, series: str, days: int = 90):
    to_d = date.today()
    from_d = to_d - timedelta(days=days)
    return f"{base_url}/?series={series}&from={from_d.isoformat()}&to={to_d.isoformat()}"

def main():
    base_url = os.environ.get("PUBLIC_BASE_URL", "https://angelhugo.github.io/sbs-hipotecas").rstrip("/")

    df = load_csv()

    fetched = fetch_latest_sbs()
    if fetched is None:
        print("No se pudo leer SBS.")
        return

    df = upsert(df, fetched["date"], fetched["rates"])

    # conservar ~400 días
    cutoff = date.today() - timedelta(days=400)
    df = df[df["date"] >= cutoff].reset_index(drop=True)
    save_csv(df)

    targets = ["promedio", "bcp", "bbva", "interbank", "scotiabank"]
    alerts = []

    for s in targets:
        sdf = df[df["series"] == s].sort_values("date")
        points = list(zip(sdf["date"].tolist(), sdf["rate"].tolist()))
        if three_day_down(points):
            alerts.append((s, points[-1][1], summarize_last_3(points)))

    if alerts:
        lines = ["📉 ALERTA SBS: 3 días seguidos a la baja"]
        for s, last_rate, summary in alerts:
            lines.append(f"- {s.upper()}: {last_rate:.2f}% | {summary}")
            lines.append(f"  Ver evolución: {build_dashboard_url(base_url, s)}")
        send_telegram("\n".join(lines))
    else:
        print("Sin alertas hoy.")

if __name__ == "__main__":
    main()
