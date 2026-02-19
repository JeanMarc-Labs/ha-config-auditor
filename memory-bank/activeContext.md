# Active Context — HACA

## Focus actuel
La version **1.1.0** est finalisée. Tous les bugs critiques ont été corrigés et le versionnage est cohérent dans tous les fichiers. Le projet est prêt pour publication et tests d'intégration sur Home Assistant.

## Dernières modifications (session 2026-02-19)

### Amélioration du diff ligne par ligne ✅
Fichier modifié : `www/haca-panel.js`
- **`highlightDiff(newText, oldText)`** : Remplacé le simple `escapeHtml()` par un vrai diff ligne par ligne
- **`_buildLCSMatrix(oldLines, newLines)`** : Nouvelle méthode pour construire la matrice LCS (Longest Common Subsequence)
- **`_generateDiffLines(oldLines, newLines, lcs, i, j, result)`** : Nouvelle méthode pour générer le diff par backtracking

#### Fonctionnalités du diff :
- **Lignes ajoutées** : fond vert clair + bordure gauche verte + préfixe `+` vert
- **Lignes supprimées** : fond rouge clair + bordure gauche rouge + préfixe `-` rouge  
- **Lignes inchangées** : affichage normal

#### Algorithme utilisé :
L'algorithme LCS (Longest Common Subsequence) permet d'identifier les lignes communes entre les deux textes et de marquer les additions/suppressions de manière optimale.

## Modifications précédentes (session 2026-02-19)

### Bump de version 1.0.0 → 1.1.0 ✅
Fichiers mis à jour :
- `manifest.json` : `"version": "1.1.0"`
- `const.py` : `VERSION = "1.1.0"` + commentaires modules
- `www/haca-panel.js` : `version: "V1.1.0"` dans `_defaultTranslations`
- `CHANGELOG.md` : section `[1.1.0]` ajoutée
- `CHANGELOG.fr.md` : section `[1.1.0]` ajoutée en français
- Memory Bank : `projectbrief.md`, `techContext.md`, `activeContext.md`, `progress.md` mis à jour

## Modifications précédentes (session 2026-02-18)

### Bugs critiques corrigés ✅

1. **`automation_analyzer.py`** — Faux positifs dans `_analyze_condition()`
   - La condition `template_simple_state` ne se déclenchait pas correctement
   - Fix : vérifie `has_complex_logic`, `has_other_functions`, `has_jinja_filter` avant de signaler

2. **`performance_analyzer.py`** — Détection des templates coûteux
   - Ajout de `import asyncio` et `import re`
   - Nouvelles méthodes : `_detect_expensive_templates()` et `_extract_templates_recursively()`
   - `get_issue_summary()` inclut maintenant `"expensive_templates"` dans le comptage

3. **`entity_analyzer.py`** — Scan des scripts (entités zombies)
   - `analyze_all()` et `_build_entity_references()` acceptent `script_configs: dict[str, dict] = None`
   - Les scripts sont scannés pour détecter les références d'entités (détection zombie)

4. **`__init__.py`** — Câblage des analyzers
   - `async_update_data()` passe `automation_analyzer._script_configs` à `entity_analyzer`
   - Idem dans `handle_scan_entities()` / `_run_scan()`

5. **`translations/en.json`** — 4 nouvelles clés de traduction
   - `expensive_template_no_domain`
   - `add_domain_filter`
   - `expensive_template_states_all`
   - `filter_by_domain`

6. **`translations/fr.json`** — Mêmes 4 clés en français

7. **`www/haca-panel.js`** — Multiples corrections frontend
   - `version: "V1.3.0"` ajouté dans `_defaultTranslations`
   - Protection XSS avec `escapeHtml()` sur : `i.alias`, `i.entity_id`, `i.message`, `i.recommendation`, `b.name`
   - **Debounce sur les 3 boutons de scan** (fix principal de la session) :
     - `scanAll()` : flag `_scanAllInProgress`, re-enable dans `setTimeout` (3s), pas de `finally`
     - `scanAutomations()` : flag `_scanAutoInProgress`, même pattern
     - `scanEntities()` : flag `_scanEntityInProgress`, même pattern

## Pattern debounce appliqué

```javascript
async scanAll() {
  if (this._scanAllInProgress) return;
  this._scanAllInProgress = true;
  // ...
  try {
    await this.hass.callService('config_auditor', 'scan_all');
    setTimeout(() => {
      this.updateFromHass();
      this._scanAllInProgress = false;
      this._setButtonLoading(btn, false, originalContent);
    }, 3000);
  } catch (error) {
    // ...
    this._scanAllInProgress = false;
    this._setButtonLoading(btn, false, originalContent);
  }
}
```

## Prochaines étapes possibles
- Tests d'intégration sur une instance HA réelle
- Vérification des traductions sur interface FR
- Potentiel : ajouter des tests unitaires Python pour les analyzers
- Potentiel : améliorer le `highlightDiff()` pour un vrai diff ligne par ligne

## Patterns importants
- Les templates literals imbriqués dans `haca-panel.js` causent des problèmes SEARCH/REPLACE → toujours rechercher avec le contexte exact incluant les lignes vides
- `callService()` dans HA résout **immédiatement** avant que le scan backend soit terminé → ne jamais utiliser `finally` pour re-activer les boutons de scan
- Le fichier JS est un Web Component pur (pas LitElement) — pas de Shadow DOM
