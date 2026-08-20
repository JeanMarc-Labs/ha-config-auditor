# Changelog — H.A.C.A

Toutes les modifications notables de ce projet sont documentées ici.

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/)
Versionnement : [Semantic Versioning](https://semver.org/lang/fr/)
---
## [1.7.6] — 2026-08-11 — Titres des Repairs, interrupteur entités bruyantes, correctif sélection des orphelins Recorder

### Ajouté

- **La détection des entités bruyantes peut désormais être désactivée** — Nouvel interrupteur « Entité bruyante » dans Configuration → Performance, à côté des autres types d'issues. Il ne se contente pas de masquer les issues : la requête d'agrégation Recorder qui les produit est entièrement sautée, et l'écouteur `EVENT_STATE_CHANGED` en mémoire qui la complète (`noisy_tracker.py`, un callback par changement d'état de toute l'instance) est arrêté. L'interrupteur s'applique immédiatement, sans redémarrer Home Assistant. La liste d'exclusion par motifs glob ajoutée en 1.7.5 reste disponible pour qui ne veut faire taire qu'une partie de ses entités.

### Corrigé

- **Les entrées Repairs affichaient « config_auditor: generic_high_issue » sans description** — La traduction `generic_high_issue` se trouvait sous `panel.issues.*` dans les 13 fichiers `translations/<lang>.json`. Ce sous-arbre n'est transmis qu'au JavaScript du panel ; le framework Repairs lit `issues.<clé>` à la **racine** du fichier de langue, ne la trouvait donc jamais et retombait sur son affichage de repli `<domaine> : <clé_de_traduction>`. `strings.json` la portait bien à la racine — mais Home Assistant ne charge pas `strings.json` pour une intégration personnalisée, uniquement `translations/<lang>.json`. La section est maintenant à la racine de chaque fichier de langue, et les huit langues qui portaient encore la phrase en anglais ont été traduites au passage.
- **Le bouton « Réparer » des Repairs HACA n'ouvrait rien** — Quatre types d'issues (`no_description`, `no_alias`, `compliance_automation_no_description`, `compliance_script_no_description`) étaient poussés avec `is_fixable=True`, alors que la plateforme repairs n'expose plus `async_create_fix_flow` — retiré avec l'ancien `HacaFixFlow` (voir `tests/test_repairs.py`, désactivé), Home Assistant n'avait donc aucun handler de flow à charger et la boîte de dialogue échouait. Tous les repairs sont désormais créés avec `is_fixable=False` ; la description renvoie vers le panneau HACA, où se trouvent réellement les correctifs.
- **Orphelins Recorder : chaque scan automatique re-sélectionnait toute la liste** — Les cases étaient générées `checked` par défaut et le tableau est redessiné à chaque résultat de scan : un scan de fond arrivant en pleine sélection recochait silencieusement toutes les lignes, et « Purger la sélection » pouvait viser des entités jamais choisies. Plus rien n'est pré-coché.
- **MCP : `ha_call_service` n'a jamais appelé le moindre service** — Chaque appel passait `limit=10` à `hass.services.async_call()`. Ce paramètre a été retiré de `ServiceRegistry.async_call` en HA 2023.7 : sur toutes les versions de Home Assistant supportées (l'intégration exige 2024.1+), l'appel levait donc `TypeError: async_call() got an unexpected keyword argument 'limit'`, que le `except Exception` environnant transformait en `{"error": "Service call failed: …"}` — l'outil semblait échouer sur le service visé, jamais sur sa propre signature d'appel. La valeur était un copier-coller de la variable `limit` de l'outil de listage d'entités situé juste au-dessus.
- **MCP : `ha_check_config` n'a jamais lancé de vérification** — L'outil appelait `homeassistant.check_config` avec `return_response=True`, alors que ce service est enregistré via `async_register_admin_service` sans `supports_response` : `ServiceRegistry.async_call` lève `ServiceValidationError` (`service_does_not_support_response`) avant même d'atteindre le handler. Le `except` générique l'absorbait en `{"error": "Config check failed: …"}`, ce qui rendait le repli écrit juste en dessous — un appel direct à `homeassistant.helpers.check_config.async_check_ha_config_file`, la fonction même qui alimente le bouton « Vérifier la configuration » de HA — inatteignable, du code mort. Le chemin par le service est supprimé, l'appel direct au helper devient l'unique chemin.
- **MCP : `ha_backup_create` annonçait un succès avant même le début de la sauvegarde** — La branche BackupManager (HA 2025.1+) planifiait `manager.async_create_backup(...)` via `hass.async_create_task()` puis renvoyait `{"success": true}` immédiatement, sans jamais attendre la coroutine ni poser de callback de fin. Toute défaillance (aucun agent de sauvegarde encore enregistré, disque plein, combinaison `include_*` refusée par le manager) n'apparaissait au mieux que sous forme de trace de tâche non récupérée dans le log, et l'appelant MCP — à qui l'on venait d'annoncer la réussite — ne pouvait jamais l'apprendre. Les sauvegardes restent volontairement en arrière-plan (les attendre ferait expirer le client MCP sur une sauvegarde qui se déroule pourtant normalement), mais l'outil échoue désormais immédiatement si aucun agent de sauvegarde n'est enregistré (en enchaînant sur la stratégie de sauvegarde suivante au lieu de perdre l'erreur), pose un callback de fin qui journalise le résultat sous `[HACA]`, et renvoie `started: true, completed: false` au lieu de `success: true`. La description de l'outil demande maintenant à l'assistant de renvoyer l'utilisateur vers Paramètres → Système → Sauvegardes plutôt que d'annoncer une sauvegarde terminée. La branche par le service `backup.create`, qui présentait la même incohérence `blocking=False` + `success: true`, a été alignée.
- **MCP : les outils Lovelace annonçaient un dashboard vide au lieu d'un dashboard à stratégie** — Un dashboard rendu par une stratégie (`original-states`, `areas`, stratégies personnalisées) ne stocke aucune clé `views` : `ha_get_lovelace` répondait donc `views_count: 0` avec une liste de vues vide, et `ha_add_lovelace_card` « aucune vue, créez-en une dans l'interface HA » — littéralement vrai, mais trompeur : rien n'est stocké parce que les vues sont générées au moment du rendu. Les quatre outils Lovelace partagent désormais un garde-fou qui nomme la stratégie en cause et renvoie vers « Prendre le contrôle ». Aucun risque d'écrasement n'existait pour les dashboards stockés. Leurs messages d'erreur génériques portent maintenant aussi le `dashboard_id`.

