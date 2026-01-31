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

export default function App() {
  const [rows, setRows] = useState([]);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [active, setActive] = useState(new Set(["Promedio"]));

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}data/hipotecarios_300_habiles.csv`)
      .then(r => r.text())
      .then(t => {
        const parsed = parseCSV(t).map(r => ({
          ...r,
          fecha_iso: ddmmyyyyToISO(r.fecha_sbs)
        }));
        parsed.sort((a, b) => a.fecha_iso.localeCompare(b.fecha_iso));
        setRows(parsed);
        setFrom(parsed[0].fecha_iso);
        setTo(parsed.at(-1).fecha_iso);
      });
  }, []);

  const filtered = useMemo(
    () => rows.filter(r => r.fecha_iso >= from && r.fecha_iso <= to),
    [rows, from, to]
  );

  const data = {
    labels: filtered.map(r => r.fecha_iso),
    datasets: [...active].map(k => ({
      label: k,
      data: filtered.map(r => Number(r[k] || null)),
      tension: 0.3,
      pointRadius: 1.5
    }))
  };

  return (
    <div style={{ maxWidth: 1100, margin: "24px auto", fontFamily: "system-ui" }}>
      <h1>SBS – Créditos Hipotecarios</h1>

      <div style={{ marginBottom: 12 }}>
        Desde <input type="date" value={from} onChange={e => setFrom(e.target.value)} />
        {"  "}Hasta <input type="date" value={to} onChange={e => setTo(e.target.value)} />
      </div>

      <div style={{ marginBottom: 12 }}>
        {SERIES.map(s => (
          <label key={s} style={{ marginRight: 10 }}>
            <input
              type="checkbox"
              checked={active.has(s)}
              onChange={() => {
                const n = new Set(active);
                n.has(s) ? n.delete(s) : n.add(s);
                if (n.size === 0) n.add("Promedio");
                setActive(n);
              }}
            />
            {s}
          </label>
        ))}
      </div>

      <Line data={data} />
    </div>
  );
}
