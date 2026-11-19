import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { CitedText, SourceList, Trace } from "./Citations.jsx";

const EXAMPLES = [
  "Quel est le rôle des LT4 dans la réponse immunitaire ?",
  "Explique le brassage intrachromosomique",
  "kifech na3ref les gènes liés fil test-cross ?",
  "Quels sont mes points faibles ?",
];

export default function Chat({ studentId, onOpenPdf }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, busy]);

  async function send(text) {
    const message = (text ?? input).trim();
    if (!message || busy) return;
    setInput("");
    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    setMessages((ms) => [...ms, { role: "user", content: message }]);
    setBusy(true);
    try {
      const r = await api.chat(studentId, message, history);
      if (r.intent === "quiz") {
        const content = r.questions.map((q, i) => `${i + 1}. ${q.question}`).join("\n");
        setMessages((ms) => [...ms, { role: "assistant", content: `Voici un exercice :\n${content}\n\n→ Utilise l'onglet « Examen blanc » pour répondre et être corrigé.`, trace: r.trace }]);
      } else {
        setMessages((ms) => [...ms, { role: "assistant", content: r.answer, citations: r.citations,
                                      verified: r.verified, trace: r.trace }]);
      }
    } catch (e) {
      setMessages((ms) => [...ms, { role: "assistant", content: `Erreur : ${e.message}`, error: true }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="chat">
      <div className="messages">
        {messages.length === 0 && (
          <div className="empty">
            <h2>Pose ta question de SVT</h2>
            <p>En français, en arabe ou en derja. Chaque réponse cite le cours ou le corrigé de bac utilisé — clique sur un numéro pour ouvrir la page.</p>
            <div className="examples">
              {EXAMPLES.map((e) => <button key={e} onClick={() => send(e)}>{e}</button>)}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role} ${m.error ? "error" : ""}`}>
            {m.role === "assistant" && m.citations
              ? <CitedText text={m.content} citations={m.citations} onOpenPdf={onOpenPdf} />
              : <div className="plain">{m.content}</div>}
            {m.role === "assistant" && m.verified === false && <span className="badge warn">À vérifier</span>}
            {m.role === "assistant" && m.verified === true && m.citations?.length > 0 && <span className="badge ok">Vérifié dans le cours</span>}
            <SourceList citations={m.citations} onOpenPdf={onOpenPdf} />
            <Trace steps={m.trace} />
          </div>
        ))}
        {busy && <div className="msg assistant thinking">Recherche dans le cours…</div>}
        <div ref={end} />
      </div>
      <form className="composer" onSubmit={(e) => { e.preventDefault(); send(); }}>
        <textarea value={input} placeholder="Ex : Pourquoi la réponse secondaire est-elle plus rapide ?" rows={2}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
        <button disabled={busy || !input.trim()}>Envoyer</button>
      </form>
    </section>
  );
}
