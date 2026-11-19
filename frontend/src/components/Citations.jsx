const TYPE_LABEL = {
  cours: "Cours", resume: "Résumé", serie: "Série", devoir: "Devoir", revision: "Révision",
  bac_sujet: "Bac — sujet", bac_corrige: "Bac — corrigé",
};

/** Renders text where [n] markers become clickable citation chips. */
export function CitedText({ text, citations, onOpenPdf }) {
  const byN = Object.fromEntries((citations || []).map((c) => [c.n, c]));
  const parts = text.split(/(\[\d+\]|\*\*[^*]+\*\*)/g);
  return (
    <div className="cited-text">
      {parts.map((p, i) => {
        if (p.startsWith("**") && p.endsWith("**") && p.length > 4) return <strong key={i}>{p.slice(2, -2)}</strong>;
        const m = p.match(/^\[(\d+)\]$/);
        if (!m) return <span key={i}>{p}</span>;
        const c = byN[Number(m[1])];
        return c ? (
          <button key={i} className="cite" title={`${c.title}, p.${c.page}`}
                  onClick={() => onOpenPdf({ doc_id: c.doc_id, page: c.page, title: c.title })}>
            {m[1]}
          </button>
        ) : <sup key={i}>{p}</sup>;
      })}
    </div>
  );
}

export function SourceList({ citations, onOpenPdf }) {
  if (!citations?.length) return null;
  return (
    <ul className="sources">
      {citations.map((c) => (
        <li key={`${c.n}-${c.chunk_id}`}>
          <button onClick={() => onOpenPdf({ doc_id: c.doc_id, page: c.page, title: c.title })}>
            <span className="n">{c.n}</span>
            <span className="tag">{TYPE_LABEL[c.doc_type] || c.doc_type}</span>
            <strong>{c.title}</strong> — p.{c.page}
            {c.section ? <em> · {c.section}</em> : null}
          </button>
          <p>{c.snippet}…</p>
        </li>
      ))}
    </ul>
  );
}

export function Trace({ steps }) {
  if (!steps?.length) return null;
  return (
    <details className="trace">
      <summary>Étapes de l'agent ({steps.length})</summary>
      <ol>{steps.map((s, i) => <li key={i}><code>{s}</code></li>)}</ol>
    </details>
  );
}
