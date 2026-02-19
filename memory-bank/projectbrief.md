# H.A.C.A - Project Brief

## Nom du Projet
**H.A.C.A — Home Assistant Config Auditor**

## Dépôt
- GitHub : `https://github.com/JeanMarc-Labs/ha-config-auditor`
- Répertoire local : `c:/Users/33698/Desktop/HACA-HEALTH-SCORE-FIX/ha-config-auditor`
- Dernier commit : `a8644c16c6a84b60121d1f914327c5814261d3d1`

## Version Actuelle
- **`manifest.json`** : `1.1.0` ✅
- **`const.py`** : `1.1.0` ✅
- **`haca-panel.js`** : `V1.1.0` ✅ (affiché dans le header UI)
- **HACS** : compatible (fichier `hacs.json` présent)
- **Statut** : version 1.1.0 publiée — tous les bugs critiques corrigés, prêt pour tests d'intégration

## Description
Intégration Home Assistant qui audite la configuration HA (automations, scripts, scènes, entités) pour détecter les mauvaises pratiques, les problèmes de sécurité et de performance, et propose des corrections automatiques.

## Objectifs Principaux
1. **Scanner** les automations, scripts, scènes et entités pour détecter les problèmes
2. **Afficher** un score de santé global (Health Score) de 0 à 100%
3. **Générer** des rapports d'audit (MD, JSON, PDF)
4. **Corriger** automatiquement certains problèmes (refactoring assisté)
5. **Notifier** l'utilisateur en temps réel lors de nouvelles issues détectées
6. **Intégrer** un assistant IA pour expliquer les problèmes

## Modules
| Module | Statut | Description |
|--------|--------|-------------|
| Module 1 - Automation Scanner | ✅ Actif | Analyse automations/scripts/scènes (faux positifs corrigés) |
| Module 2 - Health Monitor | ✅ Actif | Score de santé + entités zombies (scan scripts inclus) |
| Module 3 - Performance Analyzer | ✅ Actif | Triggers haute fréquence + templates coûteux |
| Module 4 - Compliance Report | ✅ Actif | Génération rapports MD/JSON/PDF |
| Module 5 - Refactoring Assistant | ✅ Actif | Corrections automatiques avec backup |
| Module 6 - AI Assist | ✅ Actif | Explication IA des problèmes |
| Module 7 - Security Analyzer | ✅ Actif | Analyse sécurité |

## Contraintes
- Compatible Home Assistant (custom component via HACS)
- Dépendances : `PyYAML>=6.0`, `fpdf2>=2.7.4`
- Internationalisation : FR et EN
- Toujours faire un backup avant toute correction automatique
- `iot_class: local_polling`
