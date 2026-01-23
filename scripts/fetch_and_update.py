import os
import requests
from datetime import date

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

def main():
    send_telegram(f"✅ TEST OK: workflow corrió hoy {date.today().isoformat()} (hora Perú)")

if __name__ == "__main__":
    main()
