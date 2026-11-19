"""Student model: Bayesian Knowledge Tracing (BKT) per concept + spaced repetition + prerequisite diagnosis.

BKT keeps P(known) for every (student, concept). After each graded answer:
    posterior = P(known | observation)  (Bayes rule with slip / guess)
    P(known) <- posterior + (1 - posterior) * p_learn
Answers are graded with partial credit, so the update mixes the "correct" and "wrong" posteriors
with weight = score ratio.

Spaced repetition (SM-2 style) decides *when* to review a concept; the prerequisite graph decides
*what* to review first: if a student fails a concept whose prerequisites are also weak, we
recommend the prerequisite (root cause) before the concept itself.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..concepts import CONCEPTS, prerequisites_closure


@dataclass(frozen=True)
class BKTParams:
    p_init: float = 0.25
    p_learn: float = 0.15
    p_slip: float = 0.10
    p_guess: float = 0.20


DEFAULT_PARAMS = BKTParams()
MASTERED = 0.80
WEAK = 0.55
MAX_INTERVAL_DAYS = 60.0  # the bac is at most a school year away


def bkt_update(p_know: float, score_ratio: float, params: BKTParams = DEFAULT_PARAMS) -> float:
    s, g = params.p_slip, params.p_guess
    post_correct = p_know * (1 - s) / (p_know * (1 - s) + (1 - p_know) * g)
    post_wrong = p_know * s / (p_know * s + (1 - p_know) * (1 - g))
    r = min(max(score_ratio, 0.0), 1.0)
    posterior = r * post_correct + (1 - r) * post_wrong
    return posterior + (1 - posterior) * params.p_learn


def p_correct(p_know: float, params: BKTParams = DEFAULT_PARAMS) -> float:
    """Predicted probability that the next answer is correct (used for AUC evaluation)."""
    return p_know * (1 - params.p_slip) + (1 - p_know) * params.p_guess


def sm2_next(interval_days: float, ease: float, score_ratio: float) -> tuple[float, float]:
    """SM-2 scheduling with quality q in [0, 5] derived from the score ratio."""
    q = round(score_ratio * 5)
    if q < 3:
        return 1.0, max(1.3, ease - 0.2)
    ease = max(1.3, ease + 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    interval = 1.0 if interval_days < 1 else (3.0 if interval_days < 3 else interval_days * ease)
    return min(interval, MAX_INTERVAL_DAYS), ease


SCHEMA = """
CREATE TABLE IF NOT EXISTS students (id TEXT PRIMARY KEY, name TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT, concept TEXT, question TEXT,
    score REAL, max_score REAL, ts TEXT);
CREATE TABLE IF NOT EXISTS mastery (
    student_id TEXT, concept TEXT, p_know REAL, n_attempts INTEGER, last_seen TEXT,
    next_review TEXT, interval_days REAL, ease REAL, PRIMARY KEY (student_id, concept));
"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


