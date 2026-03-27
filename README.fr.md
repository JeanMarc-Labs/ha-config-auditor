# 🛡️ H.A.C.A — Home Assistant Config Auditor

<div align="center">

![Version](https://img.shields.io/badge/version-1.6.3-orange)
![HA](https://img.shields.io/badge/Home%20Assistant-2024.1+-blue)
![Tests](https://img.shields.io/badge/tests-70%20passed-brightgreen)
![License](https://img.shields.io/badge/license-MIT-green)
![HACS](https://img.shields.io/badge/HACS-Custom-blue)

**Auditez, détectez et corrigez automatiquement les problèmes de votre configuration Home Assistant.**

[Documentation complète](https://jeanmarc-labs.github.io/docs-haca/documentation.html) · [English README](README.md) · [Signaler un bug](https://github.com/JeanMarc-Labs/ha-config-auditor/issues)

</div>

---

## Pourquoi H.A.C.A ?

Au fil du temps, une installation Home Assistant accumule des automatisations obsolètes, des entités fantômes, des références cassées, des batteries qui se vident silencieusement et des problèmes de performance difficiles à repérer manuellement. H.A.C.A fait ce travail à votre place — automatiquement, en continu, depuis un panel dédié dans votre sidebar.

---

## Fonctionnalités

| Fonctionnalité | Description |
|---|---|
| 🔍 **Audit continu** | Scan automatique toutes les 60 min (configurable). Score de santé 0-100 exposé comme capteur HA. |
| ⚡ **Corrections 1-clic** | Prévisualisation avant/après. Application directe avec backup automatique YAML. |
| 🤖 **IA intégrée** | Explications, suggestions, optimisation d'automatisations et assistant conversationnel via votre LLM HA configuré. LLM API natif — pas de hacks de prompt. |
| 📊 **Historique & Tendances** | Suivi du score dans le temps. Diff entre scans. Rapports PDF, Markdown et JSON. Fréquence configurable (quotidien / hebdomadaire / mensuel). |
| 🔋 **Batteries + Prédictions** | Surveillance de tous les appareils. Prédiction de durée de vie par régression linéaire. Alertes 7 jours à l'avance. Export CSV. |
| 🗄️ **Recorder DB + Impact** | Détection et purge des entités orphelines. Analyse de l'impact par entité (écritures/jour, Mo/an). YAML exclude prêt à copier. |
| 🔒 **Sécurité** | Détection de secrets codés en dur, données sensibles exposées, configurations vulnérables. Opérations destructives réservées aux admins. |
| ✅ **Conformité** | Audit des conventions de nommage, icônes manquantes, zones manquantes, labels inutilisés — configurable par type. |
| 🗺️ **Complexité des zones** | Heatmap interactive de la complexité par zone. Suggestions de fusion et de découpage. |
| 🔄 **Redondances** | Détection des automations en double logique, candidates à la blueprintisation, et remplaçables par des fonctionnalités HA natives. |
| 🧩 **Helpers** | Onglet dédié à tous les `input_*` et timers avec détection des helpers jamais utilisés. |
| 🔗 **Serveur MCP (65 outils)** | Serveur Model Context Protocol intégré pour 12 agents IA : Claude Desktop, Cursor, VS Code, Windsurf, Cline, n8n et plus. |
| 🗂️ **Graphe de dépendances** | Graphe D3.js avec sidebar de relations (Utilisé par / Utilise), exports CSV et Markdown par nœud ou graphe complet. |

---

## Installation

### Via HACS (recommandé)

> HACS gère les mises à jour automatiquement.

1. Dans HACS → **Intégrations** → **⋮** → **Dépôts personnalisés**
2. URL : `https://github.com/JeanMarc-Labs/ha-config-auditor` · Catégorie : **Intégration**
3. Recherchez **H.A.C.A** → **Télécharger**
4. **Redémarrez Home Assistant** (redémarrage complet obligatoire)
5. **Paramètres → Appareils & Services → + Ajouter une intégration** → cherchez **H.A.C.A**

> ✅ Le panel H.A.C.A apparaît dans la sidebar. Toute la configuration se fait depuis ce panel.

### Installation manuelle

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

## Navigation

Le panel H.A.C.A est organisé en **10 onglets principaux** :

| Onglet | Contenu |
|---|---|
| **Issues** | Toutes les issues détectées — 12 sous-onglets : Tous · Sécurité · Automations · Scripts · Scènes · Entités · Helpers · Performance · Blueprints · Dashboards · **Carte Zones** · **Redondances** |
| **Recorder** | Orphelins en base SQLite · **Impact** (écritures/jour, Mo/an) |
| **History** | Historique des scans, courbe de score, diff entre versions |
| **Backups** | Sauvegardes YAML créées avant chaque correction |
| **Reports** | Rapports PDF/Markdown/JSON |
| **Carte** | Graphe de dépendances D3.js avec exports de relations |
| **Batteries** | Moniteur · **Prédictions** (régression linéaire) |
| **Chat** | Assistant IA conversationnel (LLM API natif, 65 outils MCP) |
| **Compliance** | Audit de qualité des métadonnées |
| **Config** | Options, seuils, token MCP, fréquence rapport, types d'issues activés |

---

## Configuration

> ⚠️ **Toute la configuration se fait depuis le panel H.A.C.A** (onglet ⚙️ Config), pas depuis Paramètres → Appareils & Services.

| Option | Défaut | Description |
|---|---|---|
| `scan_interval` | 60 min | Intervalle de scan automatique (5–1440 min) |
| `battery_alert_threshold` | 20% | Seuil d'alerte batterie (pris en compte sans redémarrage) |
| `notifications_enabled` | true | Notifications HA lors de nouvelles issues HIGH |
| `report_frequency` | weekly | Fréquence du rapport automatique : `daily` / `weekly` / `monthly` / `never` |

### Ignorer des entités

Ajoutez le label **`haca_ignore`** à toute entité, appareil ou zone pour l'exclure de tous les scans.

---

## Intelligence Artificielle

### LLM API natif HA

HACA s'enregistre comme **LLM API natif** dans Home Assistant. Configurez-le une seule fois :

> Paramètres → Assistants vocaux → [votre agent] → LLM API → **HACA**

Ensuite, Mistral, Gemini, Llama ou tout agent conversation HA peut utiliser les 65 outils HACA nativement. Si l'agent préféré échoue (quota, timeout), l'agent suivant est essayé automatiquement.

### Chat IA

L'onglet **Chat** est un assistant IA conversationnel avec accès à **65 outils MCP** permettant de lire, créer, modifier et recharger toute configuration HA.

Exemples de requêtes :
```
"Crée un blueprint à partir de l'automatisation lumières_cuisine et applique-le aux 3 pièces similaires"
"Analyse les 5 automations avec le plus fort impact Recorder et génère un bloc d'exclusion YAML"
"Renomme toutes les entités de la zone Salon pour suivre la convention snake_case"
```

### Boutons IA sur les issues

Chaque issue dispose d'un bouton **IA** qui ouvre le Chat avec un prompt pré-rempli adapté au type d'issue :
- **66 types → Chat impératif** : l'IA exécute directement la correction via les outils MCP
- **8 types informationnels → Explication** : l'IA explique le problème avec des bonnes pratiques

Les issues à correction de champ simple (`no_description`, `no_alias`) affichent une modale avec suggestion éditable — pas besoin du Chat complet.

### Serveur MCP (65 outils)

Le serveur MCP intégré expose tous les outils H.A.C.A et HA aux agents IA externes :

```
# URL du serveur
http://homeassistant.local:8123/api/haca/mcp

# Header d'authentification
Authorization: Bearer <votre-token-haca>
```

**Catégories d'outils :** Audit HACA · Recherche & Découverte · Contrôle · Automations & Scripts · Blueprints · Scènes · Tableaux de bord · Monitoring · Helpers & Zones · Fichiers de configuration · Sécurité & Validation

Agents supportés : Claude Code · Claude Desktop · Cursor · VS Code/Copilot · Windsurf · Cline · Antigravity · Continue.dev · Open WebUI · n8n · HTTP/REST · Gemini CLI

---

## Types d'issues détectés

### 🤖 Automatisations & Scripts

| Type | Sévérité | Correction |
|---|---|---|
| `device_id_in_trigger` / `device_id_in_action` / `device_id_in_target` | 🔴 HIGH | ✅ Auto |
| `incorrect_mode_motion_single` | 🔴 HIGH | ✅ Auto |
| `template_simple_state` | 🟡 MEDIUM | ✅ Auto |
| `no_alias` / `no_description` | 🔵 LOW | ✅ Modale IA |
| `duplicate_automation` / `probable_duplicate_automation` | 🟡 MEDIUM | ✅ Chat IA |
| `potential_self_loop` | 🔴 HIGH | Manuel |
| `high_complexity_actions` | 🟡 MEDIUM | ✅ Chat IA |
| `deprecated_service` | 🔴 HIGH | Manuel |
| `script_blueprint_candidate` | 🟡 MEDIUM | ✅ Chat IA |

### 📦 Entités

| Type | Sévérité | Correction |
|---|---|---|
| `unavailable_entity` / `stale_entity` | 🔴/🟡 | Manuel |
| `zombie_entity` | 🟡 MEDIUM | ✅ Auto |
| `broken_device_reference` | 🔴 HIGH | ✅ Auto |
| `disabled_but_referenced` | 🟡 MEDIUM | Manuel |

### ⚡ Performance & Recorder

| Type | Sévérité |
|---|---|
| `expensive_template_states_all` | 🔴 HIGH |
| `high_parallel_max` | 🟡 MEDIUM |
| `recorder_high_impact` | 🟡 MEDIUM |

### 🛡️ Sécurité

| Type | Sévérité |
|---|---|
| `hardcoded_secret` | 🔴 HIGH |
| `sensitive_data_exposure` | 🔴 HIGH |

### ✅ Conformité

| Type | Sévérité |
|---|---|
| `compliance_no_friendly_name` / `compliance_raw_entity_name` | 🔵 LOW |
| `compliance_area_no_icon` / `compliance_unused_label` | 🔵 LOW |
| `compliance_automation_no_description` / `compliance_automation_no_unique_id` | 🔵 LOW |
| `compliance_entity_no_area` / `compliance_helper_no_icon` / `compliance_helper_no_area` | 🔵 LOW |

### 🗺️ Zones & Redondances *(v1.5.0)*

| Type | Sévérité |
|---|---|
| `area_high_complexity` | 🟡 MEDIUM |
| `area_split_suggested` | 🟡 MEDIUM |
| `area_merge_suggested` | 🔵 LOW |
| `redundancy_overlap` | 🟡 MEDIUM |
| `redundancy_blueprint_candidate` | 🟡 MEDIUM |
| `redundancy_native_ha` | 🔵 LOW |

---

## Services HA

```yaml
# Audit complet
service: config_auditor.scan_all

# Scans sélectifs
service: config_auditor.scan_automations
service: config_auditor.scan_entities
service: config_auditor.scan_compliance

# Prévisualiser une correction
service: config_auditor.preview_device_id
data:
  automation_id: "abc123"

# Appliquer une correction (avec backup automatique)
service: config_auditor.fix_device_id
data:
  automation_id: "abc123"
  dry_run: false  # true = simulation sans écriture

# Générer un rapport
service: config_auditor.generate_report
data:
  format: pdf  # pdf | md | json
```

---

## Intégration dans votre dashboard

```yaml
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

**Capteurs disponibles :**

| Capteur | Description |
|---|---|
| `sensor.haca_health_score` | Score de santé global (0–100) |
| `sensor.haca_total_issues` | Nombre total d'issues |
| `sensor.haca_automation_issues` | Issues d'automatisations |
| `sensor.haca_entity_issues` | Issues d'entités |
| `sensor.haca_battery_low_count` | Appareils sous le seuil batterie |
| `sensor.haca_battery_critical_count` | Appareils sous 10% |
| `sensor.haca_battery_threshold` | Seuil batterie actuel |

---

## Fichiers créés par H.A.C.A

```
/config/
├── custom_components/config_auditor/   # Code de l'intégration
├── .haca_backups/                      # Sauvegardes YAML avant corrections
│   ├── automations_20260314_143022.yaml
│   └── scripts_20260314_091500.yaml
└── .haca_reports/                      # Rapports générés
    ├── haca_report_20260314.pdf
    ├── haca_report_20260314.md
    └── haca_report_20260314.json
```

---

## Licence

MIT © JeanMarc-Labs

---

<div align="center">
<sub>H.A.C.A ne collecte aucune donnée. Tout traitement est local. L'IA utilise uniquement les LLM configurés dans votre Home Assistant.</sub>
</div>
