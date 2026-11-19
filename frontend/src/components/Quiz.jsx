import { useState } from "react";
import { api } from "../api.js";
import { CitedText, SourceList, Trace } from "./Citations.jsx";

const KINDS = [["qcm", "QCM"], ["short", "Restitution"], ["analysis", "Analyse de document"]];

export default function Quiz({ studentId, graph, onOpenPdf }) {
  const [selected, setSelected] = useState([]);
  const [kinds, setKinds] = useState(["qcm", "short", "analysis"]);
  const [n, setN] = useState(3);
  const [quiz, setQuiz] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const toggle = (list, setList, v) => setList(list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

  async function generate() {
    setBusy(true); setError(null); setQuiz(null);
    try {
      setQuiz(await api.quiz(studentId, n, selected, kinds));
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  const byChapter = {};
  graph?.nodes.forEach((c) => (byChapter[c.chapter] ||= []).push(c));

  return (
    <section className="quiz">
      <div className="panel setup">
        <h2>Examen blanc</h2>
        <p className="hint">Laisse les concepts vides : le copilote choisit ce que tu dois travailler en priorité (prérequis d'abord).</p>
        {graph && Object.entries(byChapter).map(([ch, concepts]) => (
          <div key={ch} className="chapter">
            <h4>{graph.chapters[ch]}</h4>
            <div className="chips">
              {concepts.map((c) => (
                <button key={c.id} className={selected.includes(c.id) ? "chip on" : "chip"}
                        onClick={() => toggle(selected, setSelected, c.id)}>{c.label}</button>
              ))}
            </div>
          </div>
        ))}
        <div className="row">
          <div className="chips">
            {KINDS.map(([k, label]) => (
              <button key={k} className={kinds.includes(k) ? "chip on" : "chip"}
                      onClick={() => toggle(kinds, setKinds, k)}>{label}</button>
            ))}
          </div>
          <label>Questions <input type="number" min={1} max={8} value={n} onChange={(e) => setN(+e.target.value)} /></label>
          <button className="primary" onClick={generate} disabled={busy || !kinds.length}>
            {busy ? "Génération et vérification…" : selected.length ? "Générer" : "Générer (adaptatif)"}
          </button>
        </div>
        {error && <p className="error">{error}</p>}
      </div>

      {quiz && (
        <>
          <p className="hint">
            Concepts : <strong>{quiz.concepts.map((c) => label(graph, c)).join(", ")}</strong>
            {quiz.rejected?.length > 0 && <> · {quiz.rejected.length} question(s) rejetée(s) par le contrôle qualité</>}
          </p>
          <Trace steps={quiz.trace} />
          {quiz.questions.map((q, i) => (
            <QuestionCard key={q.id} index={i} q={q} studentId={studentId} graph={graph} onOpenPdf={onOpenPdf} />
          ))}
        </>
      )}
    </section>
  );
}

export function QuestionCard({ q, index, studentId, graph, onOpenPdf }) {
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [showModel, setShowModel] = useState(false);

  async function grade() {
    setBusy(true);
    try {
      setResult(await api.grade({
        student_id: studentId, question: q.question + (q.options?.length ? "\n" + q.options.join("\n") : ""),
        student_answer: answer, rubric: q.rubric, reference: q.answer, concept: q.concept, max_points: q.max_points,
      }));
    } catch (e) { setResult({ error: e.message }); } finally { setBusy(false); }
  }

  const g = result?.grade;
  return (
    <article className="panel question">
      <header>
        <span className="qn">Q{index + 1}</span>
        <span className="tag">{q.type}</span>
        <span className="tag">{q.difficulty}</span>
        <span className="pts">{q.max_points} pt{q.max_points > 1 ? "s" : ""}</span>
      </header>
      <p className="qtext">{q.question}</p>
      {q.options?.length > 0 && <ul className="options">{q.options.map((o) => <li key={o}>{o}</li>)}</ul>}
      <textarea rows={4} value={answer} onChange={(e) => setAnswer(e.target.value)}
                placeholder={q.type === "qcm" ? "Ex : b et d — justifie si tu veux" : "Rédige ta réponse comme au bac…"} />
      <div className="row">
        <button className="primary" onClick={grade} disabled={busy || !answer.trim()}>{busy ? "Correction…" : "Corriger"}</button>
        <button className="link" onClick={() => setShowModel(!showModel)}>{showModel ? "Masquer" : "Voir"} la réponse modèle</button>
      </div>
      {showModel && (
        <div className="model">
          <p>{q.answer}</p>
          <ul>{q.rubric.map((r) => <li key={r.criterion}>{r.criterion} — {r.points} pt</li>)}</ul>
          <SourceList citations={q.sources} onOpenPdf={onOpenPdf} />
        </div>
      )}
      {result?.error && <p className="error">{result.error}</p>}
      {g && (
        <div className="grade">
          <div className="score">{g.score} / {g.max_score}</div>
          <table>
            <tbody>
              {g.criteria.map((c) => (
                <tr key={c.criterion}>
                  <td>{c.criterion}</td><td className="num">{c.awarded}/{c.max_points}</td><td className="comment">{c.comment}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <CitedText text={g.feedback} citations={g.citations} onOpenPdf={onOpenPdf} />
          {g.misconceptions?.length > 0 && <p className="warn-text">Erreur conceptuelle : {g.misconceptions.join(" ; ")}</p>}
          {result.mastery_update && (
            <p className="mastery-change">
              Maîtrise « {label(graph, result.mastery_update.concept)} » : {pct(result.mastery_update.before)} → <strong>{pct(result.mastery_update.after)}</strong>
            </p>
          )}
          {result.diagnosis?.length > 0 && (
            <div className="diagnosis">
              <strong>Cause possible :</strong> ces prérequis sont fragiles ou pas encore évalués —
              {" "}{result.diagnosis.map((d) => d.label).join(", ")}.
            </div>
          )}
          <Trace steps={result.trace} />
        </div>
      )}
    </article>
  );
}

const label = (graph, id) => graph?.nodes.find((n) => n.id === id)?.label || id;
const pct = (x) => `${Math.round(x * 100)} %`;
