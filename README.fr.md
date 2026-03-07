# 🛡️ H.A.C.A — Home Assistant Config Auditor

<div align="center">

![Version](https://img.shields.io/badge/version-1.1.2-orange)
![HA](https://img.shields.io/badge/Home%20Assistant-2024.1+-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![HACS](https://img.shields.io/badge/HACS-Custom-blue)

**Auditez, détectez et corrigez automatiquement les problèmes de votre configuration Home Assistant.**

[Documentation complète](https://jeanmarc-labs.github.io/docs-haca/documentation.html) · [English README](README.md) · [Signaler un bug](https://github.com/JeanMarc-Labs/ha-config-auditor/issues)

</div>

---

## Pourquoi H.A.C.A ?

Au fil du temps, une installation Home Assistant accumule des automatisations obsolètes, des entités fantômes, des références cassées et des problèmes de performance difficiles à repérer manuellement. H.A.C.A fait ce travail à votre place — automatiquement, en continu, depuis un panel dédié dans votre sidebar.

---

## Fonctionnalités

| Fonctionnalité | Description |
|---|---|
| 🔍 **Audit continu** | Scan automatique toutes les 60 min (configurable). Score de santé en temps réel exposé comme capteur HA. |
| ⚡ **Corrections 1-clic** | Prévisualisation avant/après. Application directe avec backup automatique YAML. |
| 🤖 **IA intégrée** | Explications, suggestions de description et optimisation d'automatisations complexes via le LLM configuré dans HA. |
| 📊 **Historique** | Suivi du score de santé dans le temps. Rapports exportables en PDF, Markdown et JSON. |
| 🔋 **Batteries** | Surveillance de tous les appareils. Alertes configurables. Capteurs HA exposés. |
| 🗄️ **Recorder DB** | Détection et purge des entités orphelines dans la base de données. |
| 🔒 **Sécurité** | Détection de secrets codés en dur, données sensibles et configurations vulnérables. |

---

## Installation

### Via HACS (recommandé)

> HACS gère les mises à jour automatiquement.

1. Dans HACS → **Intégrations** → **⋮** → **Dépôts personnalisés**
2. URL : `https://github.com/JeanMarc-Labs/ha-config-auditor` · Catégorie : **Intégration**
3. Recherchez **H.A.C.A** → **Télécharger**
4. Redémarrez Home Assistant (redémarrage complet obligatoire)
5. **Paramètres → Appareils & Services → + Ajouter une intégration** → cherchez **H.A.C.A**

> ✅ Le panel H.A.C.A apparaît dans la sidebar. Toute la configuration se fait depuis ce panel.

### Manuelle

```bash
git clone https://github.com/JeanMarc-Labs/ha-config-auditor.git
cp -r ha-config-auditor/custom_components/config_auditor /config/custom_components/
# Redémarrer HA, puis ajouter l'intégration depuis Paramètres → Appareils & Services
```

### Prérequis

- Home Assistant **2024.1** ou supérieur
- Python 3.12+ (inclus avec HA)
- Accès en lecture/écriture à `/config/`

---

## Configuration

> ⚠️ **Toute la configuration se fait depuis le panel H.A.C.A** (sidebar → H.A.C.A → onglet ⚙️ Configuration), pas depuis Paramètres → Appareils & Services.

| Option | Défaut | Description |
|---|---|---|
| `scan_interval` | 60 min | Intervalle de scan automatique (5–1440 min) |
| `battery_alert_threshold` | 20% | Seuil d'alerte batterie |
| `notifications_enabled` | true | Notifications HA lors de nouvelles issues |

---

## Types d'issues détectés

### 🤖 Automatisations & Scripts

| Type | Sévérité | Correction auto |
|---|---|---|
| `device_id_in_trigger` | 🔴 HIGH | ✅ |
| `device_id_in_action` | 🔴 HIGH | ✅ |
| `device_id_in_target` | 🔴 HIGH | ✅ |
| `incorrect_mode_motion_single` | 🔴 HIGH | ✅ |
| `template_simple_state` | 🟡 MEDIUM | ✅ |
| `no_alias` / `no_description` | 🔵 LOW | ✅ (IA) |
| `duplicate_automation` | 🟡 MEDIUM | Manuel |
| `potential_self_loop` | 🔴 HIGH | Manuel |
| `high_complexity_actions` | 🟡 MEDIUM | ✅ (IA) |
| `deprecated_service` | 🔴 HIGH | Manuel |

### 📦 Entités

| Type | Sévérité | Correction auto |
|---|---|---|
| `unavailable_entity` | 🔴 HIGH | Manuel |
| `zombie_entity` | 🟡 MEDIUM | ✅ |
| `broken_device_reference` | 🔴 HIGH | ✅ |
| `stale_entity` | 🟡 MEDIUM | Manuel |
| `disabled_but_referenced` | 🟡 MEDIUM | Manuel |

### ⚡ Performance

| Type | Sévérité |
|---|---|
| `expensive_template_states_all` | 🔴 HIGH |
| `template_time_check` | 🟡 MEDIUM |
| `excessive_delay` | 🔵 LOW |
| `high_parallel_max` | 🟡 MEDIUM |

### 🛡️ Sécurité

| Type | Sévérité |
|---|---|
| `hardcoded_secret` | 🔴 HIGH |
| `sensitive_data_exposure` | 🔴 HIGH |

---

## Services HA

```yaml
# Audit complet
service: config_auditor.scan_all

# Scans sélectifs
service: config_auditor.scan_automations
service: config_auditor.scan_entities
service: config_auditor.scan_performance

# Prévisualiser une correction
service: config_auditor.preview_device_id
data:
  automation_id: "abc123"

# Appliquer une correction
service: config_auditor.fix_device_id
data:
  automation_id: "abc123"
  dry_run: false  # true = simulation sans écriture

# Générer un rapport
service: config_auditor.generate_report
data:
  format: pdf  # pdf | markdown | json | all
```

---

## Intégration dans votre dashboard

Le score de santé est exposé comme capteur HA :

```yaml
# Automatisation d'alerte
automation:
  - alias: "HACA : Alerte score santé bas"
    trigger:
      - platform: numeric_state
        entity_id: sensor.haca_health_score
        below: 70
    action:
      - service: notify.mobile_app
        data:
          title: "⚠️ Configuration HA dégradée"
          message: "Score : {{ states('sensor.haca_health_score') }}/100"
```

Capteurs disponibles :

| Capteur | Description |
|---|---|
| `sensor.haca_health_score` | Score de santé global (0–100) |
| `sensor.haca_total_issues` | Nombre total d'issues |
| `sensor.haca_automation_issues` | Issues d'automatisations |
| `sensor.haca_entity_issues` | Issues d'entités |
| `sensor.haca_battery_low_count` | Appareils sous le seuil batterie |

---

## Fichiers créés par H.A.C.A

```
/config/
├── custom_components/config_auditor/   # Code de l'intégration
├── .haca_backups/                      # Sauvegardes YAML avant corrections
│   └── automations_20240315_143022.yaml
└── .haca_reports/                      # Rapports générés
    ├── haca_report_20240315.pdf
    ├── haca_report_20240315.md
    └── haca_report_20240315.json
```

---

## Licence

MIT © JeanMarc-Labs

---

<div align="center">
<sub>H.A.C.A ne collecte aucune donnée. Tout traitement est local. L'IA utilise uniquement les LLM configurés dans votre Home Assistant.</sub>
</div>
