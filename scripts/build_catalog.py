"""Build data/catalog.json: metadata for every SVT document we ingest.

Sources (bac-done.com, section Sciences expérimentales, subject id 26):
  - course documents: https://bac-done.com/sections/science-de-la-vie-et-de-la-terre/documents/26
  - official bac exams: https://bac-done.com/bacs/science-de-la-vie-et-de-la-terre/sujets/26

The catalog only stores metadata (title, type, chapter, year, URL). The PDFs themselves are
downloaded locally by scripts/download_bac_done.py and are NOT committed (copyright).

Usage:  python scripts/build_catalog.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.concepts import normalize  # noqa: E402

SITE = "https://bac-done.com"
SUBJECT_ID = 26

# (doc_id, slug, title) — copied from the SVT documents page
COURSE_DOCS = [
    (145, "cours-reproduction-chez-lhomme-et-la-femme", "Cours Reproduction chez l'homme et la femme"),
    (415, "cours-2-reproduction-chez-lhomme", "Cours 2 Reproduction chez l'homme"),
    (416, "cours-2-reproduction-chez-la-femme", "Cours 2 Reproduction chez la femme"),
    (417, "cours-2-procreation", "Cours 2 Procréation"),
    (418, "cours-brassages", "Cours brassages"),
    (419, "cours-monohybridisme", "Cours monohybridisme"),
    (420, "cours-2-genetique-humaine", "Cours 2 Génétique humaine"),
    (421, "cours-tissu-nerveux", "Cours Tissu nerveux"),
    (422, "cours-reflexe-myotatique", "Cours réflexe myotatique"),
    (423, "cours-immunite", "Cours immunité"),
    (1340, "cours-procreation-complet", "Cours Procréation complet"),
    (1614, "regulation-nerveuse-de-la-pression-arterielle", "Cours Régulation nerveuse de la pression artérielle"),
    (1660, "cours-deroulement-de-la-reponse-immunitaire-specifique", "Cours Déroulement de la réponse immunitaire spécifique"),
    (1707, "reproduction-chez-la-femme-bac-2027", "Cours Reproduction chez la femme (Bac 2027)"),
    (241, "la-fonction-reproductrice-feminine", "Résumé La fonction reproductrice féminine"),
    (242, "le-cycle-sexuel-de-ia-femme-et-sa-regulation", "Résumé Le cycle sexuel de la femme et sa régulation"),
    (243, "la-procreation", "Résumé La procréation"),
    (244, "genetiques-des-diploides", "Résumé Génétique des diploïdes"),
    (245, "genetique-humaine", "Résumé Génétique humaine"),
    (315, "genetique", "Résumé Génétique"),
    (744, "resume-la-reproduction-humaine-homme", "Résumé La reproduction humaine - Homme"),
    (745, "resume-la-reproduction-humaine-femme", "Résumé La reproduction humaine - Femme"),
    (949, "resume-2-genetique-humaine", "Résumé 2 génétique humaine"),
    (1132, "resume-homme", "Résumé Homme"),
    (1133, "resume-femme", "Résumé femme"),
    (1134, "resume-procreation", "Résumé Procréation"),
    (1135, "resume-brassages", "Résumé Brassages"),
    (1136, "resume-monohybridisme", "Résumé Monohybridisme"),
    (1137, "resume-genetiques-humaine", "Résumé génétique humaine"),
    (1138, "resume-tissue-nerveux", "Résumé Tissu nerveux"),
    (1139, "resume-reflexe-myotatique", "Résumé Réflexe myotatique"),
    (1554, "resume-genetique-humaine-2026", "Résumé Génétique humaine 2026"),
    (1701, "resume-la-reproduction-humaine-homme-bac-2027", "Résumé La reproduction humaine - Homme BAC 2027"),
    (146, "serie-homme-corrige", "Série Homme corrigé"),
    (147, "serie-femme-corrige", "Série femme corrigé"),
    (148, "serie-brassage-corrige", "Série brassage corrigé"),
    (413, "serie-corrigee-reproduction-humaine", "Série corrigée Reproduction humaine"),
    (424, "serie-2-homme-corrigee", "Série 2 Homme corrigée"),
    (425, "serie-2-femme-corrigee", "Série 2 Femme corrigée"),
    (426, "serie-3-femme-corrigee", "Série 3 Femme corrigée"),
    (427, "serie-1-procreation-corrigee", "Série 1 procréation corrigée"),
    (428, "serie-2-procreation-corrigee", "Série 2 procréation corrigée"),
    (429, "serie-2-brassage-corrigee", "Série 2 brassage corrigée"),
    (430, "serie-3-brassage-corrigee", "Série 3 brassage corrigée"),
    (431, "serie-1-genetique-humaine-corrigee", "Série 1 Génétique humaine corrigée"),
    (432, "serie-2-genetique-humaine-corrigee", "Série 2 Génétique humaine corrigée"),
    (433, "serie-1-neurophysiologie-corrigee", "Série 1 Neurophysiologie corrigée"),
    (434, "serie-2-neurophysiologie-corrigee", "Série 2 Neurophysiologie corrigée"),
    (435, "serie-1-immunite-corrigee", "Série 1 Immunité corrigée"),
    (436, "serie-2-immunite-corrigee", "Série 2 Immunité corrigée"),
    (699, "serie-reproduction-masculine-homme", "Série reproduction masculine - Homme"),
    (771, "serie-genetique-humaine-corrigee", "Série génétique humaine corrigée"),
    (1582, "serie-2-genetique-humaine-corrigee", "Série 2 génétique humaine corrigée (2)"),
    (1473, "serie-de-revison-genetique-formelle", "Série de révision : Génétique formelle"),
    (1543, "serie-de-revision-procreation-et-brassage", "Série de révision : procréation et brassage"),
    (246, "devoir-de-synthese-n1", "Devoir de synthèse n°1"),
    (247, "devoir-de-synthese-n1-correction", "Devoir de synthèse n°1 + Correction"),
    (248, "devoir-de-controle-n2-2015", "Devoir de contrôle n°2 2015"),
    (313, "devoir-de-controle-n1-svt-correction", "Devoir de contrôle n°1 SVT + Correction"),
    (314, "devoir-de-controle-n1-svt", "Devoir de contrôle n°1 SVT"),
    (359, "devoir-controle-n1-svt", "Devoir contrôle n°1 SVT"),
    (414, "devoir-de-controle-n1-correction", "Devoir de contrôle n°1 + correction"),
    (790, "devoir-de-controle-n-1-sujet-5", "Devoir de contrôle n°1 - sujet 5"),
    (794, "devoir-de-controle-n1-sujet-6", "Devoir de contrôle n°1 - Sujet 6"),
    (795, "devoir-de-synthese-n-1-sujet-4", "Devoir de synthèse n°1 - Sujet 4"),
    (808, "devoir-de-controle-n1-sujet-7-corrige", "Devoir de contrôle n°1 - Sujet 7 corrigé"),
    (809, "devoir-de-controle-n1-sujet-8-corrige", "Devoir de contrôle n°1 - Sujet 8 corrigé"),
    (810, "devoir-de-controle-n1-sujet-9-corrige", "Devoir de contrôle n°1 - Sujet 9 corrigé"),
    (811, "devoir-de-synthese-n1-sujet-5-corrige", "Devoir de synthèse n°1 - Sujet 5 corrigé"),
    (812, "devoir-de-synthese-n1-sujet-6-corrige", "Devoir de synthèse n°1 - Sujet 6 corrigé"),
    (813, "devoir-de-synthese-n1-sujet-7-corrige", "Devoir de synthèse n°1 - Sujet 7 corrigé"),
    (814, "devoir-de-synthese-n1-sujet-8-corrige", "Devoir de synthèse n°1 - Sujet 8 corrigé"),
    (971, "devoir-de-synthese-n2-sujet-1", "Devoir de synthèse n°2 - Sujet 1"),
    (972, "devoir-de-synthese-n2-sujet-2", "Devoir de synthèse n°2 - Sujet 2"),
    (973, "devoir-de-synthese-n2-sujet-3", "Devoir de synthèse n°2 - Sujet 3"),
    (974, "devoir-de-synthese-n2-sujet-4", "Devoir de synthèse n°2 - Sujet 4"),
    (1589, "devoir-de-synthese-n2-2026", "Devoir de synthèse n°2 (2026)"),
    (724, "parascolaire-svbac-avec-corriges", "Parascolaire S.V.Bac avec corrigés"),
    (1131, "revision-toute-lannee", "Révision toute l'année"),
    (1140, "revision-immunite", "Révision Immunité"),
    (1645, "fascicule-de-revision-aaam-kaml", "Fascicule de révision (année complète)"),
]

# (file_id, year, session, kind) — official bac SVT exams, section Sciences expérimentales
BAC_EXAMS = [
    (52, 2008, "principale", "sujet"), (53, 2008, "principale", "corrige"),
    (54, 2008, "controle", "sujet"), (55, 2008, "controle", "corrige"),
    (56, 2009, "principale", "sujet"), (57, 2009, "principale", "corrige"),
    (58, 2009, "controle", "sujet"), (59, 2009, "controle", "corrige"),
    (60, 2010, "principale", "sujet"), (61, 2010, "controle", "sujet"),
    (62, 2011, "principale", "sujet"), (63, 2011, "principale", "corrige"),
    (64, 2011, "controle", "sujet"),
    (65, 2012, "principale", "sujet"), (66, 2012, "principale", "corrige"),
    (67, 2012, "controle", "sujet"), (68, 2012, "controle", "corrige"),
    (69, 2013, "principale", "sujet"), (70, 2013, "principale", "corrige"),
    (71, 2013, "controle", "sujet"), (72, 2013, "controle", "corrige"),
    (73, 2014, "principale", "sujet"), (74, 2014, "controle", "sujet"),
    (75, 2015, "principale", "sujet"), (76, 2015, "principale", "corrige"),
    (77, 2015, "controle", "sujet"), (78, 2015, "controle", "corrige"),
    (79, 2016, "principale", "sujet"), (80, 2016, "principale", "corrige"),
    (81, 2016, "controle", "sujet"), (82, 2016, "controle", "corrige"),
    (83, 2017, "principale", "sujet"), (84, 2017, "principale", "corrige"),
    (85, 2017, "controle", "sujet"), (86, 2017, "controle", "corrige"),
    (87, 2018, "principale", "sujet"), (88, 2018, "principale", "corrige"),
    (89, 2018, "controle", "sujet"), (90, 2018, "controle", "corrige"),
    (91, 2019, "principale", "sujet"), (92, 2019, "principale", "corrige"),
    (93, 2019, "controle", "sujet"), (94, 2019, "controle", "corrige"),
    # Listed out of order on the site — titles say these years; verify after download.
    (95, 2010, "principale", "corrige"), (96, 2010, "controle", "corrige"),
    (97, 2014, "principale", "corrige"), (98, 2014, "controle", "corrige"),
    (99, 2011, "controle", "corrige"),
]

# Title keyword -> concepts (document-level hint; chunks are re-tagged by content at ingestion)
TITLE_CONCEPTS = [
    ("immunitaire specifique", ["reponse_specifique"]),
    ("immunite", ["soi_non_soi", "reponse_non_specifique", "reponse_specifique", "dysfonctionnement_immunitaire"]),
    ("pression arterielle", ["regulation_pa"]),
    ("reflexe", ["reflexe_myotatique"]),
    ("neurophysiologie", ["tissu_nerveux", "synapse", "reflexe_myotatique", "regulation_pa"]),
    ("nerveux", ["tissu_nerveux", "synapse"]),
    ("genetique humaine", ["genetique_humaine"]),
    ("genetiques humaine", ["genetique_humaine"]),
    ("genetique formelle", ["monohybridisme", "dihybridisme"]),
    ("diploides", ["monohybridisme", "dihybridisme"]),
    ("monohybridisme", ["monohybridisme"]),
    ("brassage", ["brassage"]),
    ("procreation", ["procreation"]),
    ("cycle sexuel", ["repro_femme", "regulation_hormonale"]),
    ("femme", ["repro_femme", "regulation_hormonale"]),
    ("feminine", ["repro_femme", "regulation_hormonale"]),
    ("homme", ["repro_homme", "regulation_hormonale"]),
    ("masculine", ["repro_homme"]),
    ("reproduction", ["repro_homme", "repro_femme"]),
    ("genetique", ["brassage", "monohybridisme", "dihybridisme", "genetique_humaine"]),
]


def doc_type(title: str) -> str:
    t = normalize(title)
    for prefix, kind in [("cours", "cours"), ("resume", "resume"), ("serie", "serie"),
                         ("devoir", "devoir"), ("parascolaire", "revision"), ("revision", "revision"),
                         ("fascicule", "revision")]:
        if t.startswith(prefix):
            return kind
    return "autre"


def title_concepts(title: str) -> list[str]:
    t = normalize(title)
    for key, concepts in TITLE_CONCEPTS:
        if key in t:
            return concepts
    return []  # mixed documents (devoirs, révisions): tagged chunk by chunk


def build() -> list[dict]:
    docs = []
    for doc_id, slug, title in COURSE_DOCS:
        t = normalize(title)
        docs.append({
            "doc_id": f"doc-{doc_id}",
            "title": title,
            "doc_type": doc_type(title),
            "has_correction": "corrig" in t or "correction" in t,
            "concepts": title_concepts(title),
            "year": None,
            "session": None,
            "page_url": f"{SITE}/sciences-experimentales/{slug}/{doc_id}",
            "pdf_url": f"{SITE}/public/uploads/documents/{SUBJECT_ID}_{doc_id}.pdf",
            "source": "bac-done.com",
        })
    for file_id, year, session, kind in BAC_EXAMS:
        label = "Corrigé" if kind == "corrige" else "Sujet"
        docs.append({
            "doc_id": f"bac-{year}-{session}-{kind}-{file_id}",
            "title": f"Bac {year} SVT — session {session} — {label}",
            "doc_type": "bac_corrige" if kind == "corrige" else "bac_sujet",
            "has_correction": kind == "corrige",
            "concepts": [],
            "year": year,
            "session": session,
            "page_url": f"{SITE}/bacs/science-de-la-vie-et-de-la-terre/sujets/{SUBJECT_ID}",
            "pdf_url": f"{SITE}/public/uploads/documents/bacs/{SUBJECT_ID}_{file_id}.pdf",
            "source": "bac-done.com",
        })
    return docs


if __name__ == "__main__":
    out = ROOT / "data" / "catalog.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    catalog = build()
    out.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    by_type: dict[str, int] = {}
    for d in catalog:
        by_type[d["doc_type"]] = by_type.get(d["doc_type"], 0) + 1
    print(f"Wrote {len(catalog)} documents to {out}: {by_type}")
