# Guide de contribution — H.A.C.A

> 🇬🇧 [English version](CONTRIBUTING.md)

Merci de votre intérêt pour H.A.C.A ! Ce document explique comment contribuer au projet.

---

## Table des matières

- [Code de conduite](#code-de-conduite)
- [Comment contribuer](#comment-contribuer)
- [Signaler un bug](#signaler-un-bug)
- [Proposer une amélioration](#proposer-une-amélioration)
- [Soumettre une Pull Request](#soumettre-une-pull-request)
- [Structure du projet](#structure-du-projet)
- [Environnement de développement](#environnement-de-développement)
- [Conventions de code](#conventions-de-code)
- [Tests](#tests)

---

## Code de conduite

Ce projet adhère à un code de conduite simple : **respectez les autres contributeurs**. Les échanges doivent rester constructifs, bienveillants et axés sur le projet.

---

## Comment contribuer

Plusieurs façons de contribuer :

- **Signaler un bug** via les [Issues GitHub](https://github.com/JeanMarc-Labs/ha-config-auditor/issues)
- **Proposer une nouvelle fonctionnalité** via les Issues (label `enhancement`)
- **Améliorer la documentation** (README, commentaires de code)
- **Soumettre une Pull Request** avec une correction ou une nouveauté
- **Tester** la version de développement et remonter des retours

---

## Signaler un bug

Avant d'ouvrir une issue, vérifiez qu'elle n'existe pas déjà.

**Informations à fournir :**

1. Version de H.A.C.A (visible dans le panel → Configuration)
2. Version de Home Assistant
3. Description précise du comportement observé vs. comportement attendu
4. Étapes pour reproduire le bug
5. Logs HA pertinents (activer le mode debug dans Configuration → Diagnostics & Logs)
6. Capture d'écran si pertinent

```yaml
# Pour activer les logs debug dans configuration.yaml :
logger:
  logs:
    custom_components.config_auditor: debug
```

---

## Proposer une amélioration

Ouvrir une issue avec le label `enhancement` en décrivant :

- Le problème que la fonctionnalité résout
- Le comportement attendu
- Des exemples d'usage concrets
- Si possible, une esquisse d'implémentation

---

## Soumettre une Pull Request

### Workflow

1. **Forker** le dépôt sur GitHub
2. **Créer une branche** depuis `main` :
   ```bash
   git checkout -b feat/nom-de-la-fonctionnalite
   # ou
   git checkout -b fix/description-du-bug
   ```
3. **Développer** en suivant les conventions ci-dessous
4. **Tester** : tous les tests existants doivent passer
5. **Commiter** avec des messages clairs (voir convention ci-dessous)
6. **Pousser** et ouvrir une Pull Request vers `main`

### Convention des commits

```
type(scope): description courte en français ou anglais

feat(analyzer): ajouter la détection des automations en mode restart
fix(panel): corriger le scroll dans la modal de proposition IA
docs(readme): mettre à jour la section installation
test(health_score): ajouter les cas limites score=0 et score=100
refactor(websocket): extraire la logique de scan dans une fonction dédiée
```

Types : `feat`, `fix`, `docs`, `test`, `refactor`, `style`, `chore`

### Critères d'acceptation d'une PR

- Les tests passent (`python3 -m pytest tests/ -v`)
- Le code respecte les conventions (voir ci-dessous)
- La PR est accompagnée d'une description claire du changement
- Les nouvelles fonctionnalités sont documentées

---

## Structure du projet

```
ha-config-auditor/
├── README.md                    # Documentation principale (EN)
├── README.fr.md                 # Documentation (FR)
├── CONTRIBUTING.md              # Guide de contribution (EN)
├── CONTRIBUTING.fr.md           # Guide de contribution (FR)
├── CHANGELOG.md                 # Journal des modifications
├── LICENSE                      # Licence MIT
├── hacs.json                    # Métadonnées HACS
└── custom_components/
    └── config_auditor/
        ├── __init__.py          # Setup et teardown de l'intégration
        ├── manifest.json        # Métadonnées HA
        ├── const.py             # Constantes globales
        ├── config_flow.py       # Flux de configuration HA
        ├── websocket.py         # Handlers WebSocket (API panel)
        ├── services.py          # Services HA déclarés
        ├── services.yaml        # Schémas des services
        ├── sensor.py            # Entités capteur HA
        ├── custom_panel.py      # Enregistrement du panel frontend
        ├── automation_analyzer.py
        ├── entity_analyzer.py
        ├── performance_analyzer.py
        ├── security_analyzer.py
        ├── dashboard_analyzer.py
        ├── recorder_analyzer.py
        ├── battery_monitor.py
        ├── dependency_mapper.py
        ├── refactoring_assistant.py
        ├── automation_optimizer.py
        ├── report_generator.py
        ├── history_manager.py
        ├── health_score.py
        ├── conversation.py      # Chat IA
        ├── event_monitor.py     # Monitoring événementiel
        ├── translation_utils.py
        ├── models.py
        ├── translations/
        │   ├── fr.json
        │   └── en.json
        ├── www/
        │   └── haca-panel.js    # Frontend (bundle compilé)
        └── tests/
            ├── conftest.py
            └── test_*.py
```

Le frontend source se trouve dans `www/src/` (non inclus dans le dépôt HACS).  
Pour modifier le frontend, cloner le dépôt de développement séparé.

---

## Environnement de développement

### Prérequis

- Python 3.12+
- Home Assistant installé en mode développement ou via Docker

### Installation

```bash
git clone https://github.com/JeanMarc-Labs/ha-config-auditor
cd ha-config-auditor/custom_components/config_auditor

# Installer les dépendances de test
pip install pytest pytest-asyncio homeassistant PyYAML fpdf2 --break-system-packages
```

### Lancer les tests

```bash
python3 -m pytest tests/ -v
# Avec couverture
python3 -m pytest tests/ -v --tb=short
```

### Déploiement local pour test

```bash
# Copier dans votre instance HA de développement
cp -r custom_components/config_auditor /config/custom_components/
# Redémarrer HA
```

---

## Conventions de code

### Python

- **Style** : PEP 8 strict, lignes ≤ 100 caractères
- **Type hints** : obligatoires sur toutes les fonctions publiques
- **Docstrings** : format Google pour toutes les fonctions non triviales
- **Logging** : utiliser `_LOGGER = logging.getLogger(__name__)` dans chaque module
- **Async** : tout le code HA doit être async-safe
- **Pas de `time.sleep()`** dans le code HA — utiliser `asyncio.sleep()`

```python
# Bon exemple
async def analyze_automation(
    hass: HomeAssistant,
    automation: dict[str, Any],
) -> list[Issue]:
    """Analyse une automation et retourne les issues détectées.

    Args:
        hass: Instance Home Assistant.
        automation: Données brutes de l'automation.

    Returns:
        Liste d'issues détectées, vide si aucune.
    """
    ...
```

### JavaScript (frontend)

- **ES2020+**, pas de framework (Vanilla JS + Web Components)
- Les méthodes publiques du panel sont documentées par un commentaire `//`
- Les appels WebSocket passent par `this._hass.callWS()`
- Les appels de service passent par `this._hass.callService()`
- Toujours vérifier `this._hass` avant usage

---

## Tests

### Organisation

```
tests/
├── conftest.py                    # Fixtures partagées (mocks HA)
├── test_automation_analyzer.py    # Tests analyseur automations
├── test_health_score.py           # Tests score de santé
├── test_infrastructure.py         # Tests setup/teardown intégration
├── test_models.py                 # Tests modèles de données
├── test_refactoring_assistant.py  # Tests corrections automatiques
├── test_event_monitor.py          # Tests monitoring événementiel
└── test_repairs.py                # Tests module Repairs (skippés)
```

### Écrire un test

```python
import pytest
from custom_components.config_auditor.automation_analyzer import AutomationAnalyzer

async def test_detects_device_id_in_trigger(mock_hass):
    """Vérifie que les device_id dans les déclencheurs sont détectés."""
    automation = {
        "id": "test_auto",
        "alias": "Test",
        "trigger": [{"platform": "device", "device_id": "abc123"}],
        "action": [],
    }
    analyzer = AutomationAnalyzer(mock_hass)
    issues = await analyzer.analyze_automation(automation)
    assert any(i.type == "device_id_in_trigger" for i in issues)
```

---

## Questions ?

Ouvrir une [Discussion GitHub](https://github.com/JeanMarc-Labs/ha-config-auditor/discussions) pour toute question qui n'est pas un bug ou une demande de fonctionnalité.