### Modifié

- **La sélection des orphelins est désormais persistante** — Elle survit aux scans, à la pagination et au changement de tri. La case d'en-tête reflète la page courante (état indéterminé si partielle), un compteur `{n} sélectionnée(s)` indique la sélection globale, et « Purger la sélection » agit sur cette sélection globale et non plus seulement sur la page visible.

### Note

- **Le texte plus gris depuis la 1.7.5 est normal.** `_syncTheme()` propage maintenant les variables de thème inline de `<html>` dans l'iframe du panel : HACA suit enfin les thèmes personnalisés comme une carte native. Avant, ces variables n'atteignaient jamais l'iframe et le panel retombait sur un quasi-noir codé en dur. Ajustez `primary-text-color` / `secondary-text-color` dans votre thème pour un rendu plus foncé.

---
## [1.7.5] — 2026-08-05 — Patterns d'exclusion scan noisy, thème sombre, faux positif sécurité, fix optimizer

### Ajouté

- **Scan entités bruyantes : exclusions par pattern** — Nouvelle section Configuration « Exclure du scan Entités bruyantes ». Accepte un glob par ligne (`sensor.browser_mod_*`, `device_tracker.*`, `*_motion`). Les entités exclues conservent leur historique Recorder complet (contrairement à l'exclusion Recorder). Champ `Tester` live pour vérifier un `entity_id` contre les patterns courants. Le label `haca_ignore` est désormais respecté par le scan noisy également.
- **Bouton « Ignorer (bruit) » par issue** — Bouton orange sur chaque carte d'issue `noisy_entity` (à côté d'« Exclure du Recorder »). Un clic ajoute l'`entity_id` littéral à la liste d'exclusion du scan noisy et fait fader la carte. Dédup : si un pattern existant (littéral ou glob) couvre déjà l'entité, le bouton no-op et le toast indique quel pattern matche. Le textarea reste pour les utilisateurs avancés qui ajoutent des familles de globs en masse.
- **Support du thème sombre** — HACA suit désormais automatiquement le thème de Home Assistant. Priorité de détection : `hass.themes.darkMode` quand c'est un booléen explicite, sinon la luminance perçue de `--primary-background-color` (que `_syncTheme()` propage déjà du document parent vers l'iframe — fonctionne même quand HA ne peuple pas le sous-objet `hass.themes` dans l'iframe), sinon `prefers-color-scheme: dark` de l'OS. Quand le résultat est sombre, le panel pose un attribut `data-haca-dark` sur son hôte et applique un calque CSS dédié : les cartes d'issues avec teinte de sévérité redeviennent lisibles sur fond sombre (opacité passée de `0.02` à `0.10`), les teintes `rgba(0,0,0,X)` (hover, désactivés, blocs `<code>`) basculent en `rgba(255,255,255,X)`, et les puces success/error échangent leur texte foncé sur fond clair (`#15803d`, `#dc2626`, `#e65100`) contre des équivalents clairs sur fond sombre (`#4ade80`, `#f87171`, `#ffb74d`). Détection réactive — basculer le thème HA en runtime fait pivoter le panel sans recharger. Les contours des nœuds du graphe de dépendances (dessinés par D3) prennent eux aussi la teinte adaptée au moment du rendu.

