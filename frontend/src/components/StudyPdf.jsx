import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { QuestionCard } from "./Quiz.jsx";

// Upload a PDF -> the backend indexes it and generates flashcards + a validated quiz from it.
export default function StudyPdf({ studentId, graph, onOpenPdf }) {
  const [uploads, setUploads] = useState([]);       // [{doc_id, title, study}]
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [over, setOver] = useState(false);
  const input = useRef(null);

  const refresh = useCallback(async () => {
    const docs = (await api.documents()).filter((d) => d.doc_type === "upload");
    const withPacks = await Promise.all(docs.map(async (d) => ({
      ...d, study: await api.studyPack(d.doc_id).catch(() => null),
    })));
    withPacks.sort((a, b) => (b.uploaded_at || "").localeCompare(a.uploaded_at || ""));
    setUploads(withPacks);
    return withPacks;
  }, []);

  useEffect(() => { refresh().then((u) => u[0] && setSelected((s) => s || u[0].doc_id)).catch(() => {}); }, [refresh]);

  // poll while something is being processed
  const processing = uploads.some((u) => u.study?.status === "processing");
  useEffect(() => {
    if (!processing) return undefined;
    const t = setInterval(() => refresh().catch(() => {}), 3000);
    return () => clearInterval(t);
  }, [processing, refresh]);

  async function upload(file) {
    if (!file) return;
    if (!/\.pdf$/i.test(file.name) && file.type !== "application/pdf") {
      setError("Seuls les fichiers PDF sont acceptés."); return;
    }
    setBusy(true); setError(null);
    try {
      const doc = await api.upload(file);
      await refresh();
      setSelected(doc.doc_id);
    } catch (e) { setError(e.message); } finally { setBusy(false); if (input.current) input.current.value = ""; }
  }

  async function regenerate(docId) {
    setError(null);
    try { await api.regenerateStudyPack(docId); await refresh(); } catch (e) { setError(e.message); }
  }

  const current = uploads.find((u) => u.doc_id === selected);

  return (
    <section className="study">
      <div className="panel">
        <h2>Mes PDF</h2>
        <p className="hint">Dépose un PDF (cours, résumé, série…) : le copilote l'indexe, puis génère des fiches de révision
          et un quiz vérifié à partir de ce document uniquement. Tu peux aussi poser des questions dessus dans le chat.</p>
        <div className="upload">
          <div className={`dropzone ${over ? "over" : ""}`}
               onClick={() => input.current?.click()}
               onDragOver={(e) => { e.preventDefault(); setOver(true); }}
               onDragLeave={() => setOver(false)}
               onDrop={(e) => { e.preventDefault(); setOver(false); upload(e.dataTransfer.files[0]); }}>
            {busy ? "Envoi…" : "Clique ou glisse un fichier PDF ici"}
          </div>
          <input ref={input} type="file" accept="application/pdf,.pdf" hidden onChange={(e) => upload(e.target.files[0])} />
        </div>
        {error && <p className="error">{error}</p>}
        {uploads.length > 0 && (
          <ul className="uploads">
            {uploads.map((u) => (
              <li key={u.doc_id} className={u.doc_id === selected ? "on" : ""}>
                <button className="title" onClick={() => setSelected(u.doc_id)}>{u.title}</button>
                <StatusPill pack={u.study} />
                <button className="link" onClick={() => onOpenPdf({ doc_id: u.doc_id, page: 1, title: u.title })}>Ouvrir</button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {current && <StudyPack key={current.doc_id} doc={current} studentId={studentId} graph={graph}
                             onOpenPdf={onOpenPdf} onRegenerate={() => regenerate(current.doc_id)} />}
    </section>
  );
}

function StatusPill({ pack }) {
  if (!pack) return <span className="pill">—</span>;
  if (pack.status === "ready") return <span className="pill ready">{pack.flashcards.length} fiches · {pack.questions.length} questions</span>;
  if (pack.status === "error") return <span className="pill error">erreur</span>;
  return <span className="pill">{pack.stage || "en cours"}…</span>;
}

function StudyPack({ doc, studentId, graph, onOpenPdf, onRegenerate }) {
  const [view, setView] = useState("cards");
  const pack = doc.study;
  if (!pack || pack.status === "processing") {
    return <div className="panel"><p className="hint">Préparation de « {doc.title} » : {pack?.stage || "en cours"}… (OCR et génération peuvent prendre une minute)</p></div>;
  }
  if (pack.status === "error") {
    return (
      <div className="panel">
        <p className="error">La génération a échoué : {pack.error}</p>
        <button className="primary" onClick={onRegenerate}>Réessayer</button>
      </div>
    );
  }
  return (
    <div className="panel">
      <div className="row" style={{ marginTop: 0 }}>
        <h3 style={{ margin: 0 }}>{doc.title}</h3>
        {pack.concepts?.length > 0 && <span className="hint">Notions : {pack.concepts.map((c) => label(graph, c)).join(", ")}</span>}
        <button className="link" style={{ marginLeft: "auto" }} onClick={onRegenerate}>Régénérer</button>
      </div>
      <div className="subtabs">
        <button className={view === "cards" ? "chip on" : "chip"} onClick={() => setView("cards")}>Fiches ({pack.flashcards.length})</button>
        <button className={view === "quiz" ? "chip on" : "chip"} onClick={() => setView("quiz")}>Quiz ({pack.questions.length})</button>
      </div>
      {view === "cards"
        ? <Deck cards={pack.flashcards} graph={graph} onOpenPdf={onOpenPdf} />
        : (
          <>
            {pack.rejected?.length > 0 && <p className="hint">{pack.rejected.length} question(s) rejetée(s) par le contrôle qualité.</p>}
            {pack.questions.map((q, i) => (
              <QuestionCard key={q.id} index={i} q={q} studentId={studentId} graph={graph} onOpenPdf={onOpenPdf} />
            ))}
          </>
        )}
    </div>
  );
}

// Leitner-style session: "À revoir" puts the card back at the end of the queue, "Je savais" removes it.
function Deck({ cards, graph, onOpenPdf }) {
  const [queue, setQueue] = useState(() => cards.map((_, i) => i));
  const [flipped, setFlipped] = useState(false);
  const [known, setKnown] = useState(0);
  const [again, setAgain] = useState(0);

  const restart = () => { setQueue(cards.map((_, i) => i)); setKnown(0); setAgain(0); setFlipped(false); };
  const next = (knewIt) => {
    const [head, ...rest] = queue;
    setQueue(knewIt ? rest : [...rest, head]);
    knewIt ? setKnown(known + 1) : setAgain(again + 1);
    setFlipped(false);
  };

  useEffect(() => {
    const onKey = (e) => {
      if (e.target.tagName === "TEXTAREA" || e.target.tagName === "INPUT" || !queue.length) return;
      if (e.key === " ") { e.preventDefault(); setFlipped((f) => !f); }
      if (flipped && e.key === "ArrowRight") next(true);
      if (flipped && e.key === "ArrowLeft") next(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (!cards.length) return <p className="hint">Aucune fiche n'a pu être générée à partir de ce document.</p>;
  if (!queue.length) {
    return (
      <div className="card-actions" style={{ flexDirection: "column", alignItems: "center" }}>
        <p><strong>Session terminée</strong> — {cards.length} fiches, {again} répétition(s).</p>
        <button className="primary" onClick={restart}>Recommencer</button>
      </div>
    );
  }
  const card = cards[queue[0]];
  const src = card.sources?.[0];
  return (
    <>
      <div className="progressbar"><div style={{ width: `${(known / cards.length) * 100}%` }} /></div>
      <p className="hint">{known} / {cards.length} acquises · {queue.length} restante(s) — espace pour retourner, ← / → pour répondre</p>
      <div className={`flashcard ${flipped ? "flipped" : ""}`} onClick={() => setFlipped(!flipped)}>
        <div className="inner">
          <div className="face front">{card.front}<small>{label(graph, card.concept) || "Clique pour voir la réponse"}</small></div>
          <div className="face back">{card.back}
            {src && <small>Source : p. {src.page}{src.section ? ` — ${src.section}` : ""}</small>}
          </div>
        </div>
      </div>
      <div className="card-actions">
        {flipped ? (
          <>
            <button className="btn-bad" onClick={() => next(false)}>À revoir</button>
            <button className="btn-good" onClick={() => next(true)}>Je savais</button>
            {src && <button className="link" onClick={() => onOpenPdf({ doc_id: src.doc_id, page: src.page, title: src.title })}>Voir dans le PDF</button>}
          </>
        ) : <button className="primary" onClick={() => setFlipped(true)}>Voir la réponse</button>}
      </div>
    </>
  );
}

const label = (graph, id) => (id ? graph?.nodes.find((n) => n.id === id)?.label || id : "");
