import { useState } from "react";
import GlassCells from "./GlassCells.jsx";

const FALLBACK = {
  reproduction: "Reproduction humaine et santé",
  genetique: "Génétique et évolution",
  neurophysiologie: "Neurophysiologie",
  immunite: "Immunité",
};

export default function Hero({ graph, onStart, onPractice }) {
  const chapters = Object.entries(graph?.chapters || FALLBACK);
  const [active, setActive] = useState(0);
  const [chId, chLabel] = chapters[active] || chapters[0];
  const notions = graph?.nodes.filter((n) => n.chapter === chId) || [];

  return (
    <section className="hero">
      <GlassCells focus={active} />

      <nav className="chapters" aria-label="Chapitres du programme">
        {chapters.map(([id, label], i) => (
          <button key={id} className={i === active ? "on" : ""} aria-pressed={i === active}
                  title={label} onClick={() => setActive(i)}>
            <span className="sr">{label}</span>
          </button>
        ))}
      </nav>

      <div className="hero-copy">
        <p className="kicker">Pour le bac Sciences expérimentales</p>
        <h1>La SVT du bac,<br />vue de près.</h1>
        <p className="lede">
          Pose tes questions en français, en arabe ou en derja. Entraîne-toi sur de vrais sujets
          de bac, et le copilote repère le prérequis qui te bloque.
        </p>
      </div>

      <div className="hero-foot">
        <div className="chapter-index">
          <span className="num">{active + 1}</span>
          <span className="of">/ {chapters.length}</span>
          <p>
            <strong>{chLabel}</strong>
            {notions.length > 0 && <span>{notions.length} notions au programme</span>}
          </p>
        </div>
        <div className="hero-actions">
          <button className="cta" onClick={onStart}>Commencer à réviser</button>
          <button className="ghost" onClick={onPractice}>Faire un examen blanc</button>
        </div>
        <p className="statement">
          <strong>Chaque réponse</strong> cite la page du cours ou du corrigé de bac
          d'où elle vient. Un clic, et la page s'ouvre.
        </p>
      </div>
    </section>
  );
}
