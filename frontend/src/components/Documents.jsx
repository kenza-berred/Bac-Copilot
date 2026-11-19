import { useEffect, useMemo, useState } from "react";
import { api } from "../api.js";

const TYPES = { cours: "Cours", resume: "Résumé", serie: "Série", devoir: "Devoir", revision: "Révision",
                bac_sujet: "Bac sujet", bac_corrige: "Bac corrigé" };

export default function Documents({ onOpenPdf }) {
  const [docs, setDocs] = useState([]);
  const [filter, setFilter] = useState("");
  const [busy, setBusy] = useState(false);
  const [stats, setStats] = useState(null);

  const load = () => api.documents().then(setDocs);
  useEffect(() => { load(); }, []);

  async function ingest() {
    setBusy(true);
    try { setStats(await api.ingest()); await load(); } finally { setBusy(false); }
  }

  const shown = useMemo(() => docs.filter((d) => !filter || d.doc_type === filter), [docs, filter]);
  const indexed = docs.filter((d) => d.indexed).length;

  return (
    <section className="documents panel">
      <div className="row">
        <h2>Base documentaire</h2>
        <span className="hint">{indexed} / {docs.length} documents indexés</span>
        <select value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="">Tous les types</option>
          {Object.entries(TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <button className="primary" onClick={ingest} disabled={busy}>{busy ? "Indexation…" : "Mettre à jour l'index"}</button>
      </div>
      {stats && <p className="hint">Nouveaux : {stats.new} · mis à jour : {stats.updated} · inchangés : {stats.unchanged} · supprimés : {stats.removed} · total passages : {stats.total_chunks}</p>}
      <table className="doc-table">
        <thead><tr><th>Titre</th><th>Type</th><th>Année</th><th>Version</th><th>Passages</th><th /></tr></thead>
        <tbody>
          {shown.map((d) => (
            <tr key={d.doc_id} className={d.indexed ? "" : "dim"}>
              <td>{d.title}</td>
              <td><span className="tag">{TYPES[d.doc_type] || d.doc_type}</span></td>
              <td>{d.year || ""}</td>
              <td>{d.version ? `v${d.version}` : "—"}</td>
              <td>{d.chunks ?? "—"}</td>
              <td>{d.indexed && <button className="link" onClick={() => onOpenPdf({ doc_id: d.doc_id, page: 1, title: d.title })}>Ouvrir</button>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