### Modifié

- **Cache-bust frontend désormais via nom de fichier hashé, plus via query string.** Plusieurs utilisateurs en 1.7.5 ont signalé voir le nouveau header `v1.7.5` (les traductions sont chargées via WebSocket à chaque visite) mais pas la nouvelle section « Hide entities from the Noisy Entity scan » (le bundle JS était servi depuis le cache). Le bust par query string (`haca-panel.js?v=<hash>`) était ignoré par le service worker du frontend HA chez ces utilisateurs. Le script de build émet désormais `haca-panel.<hash>.js` en plus de `haca-panel.js`, et `custom_panel.py` enregistre l'URL hashée — l'URL elle-même change à chaque rebuild, donc ni le cache navigateur ni le service worker ne peuvent servir une copie périmée. Les anciens `haca-panel.<oldhash>.js` sont automatiquement nettoyés à chaque rebuild.

### Corrigé

- **Critique : la purge des orphelins DB verrouillait la base du recorder jusqu'au redémarrage de Home Assistant** — `haca/purge_recorder_orphans` empilait tous les `DELETE` de toutes les entités sélectionnées et n'appelait `commit()` qu'à la toute fin. Sur SQLite, la première instruction prend le verrou d'écriture et le garde pendant toute l'exécution — et cette exécution n'était bornée par rien : deux des requêtes balayent `states` en entier, l'`UPDATE … SET old_state_id = NULL` (sa sous-requête en table dérivée empêche SQLite d'utiliser `ix_states_old_state_id`) et le `NOT EXISTS` corrélé qui cherchait les `state_attributes` non partagés. Sur une base de plusieurs Go, cela représente des minutes à des heures *par entité*, pendant lesquelles le recorder ne pouvait plus committer : `Error in database connectivity during commit: … database is locked [SQL: UPDATE states SET last_reported_ts=?]`. Sans timeout ni point d'annulation, seul un redémarrage complet de HA libérait la base. Le handler est désormais scindé en deux : `states` / `state_attributes` sont purgés par le service natif `recorder.purge_entities` — traité par lots, exécuté dans le thread du recorder, et déjà conscient des clés étrangères que HA active sur SQLite via `PRAGMA foreign_keys=ON` — et seuls `statistics` / `statistics_short_term` / `statistics_meta`, que ce service ne couvre pas, restent en SQL direct, désormais supprimés par pages de 1000 clés primaires avec un commit après chaque page. Le verrou d'écriture n'est jamais tenu plus de quelques millisecondes. Le `PRAGMA wal_checkpoint(TRUNCATE)` final, qui attend que tous les lecteurs aient terminé et pouvait bloquer à lui seul, est passé en `PASSIVE`. Si le recorder n'a pas fini d'écouler les lignes d'états au bout de 15 minutes, l'appel renvoie un résultat partiel accompagné d'une liste `pending` au lieu de bloquer — la purge se termine ensuite toute seule en arrière-plan, toujours sans rien verrouiller.
- **Les scans recorder et entités bavardes prenaient un verrou d'écriture pour lire** — `RecorderAnalyzer._query_orphans()` et le scan noisy de `PerformanceAnalyzer` émettaient tous deux un `BEGIN IMMEDIATE` avant des agrégats en lecture seule qui balayent `states` en entier. `IMMEDIATE` acquiert immédiatement un verrou `RESERVED` (écriture), donc chaque scan planifié bloquait le recorder pendant toute sa durée — le même mode de défaillance que la purge, simplement plus court. Les deux annulent maintenant la transaction inactive éventuellement héritée du pool et laissent le premier `SELECT` ouvrir une transaction de lecture normale, qui sous WAL voit déjà le dernier commit. C'était l'objectif réel du `BEGIN IMMEDIATE` d'origine.
- **Bouton « Corriger » sur les issues `device_id_in_*` échouait avec `extra keys not allowed @ data['location']`** — Régression latente introduite en 1.7.3 quand le frontend a commencé à envoyer `location` pour cibler une seule action (« Le bouton Fix cible une seule action via `location` »). Les schémas des services `preview_device_id` et `fix_device_id` n'ont jamais été mis à jour pour accepter cette nouvelle clé, donc voluptuous rejetait tous les appels. Les deux schémas déclarent maintenant `vol.Optional("location"): vol.Any(cv.string, None)`, et `apply_device_id_fix()` accepte et propage `location` à son appel preview interne — sans ça, l'apply re-prévisualisait l'automatisation complète et corrigeait toutes les références `device_id` au lieu de juste celle que l'utilisateur avait vue dans la prévisualisation. `services.yaml` documente le nouveau champ pour l'UI Outils Développeur.
- **Faux positif `sensitive_data_exposure` sur les identifiants snake_case** — La regex de détection flaggait toute chaîne alphanumérique de 16+ caractères, attrapant les constantes du protocole Mobile App telles que `clear_notification` (utilisé pour dismiss les notifications par tag). Resserrée : le snake_case pur (sans majuscule) est exclu, plus une allowlist des constantes Mobile App connues. La même heuristique est désormais partagée par les scans hardcoded-secret et notification-exposure.
- **`AutomationOptimizer.optimize` crashait avec `AttributeError: '_build_content'`** — `_build_prompt` référençait une méthode jamais définie et une variable hors-scope, donc tous les appels « Optimiser cette automation » échouaient. Le contenu du prompt est désormais construit en inline depuis les variables locales déjà calculées.
- **Serveur MCP : `tools/call` échouait avec `Object of type datetime is not JSON serializable`** — Remonté depuis les logs sous la forme `[HACA MCP] Handler error for method 'tools/call'`. Le handler MCP sérialisait chaque résultat d'outil avec un `json.dumps(result, …)` nu, alors que les résultats transportent des données Home Assistant brutes — `dict(state.attributes)` dans `ha_get_entity_detail`, les entrées logbook de `ha_get_logbook`, les métadonnées de backup, les entrées de registre — et les intégrations sont libres d'y stocker des `datetime`, `date`, `timedelta`, `Enum` ou `set` (un attribut `next_collection` façon `garbage_collection` suffit). Une seule valeur de ce type levait un `TypeError` dans `json.dumps`, le `except` générique le transformait en JSON-RPC `-32603 Internal error`, et l'appel d'outil échouait alors que le handler lui-même avait réussi. Un encodeur de repli `_json_default()` convertit désormais datetimes/dates/heures en ISO 8601, `timedelta` en secondes, `Decimal` en float, `set`/`frozenset` en listes triées, `Enum` en sa valeur, `Path`/`bytes` en chaînes, les objets HA exposant `as_dict()` en dicts, et tout le reste en `str()` — il ne peut jamais lever d'exception. Il est appliqué au payload `tools/call` ainsi qu'aux deux encodeurs de réponse HTTP (simple et batch). La même normalisation est appliquée sur le chemin LLM-API (`HacaTool.async_call`), où l'agent conversationnel en aval sérialise le résultat sans `default=` de son côté.
- **Le scan « Entités bruyantes » ignorait `recorder.exclude.entity_globs` et `recorder.exclude.domains`** dans `configuration.yaml`. Les utilisateurs ayant des patterns comme `camera.*`, `light.browser_mod_*` ou `sensor.*_recent_table` dans leurs exclusions recorder voyaient quand même toutes les entités correspondantes flaggées comme bruyantes. HACA ne lisait que la liste littérale `recorder.exclude.entities` et perdait silencieusement le reste du bloc exclude. Le lecteur YAML (`_read_recorder_excludes_sync`) retourne désormais `(entities, entity_globs, domains, authoritative)` ; le scan noisy vérifie les trois avec la sémantique `fnmatch` native de HA avant de flagger une entité. Le comportement est désormais consistent avec ce que fait le filtre recorder HA lui-même au runtime. La ligne de log visible à chaque scan a aussi été étendue — chercher `[HACA] recorder excludes from configuration.yaml: entities=… globs=… domains=…` pour debugger ce que voit HACA.

