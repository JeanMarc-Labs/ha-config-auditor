# Journal des modifications (Changelog)

Tous les changements notables apportés à ce projet seront documentés dans ce fichier.

## [1.1.1] - 2026-02-19

### Ajouté
- **Panneau Frontend** : Ajout d'un bouton "Éditer" sur chaque issue qui ouvre l'éditeur natif de Home Assistant directement (automations, scripts, scènes). Cela permet aux utilisateurs de modifier manuellement les éléments sans passer par les propositions de l'IA.
- **Traductions (FR/EN)** : Ajout de la clé `edit_ha` pour le nouveau bouton Éditer.

## [1.1.0] - 2026-02-19

### Corrections
- **Analyseur d'Automations** : Correction des faux positifs sur la détection `template_simple_state` — vérifie désormais correctement `has_complex_logic`, `has_other_functions` et `has_jinja_filter` avant de signaler un problème.
- **Analyseur de Performance** : Ajout de la détection des templates Jinja2 coûteux (`states | selectattr` sans filtre de domaine, `states | list` / `states | count` itérant tous les états). Correction des imports manquants (`asyncio`, `re`).
- **Analyseur d'Entités** : Correction de la détection des entités zombies — les scripts sont désormais scannés en plus des automations. Ajout du paramètre optionnel `script_configs` dans `analyze_all()` et `_build_entity_references()`.
- **`__init__.py`** : Correction du câblage — `script_configs` de `automation_analyzer` est désormais correctement transmis à `entity_analyzer` dans tous les chemins de scan (`async_update_data`, `handle_scan_entities`, `_run_scan`).

### Ajouté
- **Traductions (FR/EN)** : Ajout de 4 nouvelles clés pour les issues de templates coûteux : `expensive_template_no_domain`, `add_domain_filter`, `expensive_template_states_all`, `filter_by_domain`.
- **Panneau Frontend** : Affichage de la version `V1.1.0` dans l'en-tête du panneau.
- **Panneau Frontend** : Protection XSS via `escapeHtml()` sur toutes les données utilisateur injectées dans le DOM (`alias`, `entity_id`, `message`, `recommendation`, noms des sauvegardes).
- **Panneau Frontend** : Ajout d'un pattern debounce sur les boutons de scan (`scanAll`, `scanAutomations`, `scanEntities`) pour éviter les doubles-clics. Les boutons se réactivent 3 secondes après la résolution de l'appel service (et non dans un bloc `finally`).

## [1.0.0] - 2026-02-15

### Ajouté
- **Version Initiale**
- **Analyseurs de Base**: Automations, Entités, Performance et Sécurité.
- **IA Assistante**: Explications intégrées via l'agent de conversation HA.
- **Assistant de Refactoring**: Interface native pour corriger les `device_id` et les templates.
- **Interface Bilingue**: Support de l'anglais et du français.
- **Multitâche Coopératif**: Optimisation de la logique de scan pour éviter les déconnexions WebSocket.
