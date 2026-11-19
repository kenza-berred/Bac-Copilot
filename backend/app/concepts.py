"""SVT curriculum concept graph — 4ème année secondaire, section Sciences expérimentales (Tunisie).

Each concept has:
  - a chapter (the official curriculum theme),
  - prerequisites (edges of the graph, used by the student model to find root causes),
  - a keyword lexicon used to tag chunks and questions with concepts.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Concept:
    id: str
    label: str
    chapter: str
    prerequisites: tuple[str, ...] = ()
    keywords: tuple[str, ...] = field(default_factory=tuple)


CHAPTERS = {
    "reproduction": "Reproduction humaine et santé",
    "genetique": "Génétique et évolution",
    "neurophysiologie": "Neurophysiologie",
    "immunite": "Immunité",
}

CONCEPTS: dict[str, Concept] = {
    c.id: c
    for c in [
        # --- Reproduction humaine ---
        Concept("repro_homme", "Fonction reproductrice masculine", "reproduction", (),
                ("testicule", "spermatogenese", "spermatozoide", "testosterone", "leydig", "sertoli",
                 "tube seminifere", "appareil reproducteur masculin", "homme")),
        Concept("repro_femme", "Fonction reproductrice féminine et cycles", "reproduction", (),
                ("ovaire", "ovogenese", "follicule", "cycle ovarien", "cycle uterin", "ovulation",
                 "corps jaune", "oestrogene", "progesterone", "endometre", "folliculogenese", "femme")),
        Concept("regulation_hormonale", "Régulation hormonale (axe hypothalamo-hypophysaire)", "reproduction",
                ("repro_homme", "repro_femme"),
                ("hypothalamus", "hypophyse", "gnrh", "fsh", "lh", "retrocontrole", "feedback",
                 "regulation hormonale")),
        Concept("procreation", "Procréation (fécondation, grossesse, maîtrise)", "reproduction",
                ("repro_homme", "repro_femme", "regulation_hormonale"),
                ("fecondation", "nidation", "grossesse", "hcg", "contraception", "pilule", "fiv",
                 "procreation", "zygote", "placenta", "accouchement", "pma")),
        # --- Génétique ---
        Concept("brassage", "Méiose et brassage génétique", "genetique", ("repro_homme", "repro_femme"),
                ("meiose", "brassage", "interchromosomique", "intrachromosomique", "crossing-over",
                 "crossing over", "chiasma", "gamete", "anaphase", "prophase")),
        Concept("monohybridisme", "Monohybridisme", "genetique", ("brassage",),
                ("monohybridisme", "dominance", "codominance", "recessif", "dominant", "allele",
                 "homozygote", "heterozygote", "f1", "f2", "lignee pure")),
        Concept("dihybridisme", "Dihybridisme (gènes indépendants / liés)", "genetique",
                ("monohybridisme", "brassage"),
                ("dihybridisme", "genes lies", "genes independants", "test-cross", "test cross",
                 "recombine", "recombinaison", "carte factorielle", "phenotype parental")),
        Concept("genetique_humaine", "Génétique humaine", "genetique", ("monohybridisme",),
                ("arbre genealogique", "pedigree", "autosomal", "lie au sexe", "chromosome x",
                 "hemophilie", "daltonisme", "caryotype", "trisomie", "conseil genetique",
                 "genetique humaine", "drepanocytose", "myopathie")),
        # --- Neurophysiologie ---
        Concept("tissu_nerveux", "Tissu nerveux et message nerveux", "neurophysiologie", (),
                ("neurone", "potentiel de repos", "potentiel d'action", "axone", "myeline",
                 "fibre nerveuse", "nerf", "oscilloscope", "seuil", "periode refractaire",
                 "conduction", "tissu nerveux", "canaux", "pompe na")),
        Concept("synapse", "Transmission synaptique et intégration", "neurophysiologie", ("tissu_nerveux",),
                ("synapse", "neurotransmetteur", "acetylcholine", "pps", "ppse", "ppsi", "sommation",
                 "integration", "fente synaptique", "exocytose", "gaba")),
        Concept("reflexe_myotatique", "Réflexe myotatique", "neurophysiologie", ("synapse",),
                ("reflexe myotatique", "fuseau neuromusculaire", "motoneurone", "muscle antagoniste",
                 "arc reflexe", "innervation reciproque", "etirement", "reflexe")),
        Concept("regulation_pa", "Régulation nerveuse de la pression artérielle", "neurophysiologie",
                ("reflexe_myotatique",),
                ("pression arterielle", "barorecepteur", "sinus carotidien", "crosse aortique",
                 "bulbe rachidien", "parasympathique", "orthosympathique", "frequence cardiaque",
                 "hypertension", "vasomotricite")),
        # --- Immunité ---
        Concept("soi_non_soi", "Le soi et le non-soi", "immunite", (),
                ("soi", "non-soi", "cmh", "hla", "antigene", "groupe sanguin", "marqueur")),
        Concept("reponse_non_specifique", "Réponse immunitaire non spécifique", "immunite", ("soi_non_soi",),
                ("phagocytose", "inflammation", "macrophage", "polynucleaire", "non specifique",
                 "reaction inflammatoire", "diapedese")),
        Concept("reponse_specifique", "Réponse immunitaire spécifique (humorale et cellulaire)", "immunite",
                ("reponse_non_specifique",),
                ("lymphocyte", "anticorps", "lb", "lt4", "lt8", "plasmocyte", "immunoglobuline",
                 "complexe immun", "selection clonale", "interleukine", "mediation humorale",
                 "mediation cellulaire", "memoire immunitaire", "vaccination", "cytotoxique")),
        Concept("dysfonctionnement_immunitaire", "Dysfonctionnements (SIDA, allergies)", "immunite",
                ("reponse_specifique",),
                ("sida", "vih", "allergie", "immunodeficience", "seropositif", "retrovirus")),
    ]
}


def normalize(text: str) -> str:
    """Lowercase + strip accents so 'Méiose' matches 'meiose'."""
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


_PATTERNS = {
    cid: [re.compile(r"\b" + re.escape(k) + r"\b") for k in c.keywords] for cid, c in CONCEPTS.items()
}


def tag_concepts(text: str, min_hits: int = 2, max_concepts: int = 3) -> list[str]:
    """Return the concepts whose keywords appear most often in `text`.

    Very short generic keywords (e.g. "homme", "soi") only count once, so a concept needs
    `min_hits` distinct keyword hits to be assigned.
    """
    norm = normalize(text)
    scores: dict[str, int] = {}
    for cid, patterns in _PATTERNS.items():
        hits = sum(1 for p in patterns if p.search(norm))
        if hits >= min_hits:
            scores[cid] = hits
    ranked = sorted(scores, key=lambda c: scores[c], reverse=True)
    return ranked[:max_concepts]


def prerequisites_closure(concept_id: str) -> list[str]:
    """All (transitive) prerequisites of a concept, nearest first."""
    seen: list[str] = []
    frontier = list(CONCEPTS[concept_id].prerequisites)
    while frontier:
        cid = frontier.pop(0)
        if cid not in seen:
            seen.append(cid)
            frontier.extend(CONCEPTS[cid].prerequisites)
    return seen


def graph_as_dict() -> dict:
    return {
        "chapters": CHAPTERS,
        "nodes": [
            {"id": c.id, "label": c.label, "chapter": c.chapter} for c in CONCEPTS.values()
        ],
        "edges": [
            {"from": p, "to": c.id} for c in CONCEPTS.values() for p in c.prerequisites
        ],
    }
