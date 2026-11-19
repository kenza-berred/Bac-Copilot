import { useEffect, useState } from "react";
import { api } from "./api.js";
import Hero from "./components/Hero.jsx";
import Chat from "./components/Chat.jsx";
import Quiz from "./components/Quiz.jsx";
import Progress from "./components/Progress.jsx";
import Documents from "./components/Documents.jsx";
import StudyPdf from "./components/StudyPdf.jsx";
import PdfPanel from "./components/PdfPanel.jsx";

const TABS = [
  ["home", "Accueil"],
  ["chat", "Questions"],
  ["quiz", "Examen blanc"],
  ["study", "Mes PDF"],
  ["progress", "Progression"],
  ["docs", "Documents"],
];

export default function App() {
  const [tab, setTab] = useState("home");
  const [studentId, setStudentId] = useState(() => storageGet("studentId") || "eleve-demo");
  const [graph, setGraph] = useState(null);
  const [pdf, setPdf] = useState(null); // {doc_id, page, title}
  const [status, setStatus] = useState(null);

  useEffect(() => {
    api.concepts().then(setGraph).catch(() => {});
    api.health().then(setStatus).catch(() => setStatus({ status: "offline" }));
  }, []);
  useEffect(() => { storageSet("studentId", studentId); }, [studentId]);

  const online = status?.status === "ok";

  return (
    <div className={`shell ${tab === "home" ? "is-home" : ""} ${pdf ? "with-pdf" : ""}`}>
      <div className="backdrop" aria-hidden="true"><i /><i /><i /></div>

      <header className="topbar">
        <button className="wordmark" onClick={() => setTab("home")} aria-label="Accueil">
          <svg viewBox="0 0 32 32" aria-hidden="true">
            <circle cx="16" cy="16" r="13" className="wm-ring" />
            <circle cx="16" cy="16" r="5.5" className="wm-core" />
          </svg>
          Bac Copilot
        </button>
        <nav className="tabs">
          {TABS.map(([id, label]) => (
            <button key={id} className={tab === id ? "on" : ""} aria-current={tab === id ? "page" : undefined}
                    onClick={() => setTab(id)}>{label}</button>
          ))}
        </nav>
        <div className="who">
          <span className={`dot ${online ? "ok" : "off"}`}
                title={online ? `${status.chunks} passages indexés` : "API hors ligne"} />
          <label>
            <span className="sr">Identifiant élève</span>
            <input value={studentId} onChange={(e) => setStudentId(e.target.value.trim() || "eleve-demo")} />
          </label>
        </div>
      </header>

      {tab === "home" ? (
        <main className="stage-wrap">
          <Hero graph={graph} onStart={() => setTab("chat")} onPractice={() => setTab("quiz")} />
        </main>
      ) : (
        <main className="page">
          {tab === "chat" && <Chat studentId={studentId} onOpenPdf={setPdf} />}
          {tab === "quiz" && <Quiz studentId={studentId} graph={graph} onOpenPdf={setPdf} />}
          {tab === "study" && <StudyPdf studentId={studentId} graph={graph} onOpenPdf={setPdf} />}
          {tab === "progress" && <Progress studentId={studentId} graph={graph} onPractice={() => setTab("quiz")} />}
          {tab === "docs" && <Documents onOpenPdf={setPdf} />}
        </main>
      )}

      {pdf && <PdfPanel pdf={pdf} onClose={() => setPdf(null)} />}
    </div>
  );
}

function storageGet(k) {
  try { return window.localStorage.getItem(k); } catch { return null; }
}
function storageSet(k, v) {
  try { window.localStorage.setItem(k, v); } catch { /* storage unavailable */ }
}
