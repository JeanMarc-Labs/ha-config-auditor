# H.A.C.A - System Patterns

## Architecture Générale

```
ha-config-auditor/
├── custom_components/config_auditor/
│   ├── __init__.py              # Point d'entrée principal, services, orchestration
│   ├── const.py                 # Constantes globales
│   ├── config_flow.py           # Configuration UI (ConfigEntry)
│   ├── sensor.py                # Entités capteur HA (Health Score, issues counts...)
│   ├── manifest.json            # Métadonnées HACS/HA
│   │
│   ├── automation_analyzer.py   # Module 1 : Analyse automations/scripts/scènes
│   ├── entity_analyzer.py       # Module 2 : Entités problématiques
│   ├── performance_analyzer.py  # Module 3 : Performance (triggers haute fréquence)
│   ├── security_analyzer.py     # Module 7 : Sécurité
│   ├── report_generator.py      # Module 4 : Génération rapports
│   ├── refactoring_assistant.py # Module 5 : Corrections automatiques
│   ├── conversation.py          # Module 6 : IA Assist
│   │
│   ├── websocket.py             # API WebSocket (haca/* handlers)
│   ├── custom_panel.py          # Enregistrement panneau sidebar
│   ├── translation_utils.py     # Helper traductions backend
│   ├── services.yaml            # Déclaration services HA
│   ├── strings.json             # Strings config flow
│   │
│   ├── translations/
│   │   ├── en.json              # Traductions anglais
│   │   └── fr.json              # Traductions français
│   │
│   └── www/
│       └── haca-panel.js        # Panel frontend (custom element)
```

## Patterns Clés

### 1. DataUpdateCoordinator
- Utilisé pour orchestrer tous les scans périodiques
- Intervalle : configurable (défaut 60 min, min 5, max 1440)
- La méthode `async_update_data()` appelle tous les analyzers en séquence
- Les sensors HA sont des `CoordinatorEntity` qui se mettent à jour automatiquement

### 2. Modules Feature-Flagged
```python
# const.py
MODULE_4_COMPLIANCE_REPORT = True
MODULE_5_REFACTORING_ASSISTANT = True
```
Les modules 4 et 5 sont conditionnellement chargés. Patterns `if MODULE_X:` dans `__init__.py`.

### 3. Séparation des Issues par Type
Le coordinator retourne des données structurées :
```python
{
    "health_score": int,
    "automation_issues": int,      # count only
    "script_issues": int,
    "scene_issues": int,
    "entity_issues": int,
    "performance_issues": int,
    "security_issues": int,
    "total_issues": int,
    "automation_issue_list": list, # full details
    "script_issue_list": list,
    "scene_issue_list": list,
    "entity_issue_list": list,
    "performance_issue_list": list,
    "security_issue_list": list,
}
```

### 4. Structure d'une Issue
```python
{
    "entity_id": "automation.my_automation",
    "alias": "Mon Automation",
    "type": "device_id_in_trigger",  # type unique de l'issue
    "severity": "high",              # high | medium | low
    "message": "...",                # message traduit
    "location": "trigger[0]",        # où dans la config
    "recommendation": "...",         # conseil traduit
    "fix_available": True,           # si correction auto possible
}
```

### 5. WebSocket API
Endpoints enregistrés :
| Type WS | Description |
|---------|-------------|
| `haca/get_data` | Récupère toutes les données du coordinator |
| `haca/scan_all` | Lance un scan complet |
| `haca/preview_fix` | Prévisualise une correction (device_id, mode) |
| `haca/apply_fix` | Applique une correction |
| `haca/list_backups` | Liste les backups disponibles |
| `haca/restore_backup` | Restaure un backup |
| `haca/get_translations` | Récupère les traductions pour le panel |

### 6. Services HA
Services principaux :
- `config_auditor.scan_all` — Scan complet
- `config_auditor.scan_automations` — Scan automations uniquement
- `config_auditor.scan_entities` — Scan entités uniquement
- `config_auditor.generate_report` — Génère rapport MD/JSON/PDF
- `config_auditor.fix_device_id` — Corrige les device_id
- `config_auditor.fix_mode` — Corrige le mode d'une automation
- `config_auditor.purge_ghosts` — Supprime les entités fantômes
- `config_auditor.explain_issue_ai` — Explication IA d'une issue

### 7. Sensors HA Créés
| Sensor | Icône | Description |
|--------|-------|-------------|
| `sensor.haca_health_score` | `mdi:heart-pulse` | Score 0-100% |
| `sensor.haca_automation_issues` | `mdi:robot` | Nb issues automations |
| `sensor.haca_script_issues` | `mdi:script-text` | Nb issues scripts |
| `sensor.haca_scene_issues` | `mdi:palette` | Nb issues scènes |
| `sensor.haca_entity_issues` | `mdi:alert-circle` | Nb issues entités |
| `sensor.haca_performance_issues` | `mdi:speedometer` | Nb issues perf |
| `sensor.haca_total_issues` | `mdi:counter` | Total issues |
| `sensor.haca_security_issues` | `mdi:shield-alert` | Nb issues sécurité |

