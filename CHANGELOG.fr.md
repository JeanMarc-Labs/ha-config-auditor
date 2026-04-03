# Changelog — H.A.C.A

Toutes les modifications notables de ce projet sont documentées ici.

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/)
Versionnement : [Semantic Versioning](https://semver.org/lang/fr/)

---
## [1.7.1] — 2026-04-03 — Corrections mineures

### Corrigé

- **Notifications dans la langue de l'utilisateur** — les notifications sont maintenant dans la langue de l'utilisateur


---
## [1.7.0] — 2026-04-01 — Moniteur d'intégrations

### Ajouté

- **Onglet Intégrations** — liste toutes les intégrations installées avec badges typés (HACS violet, Core bleu, Custom orange, Card rose, Theme vert, App doré), statut en service/inutilisé, version, nombre d'entités, ancienneté et liens documentation
- **Add-ons Supervisor** — détectés via `hassio_supervisor_info`, affichés avec badge APP et couleur `rgb(241,196,71)`
- **Détection d'orphelins** — intégrations ayant des entités sans config entry active signalées par un badge orange
- **Analyse IA** — bouton "IA" sur les intégrations inutilisées/orphelines, ouvre le chat avec un prompt structuré
- **Export CSV / MD** — liste complète exportable en CSV ou en rapport Markdown groupé par type
- **Carte stat dashboard** — carte cliquable "Intégrations" (violet) sur le tableau de bord principal
- **Pagination** — 25 éléments par page avec navigation
- **Recherche et tri** — filtre par nom/domaine, tri par nom/type/entités/ancienneté

### Modifié

- **Vérification `unknown_state`** — contextuelle : domaines où unknown est normal exclus ; autres domaines uniquement signalés si référencés par des automatisations
- **Prompts IA blueprint** — instructions explicites d'utiliser `ha_create_blueprint()` au lieu d'expliquer manuellement
- **Placeholders traduction** — correction `{CATÉGORIE}` → `{CATEGORY}` dans les 12 langues non-anglaises

---

## [1.6.4] — 2026-03-28 — Système d'ID d'issues, AI Fix batch, catalogue d'issues

### Ajouté

- **Identifiants uniques d'issues** — chaque issue détectée a désormais un identifiant stable et lisible au format `HACA-{CATÉGORIE}-{TYPE}-{HASH6}` (ex : `HACA-AUTO-NO_ALIAS-a3f2c1`). Les IDs sont affichés dans tous les listings d'issues (onglets principaux + tableau conformité) avec copie au clic. Le hash est dérivé de l'entity_id pour garantir l'unicité
- **Outil `haca_list_issue_catalog`** — nouvel outil MCP/LLM qui retourne le catalogue complet : 10 catégories avec codes courts (AUTO, SCRIPT, SCENE, BP, ENT, HELPER, PERF, SEC, DASH, COMPL), tous les types d'issues par catégorie (76 types), sévérités, statut corrigible, et compteurs live du scan en cours
- **Outil `haca_fix_batch`** — nouvel outil MCP/LLM pour correction unitaire ou en lot. Accepte `issue_id` pour une correction unique, ou `category` + `type` + `severity` pour un lot. `dry_run=true` par défaut (prévisualisation), `dry_run=false` requis après confirmation utilisateur
- **Section AI Fix Reference** — nouvelle section dans l'onglet MCP/IA montrant le format d'ID, les codes de catégories, les niveaux de sévérité, et 5 exemples de prompts IA copiables. Traduit en 13 langues
- **Badge Fixable** — les issues auto-corrigibles affichent un badge vert « FIXABLE » à côté de leur titre
- **Workflow fix dans le prompt LLM** — le system prompt injecté aux agents IA inclut maintenant le workflow de correction (catalogue → liste → prévisualisation → application). Traduit en 13 langues

### Modifié

- **IDs dans la réponse `haca_get_issues`** — chaque issue inclut maintenant le code `category` et l'ID au nouveau format `HACA-*` (rétrocompatible : l'ancien format `entity_id|type` est toujours accepté)
- **Filtre catégorie `haca_get_issues`** — accepte maintenant `helper` et `blueprint` (manquants précédemment)
- **Compteur d'outils corrigé** — 67 outils (affiché incorrectement comme 65)
- **Prompt système MCP mis à jour** — ajout des lignes workflow FIX SINGLE, FIX BATCH et CATALOG

