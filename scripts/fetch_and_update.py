import os
import re
import requests
import pandas as pd
from datetime import date, timedelta
from io import StringIO


# Endpoint SBS (NO el portal protegido por Incapsula)
SBS_DAILY_URL = "https://www.sbs.gob.pe/app/stats/TasaDiaria_7B.asp?FECHA_CONSULTA={}"

CSV_PATH = "data/rates.csv"
WATCH = ["promedio", "bcp", "bbva", "interbank", "scotiabank"]


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
        timeout=30,
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


def _fmt_date_for_sbs(d: date) -> str:
    # DD/MM/YYYY con "/" escapado como %2F
    return d.strftime("%d/%m/%Y").replace("/", "%2F")


def _norm_bank_name(name: str) -> str:
    """
    Convierte el texto del banco (tal como aparece en la tabla SBS)
    al nombre interno de serie: promedio/bcp/bbva/interbank/scotiabank
    """
    n = (name or "").strip().upper()

    if not n or n == "NAN":
        return ""

    # Promedio
    if "PROMEDIO" in n:
        return "promedio"

    # BCP (a veces: BANCOM, CRÉDITO, BANCO DE CREDITO, etc.)
    if "BANCOM" in n or "CREDITO" in n or "CRÉDITO" in n or "BCP" in n:
        return "bcp"

    # BBVA
    if "BBVA" in n:
        return "bbva"

    # Interbank (a veces: BANCO INTERNACIONAL DEL PERU)
    if "INTERBANK" in n or "BANCO INTERNACIONAL" in n:
        return "interbank"

    # Scotiabank
    if "SCOTIABANK" in n:
        return "scotiabank"

    return ""


def fetch_latest_sbs(max_lookback_days: int = 30):
    """
    Lee la SBS diaria por fecha (endpoint app/stats) usando requests con User-Agent,
    y parsea las tablas desde el HTML (StringIO). Si hoy no tiene data, retrocede.
    Devuelve: {"date": <date>, "rates": {...}, "source_url": <url>}
    """
    last_err = None

    session = requests.Session()
    headers = {
        # “Como navegador” para evitar respuestas raras
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
    }

    for back in range(max_lookback_days):
        d = date.today() - timedelta(days=back)
        ds = _fmt_date_for_sbs(d)

        # Probamos dos variantes de query (la SBS a veces usa FEC)
        candidate_urls = [
            SBS_DAILY_URL.format(ds),  # ...?FECHA_CONSULTA=DD%2FMM%2FYYYY
            f"https://www.sbs.gob.pe/app/stats/TasaDiaria_7B.asp?FEC={ds}",
        ]

        for url in candidate_urls:
            try:
                resp = session.get(url, headers=headers, timeout=60)
                resp.raise_for_status()
                html = resp.text

                # Si no hay tablas, no hay nada que leer
                if "<table" not in html.lower():
                    last_err = ValueError("No tables found (no <table> in HTML)")
                    continue

                tables = pd.read_html(StringIO(html))  # clave: parsear HTML como contenido
                if not tables:
                    last_err = ValueError("No tables found (pandas read_html empty)")
                    continue

                df = tables[0].copy()
                df.columns = [str(c).strip() for c in df.columns]

                bank_col = df.columns[0]

                hip_col = None
                for c in df.columns:
                    if re.search(r"hipotec", c, re.IGNORECASE):
                        hip_col = c
                        break
                if hip_col is None:
                    last_err = ValueError(f"No encontré columna hipotecaria. Columnas: {df.columns.tolist()}")
                    continue

                rates = {}
                for _, row in df.iterrows():
                    bank_raw = str(row.get(bank_col, "")).strip()
                    series = _norm_bank_name(bank_raw)
                    if not series:
                        continue

                    val = row.get(hip_col, "")
                    sval = str(val).strip()
                    if sval in ("-", "nan", "NaN", ""):
                        continue

                    try:
                        rates[series] = parse_rate(val)
                    except:
                        continue

                if "promedio" not in rates:
                    last_err = ValueError(f"No vino 'promedio'. rates={rates}")
                    continue

                return {"date": d, "rates": rates, "source_url": url}

            except Exception as e:
                last_err = e
                continue

    raise RuntimeError(
        f"No pude obtener data SBS en {max_lookback_days} días. Último error: {last_err}"
    )



def upsert(df, d, rates: dict):
    new = pd.DataFrame(
        [{"date": d, "series": s, "rate": float(r)} for s, r in rates.items()]
    )
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
    return (
        f"Últimos 3 datos: {a[0]} {a[1]:.2f}% → {b[0]} {b[1]:.2f}% "
        f"({arrow} {delta:+.2f} pp)"
    )


def build_dashboard_url(base_url: str, series: str, days: int = 90):
    to_d = date.today()
    from_d = to_d - timedelta(days=days)
    return f"{base_url}/?series={series}&from={from_d.isoformat()}&to={to_d.isoformat()}"


def main():
    base_url = os.environ.get("PUBLIC_BASE_URL", "https://angelhugo.github.io/sbs-hipotecas").rstrip("/")

    df = load_csv()

    fetched = fetch_latest_sbs()
    d = fetched["date"]
    rates = fetched["rates"]
    source_url = fetched["source_url"]

    df = upsert(df, d, rates)

    # conservar ~400 días (último año + colchón)
    cutoff = date.today() - timedelta(days=400)
    df = df[df["date"] >= cutoff].reset_index(drop=True)
    save_csv(df)

    alerts = []
    for s in WATCH:
        sdf = df[df["series"] == s].sort_values("date")
        points = list(zip(sdf["date"].tolist(), sdf["rate"].tolist()))
        if three_day_down(points):
            alerts.append((s, points[-1][1], summarize_last_3(points)))

    if alerts:
        lines = ["📉 ALERTA SBS: 3 días seguidos a la baja", f"Fecha dato: {d}"]
        # Añadimos valores del día si están
        def safe_rate(key):
            return rates.get(key, None)

        daily_parts = []
        for key, label in [("promedio", "PROMEDIO"), ("bcp", "BCP"), ("bbva", "BBVA"), ("interbank", "INTERBANK"), ("scotiabank", "SCOTIABANK")]:
            v = safe_rate(key)
            if v is not None:
                daily_parts.append(f"{label}: {v:.2f}%")
        if daily_parts:
            lines.append(" | ".join(daily_parts))

        lines.append("")  # línea en blanco

        for s, last_rate, summary in alerts:
            lines.append(f"- {s.upper()}: {last_rate:.2f}% | {summary}")
            lines.append(f"  Ver evolución: {build_dashboard_url(base_url, s)}")

        lines.append(f"Fuente SBS (día): {source_url}")

        send_telegram("\n".join(lines))
    else:
        print("Sin alertas hoy.")
        print(f"Fuente SBS: {source_url}")


if __name__ == "__main__":
    main()
