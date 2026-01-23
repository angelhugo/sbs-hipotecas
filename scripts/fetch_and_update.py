from datetime import date
import os

CSV_PATH = "data/rates.csv"

def main():
    today = date.today().isoformat()

    # crear archivo si no existe
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(CSV_PATH):
        with open(CSV_PATH, "w", encoding="utf-8") as f:
            f.write("date,series,rate\n")

    # escribir una fila de prueba
    with open(CSV_PATH, "a", encoding="utf-8") as f:
        f.write(f"{today},test,0.00\n")

    print("Script ejecutado correctamente")

if __name__ == "__main__":
    main()
