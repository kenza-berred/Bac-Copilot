# Rapport technique — plan proposé

1. **Introduction**
   - Contexte : la préparation du bac en Tunisie et l'accès inégal au soutien scolaire.
   - Problème : un chatbot générique invente des réponses, ne cite rien et ne s'adapte pas à l'élève.
   - Objectifs et contributions.
2. **État de l'art (court)**
   - RAG et RAG hybride (BM25 + dense, RRF, reranking).
   - Agents (LangGraph) et autovérification.
   - MCP.
   - Knowledge tracing (BKT) et répétition espacée.
   - Correction automatique de réponses courtes.
3. **Données**
   - Corpus bac-done : 81 documents de cours et 48 sujets de bac (statistiques : pages, pages OCR, chunks par type).
   - Graphe des 16 concepts du programme.
   - Questions d'évaluation et annotation.
4. **Architecture** (s'appuyer sur `docs/ARCHITECTURE.md`)
   - Ingestion.
   - Recherche.
   - Agent (inclure le diagramme du graphe).
   - Modèle élève.
   - MCP.
   - Interface (captures d'écran).
5. **Évaluation** (s'appuyer sur `docs/EVALUATION.md`)
   - 5.1 Recherche : tableau des 4 modes, résultats par langue, ablation sur la taille des chunks.
   - 5.2 Génération : baseline contre agent, et accord entre le juge LLM et les notes humaines.
   - 5.3 Correction automatique : accord avec les notes humaines, barème officiel contre barème généré.
   - 5.4 Modèle élève : AUC sur ASSISTments, et simulation des politiques de révision (inclure la première politique, moins performante, et la correction apportée).
6. **Démonstration** : scénario d'un élève qui se trompe sur le dihybridisme et que le copilote renvoie vers le brassage génétique.
7. **Limites et perspectives**
   - Figures et schémas, OCR.
   - Biais de l'annotation.
   - Fine-tuning d'un petit modèle correcteur (optionnel).
   - Extension à la physique et aux maths.
   - Version mobile.
8. **Conclusion**

Annexes : prompts, exemples de corrections, liste des outils MCP.
