# H.A.C.A - Product Context

## Pourquoi ce projet existe

Home Assistant est une plateforme de domotique très flexible qui peut rapidement accumuler des configurations sous-optimales : automations utilisant des `device_id` au lieu d'`entity_id`, entités fantômes (zombies), modes d'automation inadaptés, templates trop complexes, etc. Sans outil d'audit, ces problèmes passent inaperçus et dégradent les performances, la stabilité et la sécurité de l'installation.

**H.A.C.A** résout ce problème en offrant un audit automatisé, continu et actionnable de la configuration Home Assistant.

## Problèmes résolus

### Pour l'utilisateur
- Détecte les automations utilisant des `device_id` (fragiles, cassent si l'appareil change)
- Identifie les entités indisponibles/inconnues/périmées référencées dans des automations
- Signale les templates pouvant être remplacés par des conditions natives (plus performants)
- Détecte les automations en mode `single` avec des triggers de mouvement + délais (devraient être `restart`)
- Repère les entités "fantômes" dans le registre (ghost registry entries)
- Analyse les triggers haute fréquence qui surchargent HA
- Vérifie la sécurité (secrets exposés, configurations dangereuses)

### Pour le développeur/mainteneur
- Panel UI intégré dans la sidebar HA
- Score de santé visuel (0-100%)
- Rapports exportables (Markdown, JSON, PDF)
- Corrections one-click avec prévisualisation diff avant/après
- Backup automatique avant toute modification
- Notifications HA persistantes pour les nouvelles issues

## Comment ça fonctionne

### Flux de données
```
automations.yaml / scripts.yaml / scenes.yaml
        ↓
AutomationAnalyzer → issues (automation, script, scene)
EntityAnalyzer → issues (entités unavailable, unknown, zombie...)
PerformanceAnalyzer → issues (triggers haute fréquence)
SecurityAnalyzer → issues (sécurité)
        ↓
DataUpdateCoordinator (polling toutes les 60 min par défaut)
        ↓
Sensors HA + Panel UI (WebSocket)
```

### Score de Santé
Formule progressive : `score = int(100 * 0.99^total_weight)`
- Poids par sévérité : `high=5`, `medium=3`, `low=1`
- Non punitif : 20 issues low → ~81%, 100 issues low → ~36%
- Minimum : 0%

### Panel UI
- Élément custom HTML `<haca-panel>` enregistré dans la sidebar HA
- Communication via WebSocket (`haca/*` endpoints)
- i18n dynamique : charge les traductions depuis `translations/{lang}.json`

## Expérience Utilisateur

1. L'utilisateur installe H.A.C.A via HACS
2. Configure l'intégration (intervalle de scan : 5-1440 min, défaut 60)
3. Un panneau "H.A.C.A" apparaît dans la sidebar avec :
   - Score de santé global
   - Liste des issues par catégorie (automations, scripts, scènes, entités, perf, sécurité)
   - Boutons de correction avec diff avant/après
   - Section rapports (génération MD/JSON/PDF)
   - Section sauvegardes (liste, restauration)
4. Les nouvelles issues déclenchent des notifications persistantes HA
5. L'utilisateur peut demander une explication IA d'une issue

## Cibles Utilisateur
- Utilisateurs Home Assistant intermédiaires à avancés
- Personnes gérant des installations HA complexes (100+ automations)
- Mainteneurs cherchant à améliorer la qualité de leur config