### Corrigé

- **Rétrocompatibilité `_find_issue_by_id`** — accepte le nouveau format `HACA-*`, l'ancien format pipe `entity_id|type`, l'entity_id brut, et la recherche par alias

---

## [1.6.3] — 2026-03-25 — Dashboard auto-généré, correction trigger rate, scripts renommés, variables template, purge

### Ajouté

- **Dashboard HACA auto-généré** — bouton "Créer Dashboard" sous les cartes de stats (séparé du bouton Scan pour éviter les erreurs de clic). Utilise les commandes WebSocket natives de HA (`lovelace/dashboards/create` + `lovelace/config/save`) pour que le dashboard apparaisse instantanément dans la barre latérale sans redémarrage. Contient : jauge Score HACA (carte custom), introduction markdown, compteurs d'issues en cartes tile (4 primaires + 4 secondaires + 3 tertiaires en horizontal stacks), alertes batteries + orphelins recorder, graphique historique 7 jours, carte dashboard HACA (custom), et un bouton d'accès au panel. Un re-clic met à jour le dashboard. Traduit en 13 langues

- **Filtres de sévérité** — 3 nouveaux toggles dans l'onglet Configuration pour afficher/masquer les issues par niveau de sévérité (Haute, Moyenne, Basse). Traduit en 13 langues
- **Bouton dashboard déplacé dans Configuration** — le bouton "Créer Dashboard" est maintenant dans sa propre section en bas de l'onglet Configuration, avec un texte explicatif. Séparé du bouton Scan pour éviter les clics accidentels
- **Tous les textes du dashboard traduits** — chaque texte du dashboard auto-généré utilise des clés de traduction `panel.dashboard.*`. Zéro texte hardcodé

### Corrigé

- **Fausses alertes "possible loop" supprimées** — `_analyze_trigger_rate` était fondamentalement défectueux : un seul timestamp `last_triggered` ne mesure pas la fréquence. Une automatisation déclenchée il y a 16s a simplement tourné récemment. La détection structurelle de boucle reste active
- **Scripts renommés toujours signalés comme inutilisés** — `_load_script_configs()` construisait les entity_id depuis les slugs YAML. Si l'utilisateur renommait l'entity_id, l'ancien slug ne correspondait plus. Résolution via le registre d'entités
- **Variables template signalées comme entités manquantes** — les scripts utilisant `entity_id: "{{ target_device }}"` étaient ajoutés aux références comme de vraies entités. La section scripts utilise maintenant le helper `_add_ref()` qui valide le format
- **Purge orphelins silencieusement en échec** — deux bugs JS/Python corrigés : `this._this.showToast()` → `this._showToast()`, et fallback session SQLAlchemy pour HA récents
- **Faux positifs doublons blueprint** — les automatisations `use_blueprint` exclues de la détection de doublons
- **Faux positifs entités zombies** — validation du format entity_id, rejection des device_id hex

### Modifié

- **Version** : 1.6.2 → 1.6.3
- **Tests** : 486 passés, 0 échoué, 32 ignorés

---

## [1.6.2] — 2026-03-23 — Correction blueprint, nettoyage i18n, refonte prompt LLM, outils Lovelace

### Ajouté

- **Prompt LLM API multilingue** — le prompt système injecté dans les agents IA charge maintenant depuis `translations/{lang}.json → llm_prompt` (18 clés × 13 langues). Précédemment en français hardcodé
- **Workflows IA proactifs** — le prompt inclut des workflows étape par étape pour les dashboards Lovelace, les automatisations et les scripts. L'agent IA sait maintenant appeler `ha_get_lovelace` avant d'ajouter des cartes et utilise `view_index=0` automatiquement quand il n'y a qu'une seule vue
- **58 descriptions d'outils enrichies** — chaque outil MCP inclut maintenant les appels prérequis, les actions de suivi et des conseils d'utilisation
- **Guide étendu Claude Desktop** — installation pas à pas avec `winget install astral-sh.uv -e` (Windows) / `curl` (macOS/Linux), chemins du fichier de config et instructions de redémarrage. Traduit en 13 langues
- **Guide étendu Antigravity / Gemini** — installation pas à pas avec `pip install mcp-proxy`, traduit en 13 langues
- **Bannière avertissement IP** — affichée en haut du panel MCP : utiliser l'adresse IP si `.local` ne fonctionne pas. Traduit en 13 langues
- **Attribut `alert_entities`** — le sensor alertes batteries expose la liste des entity_id en alerte. Les cartes Lovelace les affichent en tooltip au survol

