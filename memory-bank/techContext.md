# H.A.C.A - Tech Context

## Stack Technique

### Backend (Python)
- **Python 3.11+** (requis par Home Assistant 2024+)
- **Home Assistant Core** : intégration custom component
- **PyYAML >= 6.0** : parsing des fichiers de config HA
- **fpdf2 >= 2.7.4** : génération des rapports PDF
- **voluptuous** : validation des schémas de services/config
- **asyncio** : code entièrement asynchrone (pattern HA)

### Frontend (JavaScript)
- **Vanilla JavaScript ES2020+** : pas de framework
- **Custom HTML Element** (`<haca-panel>`) : Web Components standard
- **CSS Custom Properties** : thème HA (`--primary-color`, `--card-background-color`, etc.)
- Fichier unique : `www/haca-panel.js` (~2000+ lignes)

### Infrastructure Home Assistant
- **ConfigEntry** : gestion du cycle de vie via config_entries
- **DataUpdateCoordinator** : pattern standard pour le polling
- **CoordinatorEntity** : sensors liés au coordinator
- **WebSocket API** : communication bidirectionnelle panel ↔ backend
- **Persistent Notifications** : system de notifications HA
- **Entity Registry / Device Registry** : accès au registre des entités

## Fichiers de Configuration

### `manifest.json`
```json
{
  "domain": "config_auditor",
  "name": "Home Assistant Config Auditor (H.A.C.A)",
  "version": "1.1.0",
  "requirements": ["PyYAML>=6.0", "fpdf2>=2.7.4"],
  "iot_class": "local_polling",
  "config_flow": true
}
```

### `hacs.json`
Compatible HACS (Custom Repository).

### `const.py`
```python
DOMAIN = "config_auditor"
NAME = "H.A.C.A"
VERSION = "1.1.0"
DEFAULT_SCAN_INTERVAL = 60  # minutes
MIN_SCAN_INTERVAL = 5
MAX_SCAN_INTERVAL = 1440
```

## Options de Configuration (ConfigEntry)
| Option | Défaut | Min | Max | Description |
|--------|--------|-----|-----|-------------|
| `scan_interval` | 60 | 5 | 1440 | Intervalle scan en minutes |
| `auto_fix_enabled` | False | - | - | Corrections automatiques |
| `backup_enabled` | True | - | - | Backup avant corrections |

## Structure des Traductions
```
translations/
├── en.json    # Anglais
└── fr.json    # Français
```

Les traductions sont organisées sous la clé `panel` dans les fichiers JSON :
```json
{
  "panel": {
    "title": "...",
    "actions": { "scan": "...", "close": "..." },
    "modals": { ... },
    "notifications": { ... },
    ...
  }
}
```

## Outils de Développement Disponibles
(détectés sur la machine de développement)
- `git` — gestion des versions
- `python` — exécution Python
- `node` / `npm` — JS tooling (si besoin)
- `pip` — gestion des dépendances Python
- `code` — VS Code

## Contraintes Techniques

### Asynchrone Obligatoire
Toutes les opérations longues doivent être asynchrones ou déléguées via `async_add_executor_job` :
```python
# Lecture de fichier dans executor
content = await self.hass.async_add_executor_job(read_file)
```

### Yielding dans les boucles
Pour éviter de bloquer la boucle HA lors de l'analyse de nombreuses automations :
```python
for idx, (entity_id, config) in enumerate(self._automation_configs.items()):
    self._analyze_automation(entity_id, config)
    if idx % 10 == 0: await asyncio.sleep(0)
```

### Import conditionnel
Les modules optionnels (4, 5) sont importés conditionnellement :
```python
if MODULE_4_COMPLIANCE_REPORT:
    from .report_generator import ReportGenerator
```

### Panel Registration
Le panneau est enregistré une seule fois (pour la première instance ConfigEntry) :
```python
if len([e for e in hass.config_entries.async_entries(DOMAIN)]) == 1:
    await async_register_panel(hass)
```

### Registre d'Issues Connues
Fichier JSON à la racine du config HA : `.haca_known_issues.json`
Format : liste de signatures `"entity_id|type|message[:100]"`

## État des Versions
- `const.py` : `VERSION = "1.1.0"` ✅
- `manifest.json` : `"version": "1.1.0"` ✅
- `haca-panel.js` : affiche `V1.1.0` dans `_defaultTranslations.version` ✅
- **Point d'attention** : Il y a un conflit d'import potentiel : `custom_panel.py` et `homeassistant.components.panel_custom` sont tous deux importés dans `__init__.py` (le second peut être surchargé par le premier) — à investiguer lors des tests d'intégration.

## Dépendances Inter-modules
```
__init__.py
├── automation_analyzer.py → translation_utils.py
├── entity_analyzer.py → translation_utils.py
├── performance_analyzer.py
├── security_analyzer.py
├── report_generator.py (MODULE_4)
├── refactoring_assistant.py (MODULE_5)
├── conversation.py (MODULE_6)
├── custom_panel.py
└── websocket.py → refactoring_assistant.py
```