> Note : `sensor.haca_security_issues` est créé directement via `hass.states.async_set` dans `__init__.py`, pas via la plateforme sensor standard.

### 8. Détection en Temps Réel
Events écoutés pour détecter les nouvelles issues :
- `automation_reloaded`
- `script_reloaded`
- `scene_reloaded`
- `core_config_updated` (avec délai de 5s)

Fichier persistant : `.haca_known_issues.json` pour tracker les issues déjà connues.
Événement custom : `haca_new_issues_detected` pour le panel UI.

### 9. i18n Backend (translation_utils.py)
- `TranslationHelper(hass)` : charge les traductions depuis `translations/{lang}.json`
- Méthode `t(key, **params)` : résout une clé avec interpolation
- Utilisé dans tous les analyzers

### 10. i18n Frontend (haca-panel.js)
- Objet `_defaultTranslations` (fallback EN)
- Chargement dynamique via `haca/get_translations` WebSocket
- Méthode `t(key, params)` : résolution par clés pointées

### 11. Health Score Formula
```python
def calculate_health_score(automation_issues, entity_issues):
    severity_weights = {"high": 5, "medium": 3, "low": 1}
    total_weight = sum(severity_weights.get(issue.get("severity", "low"), 1)
                       for issue in (automation_issues + entity_issues))
    score = int(100 * math.pow(0.99, total_weight))
    return max(0, score)
```
⚠️ **Important** : Seules `automation_issues` + `entity_issues` entrent dans le calcul du score. Les issues de performance et sécurité ne sont PAS prises en compte.

### 12. Backup / Restore
- Répertoire backups : `.haca_backups/`
- Répertoire rapports : `haca_reports/`
- Fichier historique : `.haca_history.json`
- Un backup est créé avant chaque modification par `RefactoringAssistant`

### 13. Chemins de Fichiers Analysés
- `{config_dir}/automations.yaml`
- `{config_dir}/scripts.yaml`
- `{config_dir}/scenes.yaml`

### 14. EntityAnalyzer — Scan des Scripts (V1.3.0)
`analyze_all()` et `_build_entity_references()` acceptent un paramètre optionnel `script_configs` :
```python
def analyze_all(self, script_configs: dict[str, dict] = None) -> list[dict]:
    ...
    entity_refs = self._build_entity_references(script_configs)
```
`__init__.py` transmet `automation_analyzer._script_configs` dans tous les chemins de scan :
- `async_update_data()` → `entity_analyzer.analyze_all(script_configs=...)`
- `handle_scan_entities()` → idem
- `_run_scan()` → idem

### 15. PerformanceAnalyzer — Templates Coûteux (V1.3.0)
Nouvelles méthodes ajoutées :
- `_detect_expensive_templates(automations, scripts)` : parcourt toutes les configs pour détecter les patterns coûteux
- `_extract_templates_recursively(obj)` : extrait récursivement tous les templates d'une structure YAML
Patterns détectés :
- `states | selectattr(...)` sans filtre de domaine → `expensive_template_no_domain`
- `states | list` ou `states | count` global → `expensive_template_states_all`
`get_issue_summary()` inclut désormais `"expensive_templates"` dans son comptage.

### 16. Debounce Pattern sur les Boutons de Scan (V1.3.0)
Le `callService()` dans HA résout immédiatement (avant que le scan backend soit terminé). Ancien pattern `finally` : re-activait les boutons trop tôt.

**Nouveau pattern** appliqué sur `scanAll()`, `scanAutomations()`, `scanEntities()` :
```javascript
async scanAll() {
  if (this._scanAllInProgress) return;       // Guard anti-double-clic
  this._scanAllInProgress = true;
  this._setButtonLoading(btn, true, originalContent);
  try {
    await this.hass.callService('config_auditor', 'scan_all');
    setTimeout(() => {                        // Attente résultats backend
      this.updateFromHass();
      this._scanAllInProgress = false;        // Reset flag
      this._setButtonLoading(btn, false, originalContent);
    }, 3000);
  } catch (error) {
    this._scanAllInProgress = false;          // Reset immédiat en cas d'erreur
    this._setButtonLoading(btn, false, originalContent);
  }
}
```
Flags utilisés : `_scanAllInProgress`, `_scanAutoInProgress`, `_scanEntityInProgress`.

### 17. Protection XSS (V1.3.0)
La méthode `escapeHtml(text)` est appliquée sur toutes les données provenant du backend avant injection dans le DOM :
- `i.alias || i.entity_id || ''` → titre de l'issue
- `i.entity_id || ''` → badge entity
- `i.message || ''` → message de l'issue
- `i.recommendation` → conseil
- `b.name` → nom du backup dans `renderBackups()`
