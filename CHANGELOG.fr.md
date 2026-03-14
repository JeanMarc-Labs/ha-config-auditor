# Changelog — H.A.C.A

Toutes les modifications notables de ce projet sont documentées ici.

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/)
Versionnement : [Semantic Versioning](https://semver.org/lang/fr/)

---

## [1.5.2] — 2026-03-14 — LLM API natif, sécurité renforcée, relations graphe et qualité code

### Ajouté

- **LLM API HA natif** — HACA s'enregistre comme LLM API dans Home Assistant. Configuration unique dans Paramètres → Assistants vocaux → [votre agent] → LLM API → HACA. Mistral, Gemini, Llama et tout agent conversation HA peuvent ensuite utiliser les 58 outils HACA nativement, sans hacks de prompt ni parsing intermédiaire
- **Fallback Chat automatique** — si l'agent préféré échoue (quota dépassé, timeout), l'agent suivant est essayé automatiquement. Fonctionne avec tous les agents configurés dans HA, l'agent favori toujours en tête
- **Modale de correction simple** — les issues à correction de champ simple (`no_description`, `no_alias`) affichent désormais une modale avec la suggestion IA dans un champ texte éditable et trois actions : Fermer, Modifier manuellement (ouvre l'éditeur HA), Appliquer par IA (écrit le YAML directement, pas de sauvegarde nécessaire)
- **Graphe de dépendances — sidebar relations** — clic sur un nœud affiche désormais les sections "Utilisé par" et "Utilise" avec navigation cliquable entre nœuds
- **Graphe de dépendances — exports relations** — boutons CSV et Markdown dans le sidebar (par nœud) et la toolbar (graphe complet). Le rapport Markdown regroupe les nœuds par type (automations → scripts → scènes…) avec détection des orphelins
- **Fréquence du rapport configurable** — dans la section Agent IA Proactif de l'onglet Config, un sélecteur permet de choisir : Quotidien, Hebdomadaire (défaut), Mensuel, ou Jamais (désactivé). La vérification automatique se fait une fois par jour au lieu d'une fois par heure
- **`_safe_write_and_reload`** — nouvel helper dans `mcp_server.py` : écriture atomique, rechargement, et restauration automatique du fichier original si le rechargement échoue. Utilisé dans `update_automation`, `remove_automation`, `update_script`
- **`_auto_backup` unifié** — `_auto_backup` délègue désormais entièrement à `_tool_ha_backup_create` (source unique de vérité pour la logique backup). Les 11 outils MCP destructifs déclenchent un backup automatique en arrière-plan avant l'écriture
- **70 tests** dans les fichiers de tests mis à jour/nouveaux couvrant : protection admin, fallback chat, écriture atomique, auto-backup, traversal de chemin, structure LLM API, rate limiting, timeout deep_search

### Corrigé

- **Compteur outils panel MCP** — le panel affichait "33 outils" au lieu des 65 réels. Les 65 outils sont maintenant affichés dans 11 catégories (ajout : Blueprints, Scènes, Fichiers de configuration)
- **`_async_find_all_ai_task_entities`** — l'agent préféré n'était jamais placé en tête car `conversation_engine` (ex: `conversation.google_xxx`) et les entity_id `ai_task` ont des formats différents. Corrigé via `config_entry_id` dans le registre d'entités
- **`handle_apply_field_fix` match ambigu** — le fallback `msg.get("alias", item_alias)` matchait toujours la première automation. Remplacé par un système à deux passes : id HA numérique d'abord, puis alias exact
- **Heuristique slug `_tool_ha_remove_automation`** — `alias.lower().replace(" ", "_")` pouvait confondre des automations aux noms similaires. Remplacé par le même système à deux passes
- **Sidebar graphe de dépendances vide** — D3.js mute les champs `source`/`target` des edges d'strings en objets pendant la simulation. La comparaison `e.source === node.id` ne matchait jamais. Corrigé par `_edgeSrc(e)` / `_edgeTgt(e)`
- **Données sidebar perdues au refresh** — les données du nœud (`usedBy`, `uses`, `allNodes`) sont maintenant sauvegardées dans `sb._hacaNodeData` pour que les exports CSV/MD fonctionnent même après que `_graphStopAll()` met `_graphRawData = null`
- **Clés de traduction dans la mauvaise section JSON** — les nouvelles clés étaient placées à la racine (`graph.*`, `misc.*`) au lieu de sous `panel.*` où `this.t()` les cherche. Corrigé dans les 13 fichiers de langue
- **Version `manifest.json`** — était `1.5.0`, maintenant `1.5.2`
- **Fichiers de traduction** — 12 langues avaient 66–108 clés `panel.diag_prompts.*` manquantes ; comblées avec les valeurs EN en fallback
- **Intervalle de vérification rapport automatique** — réduit de toutes les heures à une fois par jour

### Sécurité

- **`@require_admin`** sur tous les handlers WebSocket destructifs (18 handlers) : `apply_fix`, `restore_backup`, `purge_recorder_orphans`, `apply_field_fix`, `chat`, `save_options`, `delete_history`, `ai_suggest_fix`, `set_log_level`, `agent_force_report`, `record_fix_outcome`, `get_battery_predictions`, `export_battery_csv`, `get_redundancy`, `get_recorder_impact`, `get_history_diff`, `scan_all`, `preview_fix`
- **Écritures YAML atomiques** — nouvel helper `_atomic_write(path, content)` : écrit dans `.tmp` puis `os.replace()`. Plus de risque de YAML corrompu si HA crashe pendant l'écriture
- **Protection traversal de chemin** — `_tool_ha_get_config_file` et `_tool_ha_update_config_file` utilisent maintenant `os.path.realpath()` pour résoudre les symlinks et les séquences `../` avant de vérifier la limite du répertoire de configuration

### Supprimé

- **Bouton Correctif IA dans l'onglet Conformité** — les problèmes de conformité (noms manquants, icônes, zones) ne nécessitent pas d'IA — utiliser directement l'éditeur HA
- **Nettoyage du code mort** :
  - `_agent_has_native_tools` + `_HA_BUILTIN_AGENTS` — obsolètes depuis le LLM API natif
  - `_sanitize_tools_for_converse` — plus nécessaire ; les outils sont injectés nativement
  - `_truncate_for_converse` — plus nécessaire ; le prompt n'est plus envoyé via `async_converse`
  - `_async_find_llm_agent` — alias déprécié sans appelant
  - `_HacaJsonEncoder` — utilisé par la boucle `[HACA_ACTION:]` supprimée
  - 7 clés de traduction mortes (`compliance.btn_ai_fix`, `compliance.ai_fix_*`) dans les 13 fichiers de langue
  - `conversation.py` réduit de 705 → 526 lignes (−25%)

---

## [1.5.1] — 2026-03-12 — Correctifs boucle IA, routing boutons et qualité code

### Corrigé

- **Boucle agentique — break-on-success** — la boucle s'arrêtait incorrectement après le premier outil réussi (ex: `ha_backup_create`), empêchant l'exécution des étapes suivantes
- **MAX_STEPS exhaustion** — lorsque les 12 étapes sont atteintes sans réponse finale, le dernier résultat d'outil utile (`last_tool_summary`) est retourné
- **Routing boutons IA — 74 types d'issues** — `_buildActionPrompt()` dispatche 66 types vers le Chat et 8 types purement informationnels vers `explainWithAI()` en fallback
- **Modale intermédiaire — Redondances et Carte Zones** — Chat direct sans modale intermédiaire
- **Messages hardcodés FR/EN dans `mcp_server.py`** — 6 messages normalisés en anglais

### Ajouté

- **49 nouveaux tests** (386 → 435)

---

## [1.5.0] — 2026-03-12 — Prédicteur batterie, Complexité zones, Analyseur redondances, Impact Recorder

### Ajouté

- **Prédicteur de batteries** (Module 18) — régression linéaire sur l'historique HA ; prédiction des dates de remplacement ; alertes 7 jours à l'avance ; export CSV
- **Analyseur de complexité de zones** (Module 19) — score de complexité composite par zone ; heatmap interactive ; suggestions de fusion/découpage
- **Analyseur de redondances** (Module 20) — chevauchements logiques, candidats blueprint (≥3 automations identiques), fonctionnalités natives HA
- **Analyseur d'impact Recorder** (Module 21) — écritures/jour, Mo/an, bloc YAML `recorder: exclude:` prêt à copier
- **Boucle agentique portée à 12 étapes**
- **12 agents MCP documentés** dans le panneau de configuration

---

## [1.4.3] — 2026-03-11 — Corrections UI/UX, unification des labels conformité, améliorations mobile

### Corrigé

- Labels des types de conformité unifiés sur 13 langues
- Boutons de configuration trop hauts sur mobile
- Disparition de la liste de conformité au refresh
- Icône de l'onglet Helpers (`cog-box` → `cog-outline`)
- Défilement des sous-onglets sur mobile
- Contraste de la note batteries

### Ajouté

- Améliorations de la modal IA de Conformité (boutons Détails + Ouvrir paramètres)
- Vérifications de conformité des Helpers (`compliance_helper_no_icon`, `compliance_helper_no_area`)
- Liste individuelle des entités sans zone (jusqu'à 150, puis récapitulatif)
- Section Conformité dans la Configuration (10 types configurables)
- Améliorations de la pagination (Page X/N, boutons première/dernière page)

---

## [1.4.2] — 2026-03-09 — Analyse de conformité, onglet Helpers, Chat IA et serveur MCP

### Ajouté

- **Onglet Conformité** — audit qualité des métadonnées
- **Onglet Helpers** — tous les `input_*` et timers, détection des helpers inutilisés
- **Assistant Chat IA** — assistant conversationnel avec contexte de santé
- **Serveur MCP** — serveur Model Context Protocol intégré, 58 outils
- **Support du label `haca_ignore`**
- **Système de traduction 13 langues** — refonte complète

---

## [1.4.0] — 2026-03-09 — Graphe de scripts, analyse de scènes, analyseur de groupes et candidats blueprints

### Ajouté

- Script Graph Analyzer (Module 13)
- Advanced Scene Analyzer
- Blueprint Candidate Detection
- Group Analyzer (Module 14)
- 110 nouveaux tests unitaires

---

## [1.2.0] — 2026-03-08 — Analyse multi-source des automatisations, analyse des helpers et améliorations UX

### Ajouté

- Bouton Open Entity
- Scan multi-source des automations
- Analyse des input helpers
- Analyse des capteurs de template
- Analyse des timer helpers

---

## [1.1.1] — 2026-03-06 — Réécriture du système d'internationalisation

### Ajouté

- Système d'internationalisation 13 langues
- Label `haca_ignore`

---

## [1.0.0] — 2026-02-26 — Première release publique

### Ajouté

- Analyseur d'automatisations (Module 1)
- Moniteur de santé des entités (Module 2)
- Analyseur de performances (Module 3)
- Générateur de rapports (Module 4)
- Refactoring Assistant (Module 5)
- Assistant IA (Module 6)
- Analyseur de sécurité (Module 7)
- Analyseur de dashboards (Module 8)
- Monitoring événementiel (Module 9)
- Analyseur Recorder (Module 10)
- Historique d'audit (Module 11)
- Graphe de dépendances (D3.js)
- Moniteur de batteries
- Score de santé global (capteur HA)
- 119 tests unitaires et de régression
