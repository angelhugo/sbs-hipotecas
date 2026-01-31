# SBS Hipotecas 📈

Visualización y análisis histórico de las tasas de interés de créditos hipotecarios en moneda nacional publicadas por la Superintendencia de Banca, Seguros y AFP (SBS) del Perú.

El proyecto:
- extrae y consolida datos históricos diarios,
- permite explorarlos visualmente en una web estática,
- y sienta la base para alertas automáticas y análisis de tendencia.

---

## 🌐 Demo

La web está disponible en:

https://angelhugo.github.io/sbs-hipotecas/

(usa el selector de fechas y activa/desactiva series para explorar la evolución de tasas).

---

## 📊 Datos

- Fuente: SBS – Tasas Activas Anuales  
- Producto: Préstamos hipotecarios para vivienda  
- Moneda: Moneda nacional  
- Frecuencia: diaria (días hábiles)  
- Horizonte actual: ~300 días hábiles  

Archivo principal:

data/hipotecarios_300_habiles.csv

Columnas:
- fecha_consultada: fecha solicitada en la web SBS  
- fecha_sbs: fecha efectiva reportada por la SBS  
- Promedio  
- Crédito (BCP)  
- Interbank  
- BBVA  
- Scotiabank  

Nota: en días sin nueva data, la SBS puede devolver la última fecha disponible.

---

## 🖥️ Web (GitHub Pages)

La visualización está construida con:
- Vite + React
- Chart.js

Funcionalidades actuales:
- gráfico de líneas (“fever chart”) de tasas hipotecarias
- selector de rango de fechas
- activación/desactivación de series (promedio y bancos)

El CSV maestro se copia automáticamente a la web durante el proceso de build.

---

## 🗂️ Estructura del proyecto

sbs-hipotecas/
├─ data/                     # datos históricos (CSV maestro)
├─ web/                      # frontend (Vite + React)
│  ├─ index.html
│  ├─ src/
│  ├─ public/data/           # CSV servido a la web
│  └─ scripts/               # utilidades de build
└─ .github/workflows/        # deploy automático a GitHub Pages

---

## 🚀 Desarrollo local

Requisitos:
- Node.js 18 o superior

Pasos:

cd web  
npm install  
npm run dev  

La app estará disponible en:

http://localhost:5173/sbs-hipotecas/

---

## 🔄 Deploy

El deploy es automático vía GitHub Actions al hacer push a la rama main.

La web se publica usando GitHub Pages.

---

## 🧭 Roadmap

Próximos pasos planificados:
- rangos rápidos (1M / 3M / 6M / 1Y)
- detección visual de tendencias (ej. 3 días a la baja)
- alertas automáticas vía Telegram
- agente diario en Raspberry Pi
- migración del histórico a SQLite

---

## ⚠️ Disclaimer

Este proyecto es informativo y experimental.  
Las tasas mostradas son referenciales y no constituyen asesoría financiera.

---

## 📄 Licencia

MIT
