// ── config_tab.js ─────────────────────────────────────────────────────────
// Onglet Configuration du panel HACA
// Remplace le flux d'options HA natif (config/integrations)
// Inclut les exclusions par type d'issue (granularité fine)
// ──────────────────────────────────────────────────────────────────────────

/**
 * Tous les types d'issues, groupés par catégorie.
 * labelFr / labelEn = libellé court dans la checkbox.
 * fixable = true si réparable depuis HA Repairs.
 */
var ISSUE_TYPES_BY_CATEGORY = [
  {
    id: 'automations',
    icon: 'mdi:robot',
    labelFr: 'Automations',
    labelEn: 'Automations',
    types: [
      { id: 'device_id_in_trigger', fr: 'device_id dans déclencheur', en: 'device_id in trigger', fixable: true },
      { id: 'device_trigger_platform', fr: 'Plateforme device (déclencheur)', en: 'Device platform (trigger)', fixable: true },
      { id: 'device_id_in_condition', fr: 'device_id dans condition', en: 'device_id in condition', fixable: true },
      { id: 'device_condition_platform', fr: 'Plateforme device (condition)', en: 'Device platform (condition)', fixable: true },
      { id: 'device_id_in_action', fr: 'device_id dans action', en: 'device_id in action', fixable: true },
      { id: 'device_id_in_target', fr: 'device_id dans cible', en: 'device_id in target', fixable: true },
      { id: 'template_simple_state', fr: 'Template → condition native', en: 'Template → native condition', fixable: true },
      { id: 'incorrect_mode_motion_single', fr: 'Mode incorrect (motion)', en: 'Incorrect mode (motion)', fixable: true },
      { id: 'deprecated_service', fr: 'Service déprécié', en: 'Deprecated service', fixable: false },
      { id: 'unknown_service', fr: 'Service inconnu', en: 'Unknown service', fixable: false },
      { id: 'no_description', fr: 'Pas de description', en: 'No description', fixable: false },
      { id: 'no_alias', fr: "Pas d'alias", en: 'No alias', fixable: false },
      { id: 'duplicate_automation', fr: 'Automation dupliquée', en: 'Duplicate automation', fixable: false },
      { id: 'probable_duplicate_automation', fr: 'Probable doublon', en: 'Probable duplicate', fixable: false },
      { id: 'ghost_automation', fr: 'Automation fantôme', en: 'Ghost automation', fixable: false },
      { id: 'never_triggered', fr: 'Jamais déclenchée', en: 'Never triggered', fixable: false },
      { id: 'excessive_delay', fr: 'Délai excessif', en: 'Excessive delay', fixable: false },
      { id: 'wait_template_vs_wait_for_trigger', fr: 'wait_template → wait_for_trigger', en: 'wait_template → wait_for_trigger', fixable: false },
      { id: 'zone_no_entity', fr: 'Zone sans entité', en: 'Zone without entity', fixable: false },
      { id: 'unknown_area_reference', fr: 'Zone inconnue', en: 'Unknown area', fixable: false },
      { id: 'unknown_floor_reference', fr: 'Étage inconnu', en: 'Unknown floor', fixable: false },
      { id: 'unknown_label_reference', fr: 'Label inconnu', en: 'Unknown label', fixable: false },
      { id: 'template_numeric_comparison', fr: 'Comparaison numérique dans template', en: 'Numeric comparison in template', fixable: false },
      { id: 'template_time_check', fr: 'Vérification heure dans template', en: 'Time check in template', fixable: false },
    ]
  },
  {
    id: 'entities',
    icon: 'mdi:tag-multiple',
    labelFr: 'Entités',
    labelEn: 'Entities',
    types: [
      { id: 'zombie_entity', fr: 'Entité zombie (référencée, supprimée)', en: 'Zombie entity (referenced, removed)', fixable: true },
      { id: 'broken_device_reference', fr: 'Référence appareil cassée', en: 'Broken device reference', fixable: true },
      { id: 'unavailable_entity', fr: 'Entité indisponible', en: 'Unavailable entity', fixable: false },
      { id: 'unknown_state', fr: 'État inconnu', en: 'Unknown state', fixable: false },
      { id: 'stale_entity', fr: 'Entité obsolète', en: 'Stale entity', fixable: false },
      { id: 'disabled_but_referenced', fr: 'Désactivée mais référencée', en: 'Disabled but referenced', fixable: false },
      { id: 'ghost_registry_entry', fr: 'Entrée fantôme dans le registre', en: 'Ghost registry entry', fixable: true },
      { id: 'unused_input_boolean', fr: 'input_boolean inutilisé', en: 'Unused input_boolean', fixable: false },
    ]
  },
  {
    id: 'security',
    icon: 'mdi:shield-alert',
    labelFr: 'Sécurité',
    labelEn: 'Security',
    types: [
      { id: 'hardcoded_secret', fr: 'Secret codé en dur', en: 'Hardcoded secret', fixable: false },
      { id: 'sensitive_data_exposure', fr: 'Exposition données sensibles', en: 'Sensitive data exposure', fixable: false },
    ]
  },
  {
    id: 'performance',
    icon: 'mdi:speedometer',
    labelFr: 'Performance',
    labelEn: 'Performance',
    types: [
      { id: 'high_complexity_actions', fr: 'Actions très complexes', en: 'High complexity actions', fixable: false },
      { id: 'high_parallel_max', fr: 'parallel_max élevé', en: 'High parallel_max', fixable: false },
      { id: 'potential_self_loop', fr: 'Boucle potentielle', en: 'Potential self-loop', fixable: false },
      { id: 'missing_state_class', fr: 'state_class manquant', en: 'Missing state_class', fixable: false },
      { id: 'expensive_template_selectattr', fr: 'Template selectattr coûteux', en: 'Expensive selectattr template', fixable: false },
      { id: 'expensive_template_states_all', fr: "Template states.all coûteux", en: 'Expensive states.all template', fixable: false },
    ]
  },
  {
    id: 'blueprints',
    icon: 'mdi:file-document-outline',
    labelFr: 'Blueprints',
    labelEn: 'Blueprints',
    types: [
      { id: 'blueprint_missing_path', fr: 'Chemin blueprint manquant', en: 'Missing blueprint path', fixable: false },
      { id: 'blueprint_file_not_found', fr: 'Fichier blueprint introuvable', en: 'Blueprint file not found', fixable: false },
      { id: 'blueprint_empty_input', fr: 'Entrée blueprint vide', en: 'Empty blueprint input', fixable: false },
      { id: 'blueprint_no_inputs', fr: 'Blueprint sans entrées', en: 'Blueprint with no inputs', fixable: false },
    ]
  },
  {
    id: 'dashboards',
    icon: 'mdi:view-dashboard',
    labelFr: 'Tableaux de bord',
    labelEn: 'Dashboards',
    types: [
      { id: 'dashboard_missing_entity', fr: 'Entité manquante dans dashboard', en: 'Missing entity in dashboard', fixable: false },
    ]
  },
];