---
## [1.7.4] — 2026-05-12 — Fusion de la bibliothèque batteries, nettoyage du scan dashboards

### Ajouté

- **Bibliothèque de piles embarquée étendue à ~2140 appareils** — Source unique, plus besoin d'intégration externe.

### Modifié

- **Analyseur de dashboards** : ne scanne plus que les fichiers `.storage/lovelace.<id>` enregistrés dans `.storage/lovelace_dashboards`. Les fichiers orphelins / backups sont ignorés — élimine les faux positifs « entité manquante » qui inondaient le panneau HA Repairs.

### Supprimé

- **Support runtime Battery Notes** — scan `sensor.*_battery_plus`, bannière d'installation, `battery_notes_tooltip` et clés de traduction associées. Le stockage `battery_last_replaced` natif HACA et la bibliothèque embarquée prennent entièrement le relais.

### Corrigé

- **Critique : des clics concurrents sur « Exclure du Recorder » pouvaient vider `configuration.yaml`** et ne laisser qu'une section `recorder:` nue. Trois défenses ajoutées : un `asyncio.Lock` qui sérialise toute la séquence édition/validation, refus d'écrire si le YAML se charge à vide, et écriture atomique via `os.replace` pour qu'aucun lecteur ne voie un fichier tronqué.

---
## [1.7.3] — 2026-05-11 — Exclusion Recorder, bibliothèque batteries, passe de traductions complète