class StudentModel:
    def __init__(self, db_path: Path, params: BKTParams = DEFAULT_PARAMS):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.params = params

    def ensure_student(self, student_id: str, name: str | None = None) -> None:
        self.conn.execute("INSERT OR IGNORE INTO students VALUES (?, ?, ?)",
                          (student_id, name or student_id, _now().isoformat()))
        self.conn.commit()

    def _row(self, student_id: str, concept: str) -> dict:
        r = self.conn.execute("SELECT * FROM mastery WHERE student_id=? AND concept=?",
                              (student_id, concept)).fetchone()
        if r:
            return dict(r)
        return {"student_id": student_id, "concept": concept, "p_know": self.params.p_init,
                "n_attempts": 0, "last_seen": None, "next_review": None, "interval_days": 0.0, "ease": 2.5}

    def record_attempt(self, student_id: str, concept: str, score: float, max_score: float,
                       question: str = "", when: datetime | None = None) -> dict:
        if concept not in CONCEPTS:
            raise ValueError(f"unknown concept {concept}")
        self.ensure_student(student_id)
        when = when or _now()
        ratio = score / max_score if max_score else 0.0
        row = self._row(student_id, concept)
        before = row["p_know"]
        row["p_know"] = bkt_update(before, ratio, self.params)
        row["interval_days"], row["ease"] = sm2_next(row["interval_days"], row["ease"], ratio)
        row["n_attempts"] += 1
        row["last_seen"] = when.isoformat()
        row["next_review"] = (when + timedelta(days=row["interval_days"])).isoformat()
        self.conn.execute(
            "INSERT OR REPLACE INTO mastery VALUES (:student_id, :concept, :p_know, :n_attempts, "
            ":last_seen, :next_review, :interval_days, :ease)", row)
        self.conn.execute("INSERT INTO attempts (student_id, concept, question, score, max_score, ts) "
                          "VALUES (?, ?, ?, ?, ?, ?)",
                          (student_id, concept, question[:500], score, max_score, when.isoformat()))
        self.conn.commit()
        return {"concept": concept, "before": round(before, 3), "after": round(row["p_know"], 3),
                "next_review": row["next_review"]}

    def mastery(self, student_id: str) -> list[dict]:
        out = []
        for cid, c in CONCEPTS.items():
            row = self._row(student_id, cid)
            p = row["p_know"]
            status = ("non évalué" if row["n_attempts"] == 0 else
                      "maîtrisé" if p >= MASTERED else "fragile" if p >= WEAK else "à revoir")
            out.append({"concept": cid, "label": c.label, "chapter": c.chapter, "p_know": round(p, 3),
                        "n_attempts": row["n_attempts"], "status": status,
                        "next_review": row["next_review"]})
        return out

    def diagnose(self, student_id: str, concept: str) -> list[dict]:
        """Weak prerequisites of `concept` — likely root causes of an error."""
        gaps = []
        for pre in prerequisites_closure(concept):
            row = self._row(student_id, pre)
            if row["n_attempts"] == 0 or row["p_know"] < WEAK:
                gaps.append({"concept": pre, "label": CONCEPTS[pre].label, "p_know": round(row["p_know"], 3),
                             "evaluated": row["n_attempts"] > 0})
        return gaps

    def recommend(self, student_id: str, n: int = 3, chapter: str | None = None) -> list[dict]:
        """Concepts to practise next ("zone of proximal development").

        1. Frontier: concepts not yet mastered whose prerequisites are all mastered (mastery learning).
           A concept with shaky prerequisites is therefore *not* in the frontier — its prerequisites
           are, so the student goes back to the root cause.
        2. Among the frontier, finish what was started: concepts closest to mastery first, then new
           ones (ties: closest to the curriculum root).
        3. Mastered concepts whose spaced-repetition review is due come after the frontier.
        When `chapter` is given, only prerequisites inside that chapter are considered.
        """
        now = _now()
        rows = {r["concept"]: r for r in self.mastery(student_id)}

        def satisfied(pre: str) -> bool:
            return rows[pre]["n_attempts"] > 0 and rows[pre]["p_know"] >= MASTERED

        scored = []
        for cid, r in rows.items():
            c = CONCEPTS[cid]
            if chapter and c.chapter != chapter:
                continue
            prereqs = [p for p in c.prerequisites if not chapter or CONCEPTS[p].chapter == chapter]
            due = r["next_review"] is not None and datetime.fromisoformat(r["next_review"]) <= now
            depth = len(prerequisites_closure(cid))
            if r["p_know"] < MASTERED and all(satisfied(p) for p in prereqs):
                priority = 1.0 + r["p_know"] - 0.01 * depth
                reason = ("jamais évalué" if r["n_attempts"] == 0 else
                          "maîtrise faible" if r["p_know"] < WEAK else "consolidation")
            elif r["p_know"] >= MASTERED and due:
                priority, reason = 0.5 - 0.01 * depth, "révision programmée"
            elif r["p_know"] < MASTERED:
                priority, reason = 0.2 * (1 - r["p_know"]), "prérequis à consolider d'abord"
            else:
                priority, reason = 0.0, "maîtrisé"
            scored.append({**r, "priority": round(priority, 3), "reason": reason})
        return sorted(scored, key=lambda r: r["priority"], reverse=True)[:n]

    def history(self, student_id: str) -> list[dict]:
        rows = self.conn.execute("SELECT concept, score, max_score, ts FROM attempts WHERE student_id=? "
                                 "ORDER BY ts", (student_id,)).fetchall()
        return [dict(r) for r in rows]
