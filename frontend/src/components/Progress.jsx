import { useEffect, useState } from "react";
import { api } from "../api.js";
import ConceptGraph from "./ConceptGraph.jsx";

export default function Progress({ studentId, graph, onPractice }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setData(null);
    api.student(studentId).then(setData).catch((e) => setError(e.message));
  }, [studentId]);

  if (error) return <p className="error">{error}</p>;
  if (!data || !graph) return <p className="hint">Chargement…</p>;

  const mastery = Object.fromEntries(data.mastery.map((m) => [m.concept, m]));
  const evaluated = data.mastery.filter((m) => m.n_attempts > 0);
  const avg = evaluated.length ? evaluated.reduce((s, m) => s + m.p_know, 0) / evaluated.length : 0;

  return (
    <section className="progress">
      <div className="kpis">
        <Kpi label="Concepts évalués" value={`${evaluated.length} / ${data.mastery.length}`} />
        <Kpi label="Maîtrise moyenne" value={evaluated.length ? `${Math.round(avg * 100)} %` : "—"} />
        <Kpi label="Concepts maîtrisés" value={data.mastery.filter((m) => m.status === "maîtrisé").length} />
        <Kpi label="Réponses corrigées" value={data.history.length} />
      </div>

      <div className="grid2">
        <div className="panel">
          <h3>Carte de maîtrise</h3>
          {Object.entries(graph.chapters).map(([ch, label]) => (
            <div key={ch} className="heat-row">
              <h4>{label}</h4>
              <div className="heat">
                {graph.nodes.filter((c) => c.chapter === ch).map((c) => {
                  const m = mastery[c.id];
                  return (
                    <div key={c.id} className={`cell ${m.n_attempts ? "" : "unseen"}`}
                         style={{ background: m.n_attempts ? heat(m.p_know) : undefined }} title={`${c.label} — ${m.status}`}>
                      <span>{c.label}</span>
                      <b>{m.n_attempts ? `${Math.round(m.p_know * 100)} %` : "—"}</b>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
          <p className="legend"><i className="lo" /> à revoir <i className="mid" /> fragile <i className="hi" /> maîtrisé <i className="none" /> non évalué</p>
        </div>

        <div className="panel">
          <h3>À travailler maintenant</h3>
          <ol className="recs">
            {data.recommendations.map((r) => (
              <li key={r.concept}><strong>{r.label}</strong><span>{r.reason} · {Math.round(r.p_know * 100)} %</span></li>
            ))}
          </ol>
          <button className="primary" onClick={onPractice}>Lancer un examen blanc adaptatif</button>
          <h3 style={{ marginTop: 24 }}>Graphe des prérequis</h3>
          <ConceptGraph graph={graph} mastery={mastery} />
        </div>
      </div>
    </section>
  );
}

const heat = (p) => (p >= 0.8 ? "var(--good)" : p >= 0.55 ? "var(--mid)" : "var(--bad)");

function Kpi({ label, value }) {
  return <div className="kpi"><span>{label}</span><strong>{value}</strong></div>;
}