// ─── Rendering ────────────────────────────────────────────────────────────

function renderConfigTab(options, lang) {
  lang = lang || 'fr';
  var t = function (fr, en) { return lang === 'fr' ? fr : en; };
  var excludedTypes = new Set(options.excluded_issue_types || []);

  var categorySections = ISSUE_TYPES_BY_CATEGORY.map(function (cat) {
    var label = lang === 'fr' ? cat.labelFr : cat.labelEn;

    var typeRows = cat.types.map(function (tp) {
      var enabled = !excludedTypes.has(tp.id);
      var tpLabel = lang === 'fr' ? tp.fr : tp.en;
      var fixBadge = tp.fixable
        ? '<span class="cfg-badge cfg-badge-fix">' + t('✓ Auto-fixable', '✓ Auto-fixable') + '</span>'
        : '';
      return '<label class="cfg-type-row' + (enabled ? '' : ' disabled') + '" data-type="' + tp.id + '">' +
        '<span class="cfg-type-label">' + tpLabel + fixBadge + '</span>' +
        '<label class="cfg-toggle cfg-toggle-sm">' +
        '<input type="checkbox" class="cfg-type-toggle" data-type="' + tp.id + '"' + (enabled ? ' checked' : '') + '>' +
        '<span class="cfg-toggle-slider"></span>' +
        '</label>' +
        '</label>';
    }).join('');

    return '<div class="cfg-cat-section">' +
      '<div class="cfg-cat-section-header">' +
      '<div class="cfg-cat-header-left">' +
      '<ha-icon icon="' + cat.icon + '" style="--mdc-icon-size:18px;color:var(--primary-color);"></ha-icon>' +
      '<span class="cfg-cat-section-title">' + label + '</span>' +
      '<span class="cfg-cat-count" id="count-' + cat.id + '"></span>' +
      '</div>' +
      '<div class="cfg-cat-header-actions">' +
      '<button class="cfg-cat-all-btn" data-cat="' + cat.id + '" data-action="enable">' + t('Tout activer', 'Enable all') + '</button>' +
      '<button class="cfg-cat-all-btn" data-cat="' + cat.id + '" data-action="disable">' + t('Tout désactiver', 'Disable all') + '</button>' +
      '</div>' +
      '</div>' +
      '<div class="cfg-type-list" id="types-' + cat.id + '">' + typeRows + '</div>' +
      '</div>';
  }).join('');

  return '<div class="cfg-root">' +

    // ── Header ──
    '<div class="cfg-header">' +
    '<ha-icon icon="mdi:cog" style="--mdc-icon-size:28px;color:var(--primary-color);"></ha-icon>' +
    '<div>' +
    '<div class="cfg-header-title">' + t('Configuration H.A.C.A', 'H.A.C.A Configuration') + '</div>' +
    '<div class="cfg-header-sub">' + t('Paramètres généraux, seuils et types d\'issues actifs', 'General settings, thresholds and active issue types') + '</div>' +
    '</div>' +
    '</div>' +

    // ── Section : Scan ──
    '<div class="cfg-section">' +
    '<div class="cfg-section-title"><ha-icon icon="mdi:magnify-scan" style="--mdc-icon-size:18px;"></ha-icon>' + t('Scan automatique', 'Automatic scan') + '</div>' +
    '<div class="cfg-row">' +
    '<div class="cfg-row-label"><span>' + t('Intervalle de scan (minutes)', 'Scan interval (minutes)') + '</span><span class="cfg-row-hint">5 – 1440 min</span></div>' +
    '<input type="number" id="cfg-scan-interval" class="cfg-input" min="5" max="1440" value="' + (options.scan_interval || 60) + '">' +
    '</div>' +
    '<div class="cfg-row">' +
    '<div class="cfg-row-label"><span>' + t('Délai au démarrage (secondes)', 'Startup delay (seconds)') + '</span><span class="cfg-row-hint">0 – 300 s</span></div>' +
    '<input type="number" id="cfg-startup-delay" class="cfg-input" min="0" max="300" value="' + (options.startup_delay_seconds || 60) + '">' +
    '</div>' +
    '</div>' +

    // ── Section : Événements ──
    '<div class="cfg-section">' +
    '<div class="cfg-section-title"><ha-icon icon="mdi:bell-ring-outline" style="--mdc-icon-size:18px;"></ha-icon>' + t('Surveillance des événements', 'Event monitoring') + '</div>' +
    '<div class="cfg-row">' +
    '<div class="cfg-row-label"><span>' + t('Surveillance active', 'Active monitoring') + '</span><span class="cfg-row-hint">' + t('Rescan après modification', 'Auto-rescan after changes') + '</span></div>' +
    '<label class="cfg-toggle"><input type="checkbox" id="cfg-event-monitoring"' + (options.event_monitoring_enabled !== false ? ' checked' : '') + '><span class="cfg-toggle-slider"></span></label>' +
    '</div>' +
    '<div class="cfg-row" id="cfg-debounce-row">' +
    '<div class="cfg-row-label"><span>' + t('Délai anti-rebond (secondes)', 'Debounce delay (seconds)') + '</span><span class="cfg-row-hint">5 – 300 s</span></div>' +
    '<input type="number" id="cfg-event-debounce" class="cfg-input" min="5" max="300" value="' + (options.event_debounce_seconds || 30) + '">' +
    '</div>' +
    '</div>' +

    // ── Section : Types d'issues ──
    '<div class="cfg-section">' +
    '<div class="cfg-section-title">' +
    '<ha-icon icon="mdi:checkbox-multiple-marked-outline" style="--mdc-icon-size:18px;"></ha-icon>' +
    t('Types d\'issues à détecter', 'Issue types to detect') +
    '</div>' +
    '<div class="cfg-section-hint">' +
    t('Décochez les types que vous ne souhaitez pas voir dans le tableau de bord. ' +
      'Les types en ✓ Auto-fixable peuvent être réparés automatiquement.',
      'Uncheck issue types you don\'t want to see in the dashboard. ' +
      'Types marked ✓ Auto-fixable can be automatically repaired.') +
    '</div>' +
    '<div class="cfg-categories-root">' + categorySections + '</div>' +
    '</div>' +

    // ── Section : Batteries ──
    '<div class="cfg-section">' +
    '<div class="cfg-section-title"><ha-icon icon="mdi:battery" style="--mdc-icon-size:18px;"></ha-icon>' + t('Seuils batterie', 'Battery thresholds') + '</div>' +
    '<div class="cfg-row"><div class="cfg-row-label"><span>🔴 ' + t('Critique (%)', 'Critical (%)') + '</span></div><input type="number" id="cfg-battery-critical" class="cfg-input" min="1" max="50" value="' + (options.battery_critical || 5) + '"></div>' +
    '<div class="cfg-row"><div class="cfg-row-label"><span>🟠 ' + t('Faible (%)', 'Low (%)') + '</span></div><input type="number" id="cfg-battery-low" class="cfg-input" min="5" max="50" value="' + (options.battery_low || 15) + '"></div>' +
    '<div class="cfg-row"><div class="cfg-row-label"><span>🟡 ' + t('Avertissement (%)', 'Warning (%)') + '</span></div><input type="number" id="cfg-battery-warning" class="cfg-input" min="10" max="75" value="' + (options.battery_warning || 25) + '"></div>' +
    '</div>' +

    // ── Section : Historique ──
    '<div class="cfg-section">' +
    '<div class="cfg-section-title"><ha-icon icon="mdi:history" style="--mdc-icon-size:18px;"></ha-icon>' + t('Historique & Sauvegardes', 'History & Backups') + '</div>' +
    '<div class="cfg-row">' +
    '<div class="cfg-row-label"><span>' + t('Rétention de l\'historique (jours)', 'History retention (days)') + '</span><span class="cfg-row-hint">30 – 730</span></div>' +
    '<input type="number" id="cfg-history-retention" class="cfg-input" min="30" max="730" value="' + (options.history_retention_days || 365) + '">' +
    '</div>' +
    '<div class="cfg-row">' +
    '<div class="cfg-row-label"><span>' + t('Sauvegarde automatique avant fix', 'Auto-backup before fix') + '</span><span class="cfg-row-hint">' + t('Recommandé', 'Recommended') + '</span></div>' +
    '<label class="cfg-toggle"><input type="checkbox" id="cfg-backup-enabled"' + (options.backup_enabled !== false ? ' checked' : '') + '><span class="cfg-toggle-slider"></span></label>' +
    '</div>' +
    '</div>' +

    // ── Section Diagnostics & Logs ──
    '<div class="cfg-section" style="margin-top:4px;">' +
    '<div class="cfg-section-title"><ha-icon icon="mdi:bug" style="--mdc-icon-size:18px;color:var(--warning-color,#ffa726);"></ha-icon>' + t('Diagnostics &amp; Logs', 'Diagnostics &amp; Logs') + '</div>' +
    '<div class="cfg-row" style="align-items:flex-start;">' +
    '<div class="cfg-row-label">' +
    '<span>' + t('Mode debug', 'Debug mode') + '</span>' +
    '<span class="cfg-row-hint">' + t('Logs détaillés dans Paramètres → Système → Journaux', 'Detailed logs in Settings → System → Logs') + '</span>' +
    '</div>' +
    '<label class="cfg-toggle">' +
    '<input type="checkbox" id="cfg-debug-toggle">' +
    '<span class="cfg-toggle-slider"></span>' +
    '</label>' +
    '</div>' +
    '<div style="margin-top:12px;padding:10px 14px;background:var(--secondary-background-color);border-radius:8px;font-size:11px;color:var(--secondary-text-color);line-height:1.9;">' +
    t('Filtrer dans les logs HA :', 'Filter in HA logs:') + ' <code>custom_components.config_auditor</code><br>' +
    t('Pour persister entre redémarrages, ajoutez dans', 'To persist across restarts, add to') + ' <code>configuration.yaml</code> :<br>' +
    '<code style="display:block;margin-top:4px;padding:6px 8px;background:rgba(0,0,0,0.1);border-radius:4px;white-space:pre;">logger:\n  logs:\n    custom_components.config_auditor: debug</code>' +
    '</div>' +
    '</div>' +

    // ── Boutons ──
    '<div class="cfg-actions">' +
    '<button class="cfg-btn cfg-btn-secondary" id="cfg-reset-btn"><ha-icon icon="mdi:restore" style="--mdc-icon-size:18px;"></ha-icon>' + t('Réinitialiser', 'Reset') + '</button>' +
    '<button class="cfg-btn cfg-btn-primary" id="cfg-save-btn"><ha-icon icon="mdi:content-save" style="--mdc-icon-size:18px;"></ha-icon>' + t('Enregistrer', 'Save') + '</button>' +
    '</div>' +
    '<div id="cfg-save-status" class="cfg-save-status" style="display:none;"></div>' +
    '</div>';
}

