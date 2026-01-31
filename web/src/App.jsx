import { useEffect, useMemo, useState } from "react";
import { Line } from "react-chartjs-2";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend
} from "chart.js";
import { parseCSV, ddmmyyyyToISO } from "./parseCsv";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend
);

const SERIES = ["Promedio", "Crédito", "Interbank", "BBVA", "Scotiabank"];

/**
 * Construye:
 * - data (forward filled)
 * - mask: true si el valor ORIGINAL estaba presente, false si fue rellenado
 */
function forwardFillWithMask(rawValues) {
  let last = null;
  const filled = [];
  const isOriginal = [];

  for (const v of rawValues) {
    const missing = v === null || v === "" || Number.isNaN(v);
    if (missing) {
      filled.push(last);
      isOriginal.push(false);
    } else {
      last = v;
      filled.push(v);
      isOriginal.push(true);
    }
  }
  return { filled, isOriginal };
}

export default function App() {
  const [rows, setRows] = useState([]);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [active, setActive] = useState(new Set(["Promedio"]));

  // Cargar CSV
  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}data/hipotecarios_300_habiles.csv`)
      .then(r => r.text())
      .then(text => {
        const parsed = parseCSV(text).map(r => ({
          ...r,
          fecha_iso: ddmmyyyyToISO(r.fecha_sbs)
        }));

        parsed.sort((a, b) => a.fecha_iso.localeCompare(b.fecha_iso));

        setRows(parsed);
        if (parsed.length) {
          setFrom(parsed[0].fecha_iso);
          setTo(parsed[parsed.length - 1].fecha_iso);
        }
      })
      .catch(err => {
        console.error("Error cargando CSV:", err);
      });
  }, []);

  // Filtrar por rango
  const filtered = useMemo(() => {
    if (!from || !to) return rows;
    return rows.filter(r => r.fecha_iso >= from && r.fecha_iso <= to);
  }, [rows, from, to]);

  const chartData = useMemo(() => {
    const labels = filtered.map(r => r.fecha_iso);

    const datasets = [...active].map(key => {
      // valores crudos desde CSV
      const raw = filtered.map(r => {
        const v = r[key];
        return v === "" || v === undefined ? null : Number(v);
      });

      const { filled, isOriginal } = forwardFillWithMask(raw);

      // Puntos huecos cuando el valor fue rellenado:
      // - background transparente
      // - border igual (Chart.js lo heredará por defecto)
      const pointBackgroundColor = isOriginal.map(ok =>
        ok ? undefined : "rgba(0,0,0,0)"
      );

      // Para enfatizar un poquito sin tocar colores globales:
      // puntos rellenos un poco más visibles
      const pointRadius = isOriginal.map(ok => (ok ? 2 : 3));
      const pointHoverRadius = isOriginal.map(ok => (ok ? 4 : 5));

      return {
        label: key,
        data: filled,
        tension: 0.3,
        spanGaps: true,

        // 👇 magia de puntos huecos
        pointBackgroundColor,
        pointRadius,
        pointHoverRadius
      };
    });

    return { labels, datasets };
  }, [filtered, active]);

  const options = {
    responsive: true,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: { position: "top" },
      tooltip: {
        callbacks: {
          label: ctx => {
            const v = ctx.parsed.y;
            return v == null
              ? `${ctx.dataset.label}: sin dato`
              : `${ctx.dataset.label}: ${v.toFixed(2)}%`;
          }
        }
      }
    },
    scales: {
      y: { title: { display: true, text: "Tasa (%)" } },
      x: { ticks: { maxTicksLimit: 10 } }
    }
  };

  return (
    <div
      style={{
        maxWidth: 1100,
        margin: "24px auto",
        padding: "0 16px",
        fontFamily: "system-ui, -apple-system, BlinkMacSystemFont"
      }}
    >
      <h1>SBS – Créditos Hipotecarios</h1>

      <div style={{ marginBottom: 12 }}>
        Desde{" "}
        <input type="date" value={from} onChange={e => setFrom(e.target.value)} />
        {"  "}
        Hasta{" "}
        <input type="date" value={to} onChange={e => setTo(e.target.value)} />
      </div>

      <div style={{ marginBottom: 16 }}>
        {SERIES.map(s => (
          <label key={s} style={{ marginRight: 12 }}>
            <input
              type="checkbox"
              checked={active.has(s)}
              onChange={() => {
                const next = new Set(active);
                if (next.has(s)) next.delete(s);
                else next.add(s);
                if (next.size === 0) next.add("Promedio");
                setActive(next);
              }}
            />{" "}
            {s}
          </label>
        ))}
      </div>

      <Line data={chartData} options={options} />

      <div style={{ marginTop: 12, fontSize: 12, opacity: 0.7 }}>
        Registros mostrados: {filtered.length}
      </div>
    </div>
  );
}
