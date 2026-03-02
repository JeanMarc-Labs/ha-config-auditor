# Changelog — H.A.C.A

Toutes les modifications notables de ce projet sont documentées ici.

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.0.3/)  
Versionnement : [Semantic Versioning](https://semver.org/lang/fr/)

---
## [1.0.3] — 2026-03-03 — Internationnalisation de textes en dur et fixation de bugs

## [1.0.2] — 2026-03-02 — Internationnalisation de textes en dur et fixation de bugs

## [1.0.1] — 2026-03-01 — Internationnalisation de textes en dur

## [1.0.0] — 2026-02-26 — Première release publique

### Ajouté

- **Analyseur d'automations** (Module 1) — détection `device_id`, modes incorrects, services inconnus, références cassées, doublons exacts et fonctionnels
- **Moniteur de santé des entités** (Module 2) — entités fantômes, indisponibles, désactivées mais référencées, doublons de registre
- **Analyseur de performances** (Module 3) — automations haute fréquence, templates à rafraîchissement élevé, patterns en boucle
- **Générateur de rapports** (Module 4) — rapports MD, JSON et PDF horodatés dans `/config/haca_reports/`
- **Refactoring Assistant** (Module 5) — correction automatique `device_id → entity_id`, modes, templates simples ; sauvegarde YAML avant chaque correction
- **Assistant IA** (Module 6) — explication des issues et suggestions via OpenAI / Google Generative AI
- **Analyseur de sécurité** (Module 7) — détection d'expositions et mauvaises pratiques
- **Analyseur de dashboards** (Module 9) — entités manquantes dans les vues Lovelace
- **Monitoring événementiel** (Module 10) — scan automatique debounced sur modification de config HA
- **Analyseur Recorder** (Module 11) — entités orphelines en SQLite, estimation espace gaspillé, purge en un clic
- **Historique d'audit** (Module 12) — snapshots horodatés, courbe de score de santé, suppression individuelle/groupée
- **Graphe de dépendances** — visualisation D3.js force-directed, filtres par type/issues, export SVG et PNG
- **Moniteur de batteries** — tableau de toutes les batteries, alertes par sévérité
- **Score de santé global** — score 0-100 calculé sur l'ensemble des issues, affiché avec tendance
- **Complexité d'automations** — classement par score de complexité avec métriques détaillées
- Panel personnalisé HA avec 8 onglets principaux et sous-onglets par catégorie
- Filtres par sévérité (HIGH / MEDIUM / LOW) et export CSV sur chaque liste d'issues
- Recherche textuelle dans le graphe de dépendances
- Notifications persistantes HA pour les nouvelles issues HIGH détectées
- Support multilingue français / anglais
- Config flow HA avec options configurables (intervalle scan, délai démarrage, monitoring événementiel)
- 119 tests unitaires et de régression