// ─── CSS ──────────────────────────────────────────────────────────────────

var CONFIG_TAB_CSS = `
  .cfg-root { max-width: 860px; margin: 0 auto; padding: 24px 20px 48px; display: flex; flex-direction: column; gap: 20px; }
  .cfg-header { display: flex; align-items: center; gap: 16px; padding: 20px 24px; background: var(--card-background-color); border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
  .cfg-header-title { font-size: 1.2em; font-weight: 700; color: var(--primary-text-color); }
  .cfg-header-sub { font-size: 0.85em; color: var(--secondary-text-color); margin-top: 2px; }
  .cfg-section { background: var(--card-background-color); border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); overflow: hidden; }
  .cfg-section-title { display: flex; align-items: center; gap: 8px; padding: 16px 20px 12px; font-weight: 700; font-size: 0.9em; color: var(--primary-color); text-transform: uppercase; letter-spacing: 0.04em; border-bottom: 1px solid var(--divider-color); }
  .cfg-section-hint { font-size: 0.82em; color: var(--secondary-text-color); padding: 10px 20px; background: rgba(var(--rgb-primary-color,33,150,243),0.04); border-bottom: 1px solid var(--divider-color); line-height: 1.5; }
  .cfg-row { display: flex; align-items: center; justify-content: space-between; padding: 14px 20px; gap: 16px; border-bottom: 1px solid var(--divider-color); }
  .cfg-row:last-child { border-bottom: none; }
  .cfg-row-label { display: flex; flex-direction: column; gap: 3px; flex: 1; }
  .cfg-row-label > span:first-child { font-size: 0.92em; color: var(--primary-text-color); }
  .cfg-row-hint { font-size: 0.78em; color: var(--secondary-text-color); }
  .cfg-input { width: 90px; padding: 8px 12px; border: 1.5px solid var(--divider-color); border-radius: 8px; background: var(--primary-background-color); color: var(--primary-text-color); font-size: 0.9em; text-align: center; flex-shrink: 0; transition: border-color 0.2s; }
  .cfg-input:focus { outline: none; border-color: var(--primary-color); }
  .cfg-toggle { position: relative; display: inline-block; width: 48px; height: 26px; flex-shrink: 0; cursor: pointer; }
  .cfg-toggle-sm { width: 40px; height: 22px; }
  .cfg-toggle input { opacity: 0; width: 0; height: 0; }
  .cfg-toggle-slider { position: absolute; inset: 0; background: var(--disabled-text-color,#bbb); border-radius: 26px; transition: 0.25s; }
  .cfg-toggle-slider::before { content: ''; position: absolute; height: 20px; width: 20px; left: 3px; bottom: 3px; background: white; border-radius: 50%; transition: 0.25s; box-shadow: 0 1px 4px rgba(0,0,0,0.25); }
  .cfg-toggle-sm .cfg-toggle-slider::before { height: 16px; width: 16px; left: 3px; bottom: 3px; }
  .cfg-toggle input:checked + .cfg-toggle-slider { background: var(--primary-color); }
  .cfg-toggle input:checked + .cfg-toggle-slider::before { transform: translateX(22px); }
  .cfg-toggle-sm input:checked + .cfg-toggle-slider::before { transform: translateX(18px); }
  /* ── Issue type list ── */
  .cfg-categories-root { padding: 0 0 8px; }
  .cfg-cat-section { border-bottom: 1px solid var(--divider-color); }
  .cfg-cat-section:last-child { border-bottom: none; }
  .cfg-cat-section-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 20px; background: rgba(var(--rgb-primary-color,33,150,243),0.04); cursor: pointer; }
  .cfg-cat-header-left { display: flex; align-items: center; gap: 10px; }
  .cfg-cat-section-title { font-weight: 700; font-size: 0.88em; color: var(--primary-text-color); }
  .cfg-cat-count { font-size: 0.78em; color: var(--secondary-text-color); margin-left: 4px; }
  .cfg-cat-header-actions { display: flex; gap: 6px; }
  .cfg-cat-all-btn { font-size: 0.75em; padding: 3px 8px; border: 1px solid var(--divider-color); border-radius: 4px; background: var(--card-background-color); color: var(--secondary-text-color); cursor: pointer; }
  .cfg-cat-all-btn:hover { background: var(--primary-background-color); color: var(--primary-text-color); }
  .cfg-type-list { display: flex; flex-direction: column; }
  .cfg-type-row { display: flex; align-items: center; justify-content: space-between; padding: 9px 20px 9px 32px; gap: 12px; border-bottom: 1px solid var(--divider-color); transition: background 0.15s; cursor: default; }
  .cfg-type-row:last-child { border-bottom: none; }
  .cfg-type-row.disabled { opacity: 0.45; background: rgba(0,0,0,0.015); }
  .cfg-type-row:hover { background: rgba(var(--rgb-primary-color,33,150,243),0.03); }
  .cfg-type-label { font-size: 0.85em; color: var(--primary-text-color); flex: 1; }
  .cfg-badge { font-size: 0.72em; padding: 1px 6px; border-radius: 3px; margin-left: 6px; font-weight: 600; vertical-align: middle; }
  .cfg-badge-fix { background: rgba(34,197,94,0.15); color: #15803d; border: 1px solid rgba(34,197,94,0.4); }
  /* ── Actions ── */
  .cfg-actions { display: flex; gap: 12px; justify-content: flex-end; padding: 8px 0; }
  .cfg-btn { display: inline-flex; align-items: center; gap: 8px; padding: 10px 20px; border-radius: 8px; font-size: 0.9em; font-weight: 600; cursor: pointer; border: none; transition: background 0.2s, transform 0.1s; }
  .cfg-btn:active { transform: scale(0.97); }
  .cfg-btn-primary { background: var(--primary-color); color: white; border-color: transparent; }
  .cfg-btn-primary:hover { background: var(--primary-color); color: white; filter: brightness(1.1); border-color: transparent; }
  .cfg-btn-secondary { background: var(--card-background-color); color: var(--primary-text-color); border: 1.5px solid var(--divider-color); }
  .cfg-btn-secondary:hover { background: var(--primary-color); color: white; border-color: var(--primary-color); }
  .cfg-save-status { padding: 12px 20px; border-radius: 8px; font-size: 0.88em; font-weight: 500; text-align: center; animation: fadeIn 0.2s ease-out; }
  .cfg-save-status.success { background: rgba(34,197,94,0.15); color: #15803d; border: 1px solid rgba(34,197,94,0.3); }
  .cfg-save-status.error { background: rgba(239,68,68,0.12); color: #dc2626; border: 1px solid rgba(239,68,68,0.3); }
`;