### Ajouté

- **Exclure du Recorder** — bouton vert sur chaque issue `noisy_entity` qui écrit l'entité dans `recorder.exclude.entities` de `configuration.yaml` (sauvegarde horodatée, commentaires préservés via ruamel.yaml, validation par `homeassistant.check_config`, rollback automatique en cas d'échec)
- **Bibliothèque de piles autonome** — fichier seed embarqué (~50 marques), enrichissement Battery Notes optionnel, éditeur de bibliothèque intégré, colonne fabricant/modèle, bouton « Marquer remplacée » par ligne
- **Traceur d'entités bruyantes en direct** — compteur de changements d'état en mémoire qui complète la base Recorder : une entité retirée de `configuration.yaml` réapparaît au scan suivant, sans redémarrer Home Assistant
- **Orphelins DB triables + badge d'onglet** — tri par taille ou par nom ; l'icône de l'onglet Database affiche un badge rouge avec le décompte

### Modifié

- **`configuration.yaml` devient la source autoritaire pour les exclusions Recorder** — lu à chaque scan avec PyYAML compatible avec les tags HA ; prime sur le filtre Recorder figé au démarrage
- **Traductions** — passe complète sur les 13 langues : panneau, onglet Configuration HACA, filtres et badges de sévérité, types/hints/catégories d'issues, catégories d'outils MCP, sections du rapport PDF, notification de fin de rapport, rapport hebdomadaire, panneaux Conformité et Prédiction de batteries (~700 entrées)
- **`haca_id`** : hash stable sur `entity_id | type | location` pour adresser chaque issue de façon unique

### Supprimé

- **Fonction Ignorer par issue** — remplacée par Exclure du Recorder (limité aux issues `noisy_entity`)

### Corrigé

- Issue exclue ne réapparaissant pas après suppression manuelle dans `configuration.yaml`
- Badges de sévérité (`HIGH/MEDIUM/LOW`) en anglais et titres de catégories MCP en français codés en dur dans la carte de référence AI fix
- Plusieurs chaînes de stat cards et de notifications encore en anglais en danois / suédois / allemand
- Les corrections `device_id` préservent `continue_on_error` / `enabled` / `alias` et fusionnent les champs supplémentaires (`preset_mode`, `brightness`) dans `data`
- Le bouton Fix cible une seule action via `location`, plus toute l'automatisation
- Texte de conseil de réparation dupliqué supprimé ; le changement d'onglet auto-scrolle sur petits écrans

---

## [1.7.2] — 2026-04-26 — Corrections mineures

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