### Corrigé

- **Création de blueprint : corruption des inputs JSON** — les agents IA envoyaient les inputs sous forme de JSON string imbriqué. Le parser détecte et déplie maintenant ce pattern, produisant des champs `name` + `selector` propres
- **Blueprint : texte français hardcodé** — commentaire d'en-tête, description par défaut et messages de succès passés en anglais
- **`strings.json` manquait 9 des 14 sensors** — HA utilise `strings.json` comme référence pour la résolution des `translation_key`. Les 14 sensors sont maintenant présents
- **Chaînes françaises en runtime** — 9 chaînes françaises remplacées par l'anglais dans `mcp_server.py`, `websocket.py`, `proactive_agent.py`
- **Outils Lovelace refactorisés** — les 5 outils utilisent un helper partagé `_get_lovelace_dashboard()` compatible avec toutes les versions de HA
- **`ha_add_lovelace_card` plus intelligent** — détection automatique de `view_index=0`, détection automatique d'entité pour les types `weather-forecast`, `thermostat`, etc.
- **Faux positifs entités zombies** — validation du format entity_id. Les device_id (hash hex) et automation_id sont rejetés
- **Faux positifs doublons blueprint** — les automatisations utilisant `use_blueprint` sont exclues de la détection de doublons
- **Carte HACA Score : sélecteur d'entité** — éditeur custom qui filtre `battery_alerts`. Jauge pour health_score, nombre brut pour les autres
- **Carte Score : `e()` avant initialisation** — fonction d'échappement déplacée en début de `_update()`
- **Intervalle de scan 0** — `|| 60` traitait 0 comme falsy. Corrigé avec `!= null`
- **Panel MCP : fallbacks hardcodés** — tous les `_t('mcp.*', 'texte')` remplacés par `_t('mcp.*')`
- **Panel MCP : traductions dans `panel.mcp`** — clés déplacées de la racine JSON vers `panel.mcp`
- **MCP auth 401** — passage à `requires_auth = True` (middleware standard HA)
- **Détection batterie stricte** — seul `device_class: "battery"` accepté
- **Icône menu invisible** — path SVG `menu` ajouté au dictionnaire `_MDI`
- **Section token supprimée** — `mcp_ha_token` supprimé (inutilisé)

### Modifié

- **Version** : 1.6.1 → 1.6.2
- **Badge version MCP** : v1.6.2
- **Configs agents MCP** : Claude Code en HTTP direct, Claude Desktop via `uvx mcp-proxy`, Antigravity via `mcp-proxy -H`

---

## [1.6.1] — 2026-03-20 — Corrections de bugs, nouvelles fonctionnalités, améliorations UX

### Ajouté