// ─── Defaults ─────────────────────────────────────────────────────────────

var DEFAULT_OPTIONS = {
  scan_interval: 60,
  startup_delay_seconds: 60,
  event_monitoring_enabled: true,
  event_debounce_seconds: 30,
  excluded_issue_types: [],
  battery_critical: 5,
  battery_low: 15,
  battery_warning: 25,
  history_retention_days: 365,
  backup_enabled: true,
};

// ─── Collecte des valeurs ─────────────────────────────────────────────────

function collectFormOptions(root) {
  var q = function (sel) { return root.querySelector(sel); };
  var num = function (sel, def) { var el = q(sel); return el ? (parseInt(el.value, 10) || def) : def; };
  var bool = function (sel, def) { var el = q(sel); return el ? el.checked : def; };

  // Types exclus = ceux dont la checkbox est décochée
  var excluded = [];
  var checkboxes = root.querySelectorAll('.cfg-type-toggle');
  for (var i = 0; i < checkboxes.length; i++) {
    if (!checkboxes[i].checked) excluded.push(checkboxes[i].dataset.type);
  }

  return {
    scan_interval: num('#cfg-scan-interval', 60),
    startup_delay_seconds: num('#cfg-startup-delay', 60),
    event_monitoring_enabled: bool('#cfg-event-monitoring', true),
    event_debounce_seconds: num('#cfg-event-debounce', 30),
    excluded_issue_types: excluded,
    battery_critical: num('#cfg-battery-critical', 5),
    battery_low: num('#cfg-battery-low', 15),
    battery_warning: num('#cfg-battery-warning', 25),
    history_retention_days: num('#cfg-history-retention', 365),
    backup_enabled: bool('#cfg-backup-enabled', true),
    debug_mode: bool('#cfg-debug-toggle', false),
  };
}

// ─── Helper : mise à jour des compteurs ──────────────────────────────────

function _updateTypeCounts(el) {
  ISSUE_TYPES_BY_CATEGORY.forEach(function (cat) {
    var list = el.querySelector('#types-' + cat.id);
    if (!list) return;
    var toggles = list.querySelectorAll('.cfg-type-toggle');
    var enabled = 0;
    toggles.forEach(function (cb) { if (cb.checked) enabled++; });
    var countEl = el.querySelector('#count-' + cat.id);
    if (countEl) countEl.textContent = '(' + enabled + '/' + toggles.length + ')';
  });
}