- **Checks LOW désactivés par défaut** (#10) — Les nouvelles installations excluent 14 types d'issues de faible sévérité (no_description, no_alias, helper_unused, etc.) pour éviter de submerger les nouveaux utilisateurs avec 1400+ notifications
- **Mode scan manuel uniquement** (#19) — Mettre scan_interval à 0 désactive le scan automatique. HACA ne scanne que lorsque l'utilisateur clique "Scan complet"
- **Toggle notifications batterie** (#11) — Nouveau toggle dans la Configuration pour désactiver les notifications persistantes de batterie tout en gardant la liste dans le dashboard
- **Panel admin uniquement** (#6.2) — Le panel HACA dans la sidebar est masqué pour les utilisateurs non-admin via `require_admin=True`
- **Bouton menu mobile** (#6.3) — Icône menu hamburger dans le header sur mobile/tablette qui ouvre la sidebar HA (dispatche `hass-toggle-menu`), comme toutes les intégrations HA
- **Explications des types d'issues** (#13) — 33 explications courtes affichées sous chaque issue expliquant ce qui a été détecté et pourquoi. Traduites en anglais et français
- **Timestamp du dernier scan** — Affiché dans le header du panel HACA à côté du bouton Scan avec le label "Dernier scan" (traduit en 13 langues), date et heure avec année
- **Config : catégories scripts, scènes, helpers, groupes** — Les toggles de types d'issues couvrent maintenant les 74 types d'analyseurs dans 11 catégories

### Corrigé

- **`excluded_issue_types` ne fonctionnait pas** (#12, #18, #6) — Cause racine : 29 types d'analyseurs manquaient dans la liste de toggles du panel de config. Resynchronisation complète des 74 types dans 11 catégories
- **Label `haca_ignore` ignoré par les analyseurs performance et sécurité** (#3) — Les deux analyseurs chargent et filtrent maintenant par labels `haca_ignore`
- **Repairs non nettoyées après correction des issues** (#16) — Réécriture de `repairs.py` : supprime TOUTES les anciennes repairs HACA avant de recréer les actuelles
- **Messages Repairs trop vagues** (#9) — Type affiché en texte lisible. Recommandation incluse. Seuls les fixes simples sont marqués auto-fixables
- **Scripts supprimés toujours signalés** (#17) — `.clear()` ajouté avant le rechargement des fichiers YAML
- **"IA" codé en dur au lieu de "AI"** (#4) — Remplacé par la clé de traduction `actions.ai_explain`
- **Vérification labels inutilisés trop restrictive** (#7) — Vérifie maintenant entités, appareils, zones et automations/scripts
- **Boutons copier ne fonctionnaient pas** — Remplacement de `navigator.clipboard` par un fallback compatible HTTP
- **Création de blueprint bloquée par le backup** — L'IA n'appelle plus `ha_backup_create` séparément. Le backup est géré en interne
- **Format `inputs` du blueprint rejeté** — Parsing robuste : accepte dict, JSON string, ou valeurs simples
- **Carte Score affichait "0/100"** — Changé en "%"
- **Carte Score batterie affichait "0%"** — Affiche ✓ avec icône batterie verte quand battery_alerts = 0
- **Carte Dashboard batterie "0"** — Affiche ✓ au lieu de "0"

### Modifié

- **Config MCP Antigravity** — Utilise le pont `mcp-proxy` (HACA ne supporte pas OAuth2 dynamic client registration)
- **Alias MCP `/api/haca_mcp/sse`** — Conservé mais tous les exemples utilisent l'URL de base

---

## [1.6.1] — 2026-03-20 — Corrections issues tracker, nouvelles options de config, UX mobile et améliorations MCP

### Ajouté

- **Checks LOW désactivés par défaut** (#10) — les nouvelles installations excluent 14 types d'issues de faible sévérité pour éviter de submerger les utilisateurs avec 1400+ notifications
- **Mode scan manuel uniquement** (#19) — intervalle de scan à 0 dans la Configuration pour désactiver les scans automatiques ; seul le bouton "Scan complet" déclenche l'analyse
- **Toggle notifications batterie** (#11) — nouveau toggle dans la Configuration pour désactiver les notifications persistantes tout en gardant la liste dans le dashboard
- **Explications par type d'issue** (#13) — 33 explications courtes affichées sous chaque carte d'issue. Traduites en 13 langues
- **Panel admin uniquement** (#6.2) — `require_admin=True` ; les utilisateurs non-admin ne voient plus HACA dans la barre latérale
- **Bouton menu mobile** (#6.3) — icône hamburger dans le header qui ouvre la barre latérale HA sur mobile/tablette
- **Timestamp dernier scan** — "Dernier scan : JJ/MM/AAAA HH:MM" dans le header à côté du bouton Scan, traduit en 13 langues
- **Route alias MCP `/sse`** — `/api/haca_mcp/sse` accepté comme URL alternative pour les clients MCP basés sur SSE

### Corrigé

- **`excluded_issue_types` désynchronisé** (#12/#18/#6) — le panel config listait 55 types mais les analyseurs en produisent 74. Ajout de 4 nouvelles catégories (Scripts, Scènes, Helpers, Groupes) avec 31 types manquants
- **`haca_ignore` non respecté** (#3) — `performance_analyzer.py` et `security_analyzer.py` n'avaient aucun filtre
- **Repairs non nettoyées** (#9/#16) — réécriture de `repairs.py` : remise à zéro à chaque scan, noms de types lisibles, recommandations
- **Scripts supprimés toujours signalés** (#17) — les dicts de configs n'étaient pas vidés avant rechargement
- **"IA" hardcodé au lieu de "AI"** (#4) — remplacé par la clé de traduction `actions.ai_explain`
- **Faux positifs label inutilisé** (#7) — vérification étendue aux devices, areas et automations
- **Régression création de blueprint** — l'IA appelait un backup séparé et se bloquait. Backup maintenant interne, parsing des inputs robuste
- **Boutons copier MCP** — fallback pour HTTP, event listeners au lieu de onclick inline
- **Carte score batterie 0/100** — affiche ✓ vert au lieu de 0%
- **Carte dashboard /100** — jauge affiche % au lieu de /100

### Modifié

- **Configs agents MCP** — URL de base `/api/haca_mcp` pour tous. Antigravity utilise `mcp-proxy` (OAuth2 non supporté)
- **Valeurs par défaut config_flow** — `excluded_issue_types`, `repairs_enabled`, `battery_notifications_enabled` définis à l'installation

---

## [1.6.0] — 2026-03-16 — Cartes Lovelace, audit approfondi, slugs Unicode et compatibilité HA 2026.x

### Ajouté

- **Carte Lovelace Dashboard** (`haca-dashboard-card`) — carte personnalisée avec jauge de score de santé, grille de compteurs d'issues, bouton de scan et lien vers le panel. Configuration visuelle via `getConfigForm()` avec les sélecteurs natifs HA (titre, toggles, nombre de colonnes, sélecteur d'entités filtré par intégration). Un clic ouvre le dialogue more-info standard de HA (historique, engrenage, menu 3 points)
- **Carte Lovelace Score** (`haca-score-card`) — jauge de score de santé compacte avec pastilles optionnelles de compteurs d'issues. Découverte automatique de l'entité score via l'attribut `haca_type`. Éditeur visuel avec sélecteur d'entité et toggle de détails
- **Enregistrement automatique des ressources Lovelace** — les cartes sont auto-enregistrées comme ressources du dashboard au setup de l'intégration via `async_setup` suivant le pattern officiel HA (dépendances manifest, `lovelace.resources.async_create_item`, retry sur `resources.loaded`). Les anciennes ressources obsolètes sont automatiquement nettoyées
- **Attribut d'état `haca_type`** — les 14 capteurs HACA exposent `haca_type` (ex: `"health_score"`, `"automation_issues"`) dans `extra_state_attributes` pour la découverte d'entités indépendante de la langue par les cartes frontend
- **`suggested_object_id`** — les capteurs suggèrent des identifiants en anglais quel que soit la langue du backend HA, produisant des entity_id stables comme `sensor.h_a_c_a_health_score` au lieu de variantes localisées
- **Helper `_slugify()`** — générateur de slug centralisé avec support Unicode via `unicodedata.normalize('NFKD')`. Gère tous les diacritiques (é→e, ç→c, ñ→n, ü→u). Appliqué sur 9 emplacements : blueprints (3), area_id, script_id, helper_id, entity_id dans create_automation, entity_id dans deep_search, création de scènes
- **`_issue_stable_id()`** — génère des identifiants d'issues déterministes (`entity_id|type`) pour les outils MCP car les analyseurs ne produisent pas de champ `id`
- **Stratégie de fusion `_TS_CACHE`** — le cache de traductions stocke maintenant le JSON racine + panel fusionné, rendant `ai_prompts` (30 clés), `services_notif` et `notifications` racine accessibles aux côtés des sections panel

### Corrigé

- **Champ `fixable` des outils MCP** — les outils lisent maintenant `fix_available` et `recommendation` (les vrais noms de champs des analyseurs) au lieu de `fixable` et `fix_description` inexistants. Corrige `haca_fix_suggestion`, `haca_apply_fix` et `haca_get_issues`
- **`_find_issue_by_id` cassé** — cherchait `issue.get("id")` mais aucun analyseur ne produit de champ `id`. Cherche maintenant par ID stable, entity_id ou alias
- **`_tool_get_score` incomplet** — ne comptait que 5 des 10 catégories dans `by_severity`. Compte maintenant les 10 (automation, script, scene, blueprint, entity, helper, performance, security, dashboard, compliance). Suppression du champ fantôme `last_scan`
- **13 I/O bloquants dans `mcp_server.py`** — tous les `.read_text()`, `.exists()`, `open()`, `os.remove()`, `os.makedirs()` dans des fonctions async encapsulés dans `async_add_executor_job`
- **`_TS_CACHE` ne stockait que le sous-arbre `panel`** — les notifications de `services.py`, les prompts IA de `conversation.py` (30 clés), le prompt système de `automation_optimizer.py` et le message de désinstallation de `__init__.py` retournaient tous les clés brutes au lieu du texte traduit
- **`extra_state_attributes` écrasait `super()`** — `HACAHealthScoreSensor`, `HACABatteryAlertsSensor` et `HACARecorderOrphansSensor` perdaient l'attribut `haca_type` de la classe de base. Les trois appellent maintenant `super().extra_state_attributes`
- **Slug de blueprint `allumer_une_lumi_re`** — `re.sub(r"[^a-z0-9_]", "_", ...)` transformait les accents en underscores. Corrigé par `_slugify()` avec normalisation NFKD : `"Allumer une lumière avec un capteur de présence"` → `"allumer_une_lumiere_avec_un_capteur_de_presence"`
- **Remplacement manuel des accents** — la génération de area_id utilisait une chaîne de 8 `.replace("é","e")`. Remplacé par `_slugify()` pour une couverture Unicode complète
- **Crash `Path.mkdir(True)`** — `exist_ok` est keyword-only dans `Path.mkdir()`. Passer `True` en positionnel définissait `mode=1`. Corrigé avec lambda
- **`LovelaceData.mode` supprimé dans HA 2026.x** — remplacé par `resource_mode`. Le code utilise maintenant `getattr` avec fallback pour la compatibilité
- **Cache des ressources de cartes** — les URLs utilisaient une version statique `?v=1.5.2` qui ne changeait jamais entre les rebuilds JS. Utilise maintenant le hash de build (`?v=70c62e88`) garantissant le rechargement du navigateur à chaque modification
- **Crash `customElements.define`** — le registre scopé de HA 2026.x lance une exception en cas de double enregistrement. Les deux cartes sont protégées par `if (!customElements.get(...))`
- **`ha-card` détruit à chaque rendu** — `this.innerHTML = '<ha-card>...'` dans `set hass()` remplaçait l'élément `ha-card` auquel HA avait attaché son overlay d'édition. Suit maintenant le pattern officiel HA : `ha-card` créé une seule fois dans `if (!this.content)`, seul le contenu du `div` intérieur est mis à jour
- **`setConfig` détruisait le DOM** — remettait `_cardBuilt = false` causant la recréation de `ha-card`. `setConfig` stocke maintenant la config uniquement, ne touche jamais le DOM

### Modifié

- **`manifest.json`** — `dependencies` inclut maintenant `["frontend", "http"]` (requis pour l'enregistrement des ressources Lovelace)
- **Enregistrement des cartes dans `async_setup`** — déplacé de `async_setup_entry` vers `async_setup` selon le guide officiel du développeur HA (s'exécute une fois par domaine, pas par config entry). Utilise la vérification `CoreState.running` avec fallback sur l'événement `homeassistant_started`

### Supprimé

- **Éditeurs de cartes custom** — les éléments `HacaDashboardCardEditor` et `HacaScoreCardEditor` supprimés au profit de `getConfigForm()` avec les sélecteurs natifs HA

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
