class HacaPanel extends HTMLElement {
  constructor() {
    super();
    this._translations = {};
    this._language = 'en';
    // English as default fallback
    this._defaultTranslations = {
      title: "H.A.C.A",
      subtitle: "Home Assistant Config Auditor",
      version: "V1.1.1",
      buttons: {
        scan_all: "Full Scan",
        automations: "Automations",
        entities: "Entities",
        security: "Security",
        report: "Report",
        refresh: "Refresh"
      },
      stats: {
        health_score: "Health Score",
        health_score_desc: "Global health score",
        security: "Security",
        security_desc: "Secrets and vulnerabilities",
        automations: "Automations",
        automations_desc: "Automation issues",
        scripts: "Scripts",
        scripts_desc: "Script issues",
        scenes: "Scenes",
        scenes_desc: "Scene issues",
        entities: "Entities",
        entities_desc: "Unavailable/zombie entities",
        performance: "Performance",
        performance_desc: "Loops and DB impact",
        blueprints: "Blueprints",
        blueprints_desc: "Blueprint issues"
      },
      tabs: {
        all: "All",
        automations: "Automations",
        scripts: "Scripts",
        scenes: "Scenes",
        entities: "Entities",
        security: "Security",
        performance: "Performance",
        blueprints: "Blueprints",
        backups: "Backups",
        reports: "Reports"
      },
      sections: {
        all_issues: "All Issues",
        security_issues: "Security Issues",
        automation_issues: "Automation Issues",
        script_issues: "Script Issues",
        scene_issues: "Scene Issues",
        entity_issues: "Entity Issues",
        performance_issues: "Performance Issues",
        blueprint_issues: "Blueprint Issues",
        backup_management: "Backup Management",
        report_management: "Report Management"
      },
      actions: {
        create_backup: "Create Backup",
        fix: "Fix",
        ai_explain: "AI",
        edit_ha: "Edit",
        restore: "Restore",
        view: "View",
        download: "Download",
        fullscreen: "Full Screen",
        close: "Close",
        cancel: "Cancel",
        apply: "Apply",
        delete: "Delete"
      },
      messages: {
        no_issues: "No issues detected in this category",
        no_backups: "No backup available",
        no_reports: "No report generated",
        loading: "Loading...",
        scan_in_progress: "Scan in progress...",
        backup_created: "Backup created",
        backup_restored: "Backup restored. Restart Home Assistant.",
        confirm_backup: "Create a new backup?",
        confirm_restore: "Do you really want to restore this backup?\n⚠️ A backup of the current state will be created before restoration.",
        reports_generated: "Reports generated (MD, JSON, PDF) in /config/.haca_reports/",
        data_refreshed: "Data refreshed",
        ai_analyzing: "AI is analyzing your problem...",
        ai_generating: "AI is generating a description...",
        yaml_updating: "Updating YAML file...",
        no_issues_filtered: "No issues match the selected filter"
      },
      modals: {
        correction_proposal: "Correction Proposal",
        before: "Before (Current)",
        after: "After (Proposal)",
        changes_identified: "Changes identified",
        apply_correction: "Apply Correction",
        correction_applied: "Correction Applied!",
        ai_analysis: "AI Assist Analysis",
        suggest_description: "Suggest a description",
        ai_proposition: "AI proposition:",
        edit_text: "You can edit this text before applying.",
        broken_device_ref: "Broken device reference",
        cannot_auto_fix: "This issue cannot be fixed automatically",
        how_to_fix: "How to fix manually:",
        open_editor: "Open Editor",
        automation: "Automation",
        problem: "Problem"
      },
      notifications: {
        new_issue: "New issue detected",
        new_issues: "new issues detected",
        config_modified: "Configuration modified",
        reported_by: "Reported by H.A.C.A",
        view_details: "View details",
        and_others: "...and {count} other(s)",
        report_generated: "Report Generated",
        report_generated_msg: "MD, JSON and PDF available in /config/.haca_reports/",
        error: "Error",
        backup_created_success: "Backup created successfully",
        backup_restored_success: "Backup restored. Restart Home Assistant."
      },
      tables: {
        name: "Name",
        date: "Date",
        size: "Size",
        action: "Action",
        audit_date: "Audit Date",
        available_formats: "Available Formats"
      },
      backup: {
        loading: "Loading...",
        error_loading: "Error loading backups",
        confirm_create: "Create a new backup?",
        confirm_restore: "Do you really want to restore this backup?\n⚠️ A backup of the current state will be created before restoration."
      },
      reports: {
        loading: "Loading...",
        loading_report: "Loading report...",
        loading_proposal: "Loading proposal...",
        error_loading: "Error loading reports",
        error_display: "Error displaying reports"
      },
      ai: {
        analyzing: "AI is analyzing your problem...",
        generating: "AI is generating a description...",
        searching: "Searching for a relevant phrase for your configuration",
        no_explanation: "Sorry, the AI could not generate an explanation. Check if you have configured OpenAI/Gemini in Home Assistant."
      },
      fix: {
        applying: "Applying fix...",
        success: "Fix Applied Successfully!",
        error_unknown: "Unknown error",
        cannot_find_automation: "Cannot find automation ID"
      },
      instructions: {
        open_yaml_editor: "Open the automation in the YAML editor",
        find_device_ref: "Find the device_id reference",
        replace_entity: "Replace with a valid entity_id",
        save_reload: "Save and reload the automation"
      },
      seconds: "This may take a few seconds",
      filter: {
        all: "All",
        high: "\ud83d\udd34 High",
        medium: "\ud83d\udfe0 Medium",
        low: "\ud83d\udd35 Low",
        label: "Filter:",
        export_csv: "Export CSV"
      }
    };
  }

  // Helper method to get translation
  t(key, params = {}) {
    const keys = key.split('.');
    let value = this._translations;

    for (const k of keys) {
      if (value && typeof value === 'object' && k in value) {
        value = value[k];
      } else {
        // Fallback to default translations
        value = this._defaultTranslations;
        for (const k2 of keys) {
          if (value && typeof value === 'object' && k2 in value) {
            value = value[k2];
          } else {
            return key; // Return key if not found
          }
        }
        break;
      }
    }

    // Replace parameters like {count}
    if (typeof value === 'string') {
      for (const [param, val] of Object.entries(params)) {
        value = value.replace(new RegExp(`\\{${param}\\}`, 'g'), val);
      }
    }

    return value || key;
  }

  set panel(panelInfo) {
    this._panel = panelInfo;

    if (!this._initialized) {
      this._initialized = true;
      // Render first with default translations
      this.render();
      this.attachListeners();

      // Then try to load translations and update
      setTimeout(() => {
        this.loadTranslations().then(() => {
          // Re-render with loaded translations
          this.render();
          this.attachListeners();
          console.log('[HACA] Panel re-rendered with translations');
        });
        console.log('[HACA] Loading initial data...');
        this.updateFromHass();
      }, 100);
    }
  }

  async loadTranslations() {
    if (!this._hass) {
      console.warn('[HACA] hass not available yet for loading translations');
      return;
    }
    try {
      console.log('[HACA] Loading translations...');
      const result = await this._hass.callWS({ type: 'haca/get_translations' });
      console.log('[HACA] Translation result:', result);
      if (result && result.translations) {
        this._translations = result.translations;
        this._language = result.language || 'en';
        console.log('[HACA] Translations loaded for language:', result.language);
        console.log('[HACA] Panel translations:', this._translations);
      }
    } catch (error) {
      console.warn('[HACA] Could not load translations, using defaults:', error);
    }
  }

  set hass(hass) {
    this._hass = hass;
    // Load translations when hass becomes available
    if (this._initialized && !this._translationsLoaded) {
      this._translationsLoaded = true;
      this.loadTranslations().then(() => {
        this.render();
        this.attachListeners();
      });
    }
  }

  get hass() {
    return this._hass;
  }

  render() {
    this.innerHTML = `
      <style>
        :host {
          display: block;
          padding: 16px;
          background: var(--primary-background-color);
          color: var(--primary-text-color);
          font-family: 'Roboto', 'Outfit', sans-serif;
          box-sizing: border-box;
        }
        *, *::before, *::after { box-sizing: inherit; }
        .container { max-width: 1400px; margin: 0 auto; animation: fadeIn 0.5s ease-out; }

        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(10px); }
          to   { opacity: 1; transform: translateY(0); }
        }

        /* ── HEADER ───────────────────────────────── */
        .header {
          background: linear-gradient(135deg, var(--primary-color) 0%, var(--accent-color, #03a9f4) 100%);
          color: white;
          padding: 24px;
          border-radius: 16px;
          margin-bottom: 20px;
          box-shadow: 0 8px 32px rgba(0,0,0,0.15);
          display: flex;
          justify-content: space-between;
          align-items: center;
          flex-wrap: wrap;
          gap: 16px;
        }
        .header-title { display: flex; align-items: center; gap: 14px; flex: 1; min-width: 0; }
        .header-title ha-icon { --mdc-icon-size: 42px; flex-shrink: 0; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3)); }
        .header h1 { margin: 0; font-size: 28px; font-weight: 500; letter-spacing: -0.5px; }
        .header-sub { font-size: 13px; opacity: 0.8; font-weight: 400; }
        .actions { display: flex; gap: 10px; flex-wrap: wrap; }

        /* ── BUTTONS ──────────────────────────────── */
        button {
          background: rgba(255,255,255,0.15);
          color: white;
          border: 1px solid rgba(255,255,255,0.3);
          padding: 10px 18px;
          border-radius: 12px;
          cursor: pointer;
          font-size: 13px;
          font-weight: 500;
          display: flex;
          align-items: center;
          gap: 8px;
          backdrop-filter: blur(8px);
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          white-space: nowrap;
        }
        button:hover { background: rgba(255,255,255,0.25); transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.2); }
        button:active { transform: translateY(0); }
        button:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
        button#scan-all { background: white; color: var(--primary-color); font-weight: 700; border: none; }
        button#scan-all:hover { background: rgba(255,255,255,0.9); }

        .btn-loader {
          width: 14px; height: 14px;
          border: 2px solid transparent; border-top-color: currentColor;
          border-radius: 50%; animation: btn-spin 0.8s linear infinite; display: inline-block;
        }
        @keyframes btn-spin { to { transform: rotate(360deg); } }
        button.scanning { pointer-events: none; }
        button.scanning ha-icon { display: none; }

        /* ── STAT CARDS ───────────────────────────── */
        .stats {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
          gap: 16px;
          margin-bottom: 28px;
        }
        .stat-card {
          background: var(--card-background-color);
          padding: 20px;
          border-radius: 16px;
          box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgba(0,0,0,0.05));
          border: 1px solid var(--divider-color);
          display: flex; flex-direction: column; gap: 8px;
          transition: transform 0.3s ease;
        }
        .stat-card.blueprint { border-left: 5px solid var(--info-color, #26c6da); }
        .stat-card:hover { transform: translateY(-3px); }
        .stat-header { display: flex; justify-content: space-between; align-items: center; }
        .stat-label { color: var(--secondary-text-color); font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.8px; }
        .stat-icon { color: var(--primary-color); opacity: 0.8; }
        .stat-value { font-size: 38px; font-weight: 700; color: var(--primary-text-color); margin-top: 2px; }
        .stat-desc { font-size: 12px; color: var(--secondary-text-color); }

        /* ── TABS ─────────────────────────────────── */
        .tabs-container {
          margin-bottom: 20px;
          position: sticky; top: 0; z-index: 10;
          background: var(--primary-background-color);
          padding: 8px 0;
        }
        .tabs {
          display: flex; gap: 6px;
          background: var(--secondary-background-color);
          padding: 5px; border-radius: 14px;
          overflow-x: auto; scrollbar-width: none;
          -webkit-overflow-scrolling: touch;
        }
        .tabs::-webkit-scrollbar { display: none; }
        .tabs .tab {
          flex-shrink: 0;
          padding: 10px 14px;
          background: transparent; cursor: pointer;
          border-radius: 10px; border: none;
          color: var(--secondary-text-color);
          font-weight: 600; white-space: nowrap;
          display: flex; align-items: center; justify-content: center; gap: 8px;
          transition: all 0.2s ease; font-size: 13px;
        }
        .tabs .tab ha-icon { --mdc-icon-size: 18px; flex-shrink: 0; }
        .tab-label { display: inline; }
        .tabs .tab:hover { color: var(--primary-text-color); background: rgba(0,0,0,0.05); }
        .tabs .tab.active { background: var(--card-background-color); color: var(--primary-color); box-shadow: 0 4px 12px rgba(0,0,0,0.08); }

        /* ── SECTION CARD ─────────────────────────── */
        .tab-content { display: none; animation: fadeIn 0.3s ease-out; }
        .tab-content.active { display: block; }
        .section-card {
          background: var(--card-background-color);
          padding: 0; border-radius: 16px;
          box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgba(0,0,0,0.05));
          border: 1px solid var(--divider-color); overflow: hidden;
        }
        .section-header {
          padding: 18px 22px; border-bottom: 1px solid var(--divider-color);
          display: flex; justify-content: space-between; align-items: center;
          background: var(--secondary-background-color); flex-wrap: wrap; gap: 10px;
        }
        .section-header h2 { margin: 0; font-size: 17px; font-weight: 600; display: flex; align-items: center; gap: 10px; }
        .section-header-btns { display: flex; gap: 10px; flex-wrap: wrap; }

        /* ── ISSUE ITEMS ──────────────────────────── */
        .issue-list { padding: 8px 20px 20px; }
        .issue-item {
          padding: 18px;
          margin: 14px 0;
          background: var(--card-background-color);
          border: 1px solid var(--divider-color);
          border-left: 6px solid var(--primary-color);
          border-radius: 12px;
          transition: all 0.2s ease;
        }
        .issue-item:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
        .issue-item.high   { border-left-color: var(--error-color, #ef5350); background: rgba(239,83,80,0.02); }
        .issue-item.medium { border-left-color: var(--warning-color, #ffa726); background: rgba(255,167,38,0.02); }
        .issue-item.low    { border-left-color: var(--info-color, #26c6da); background: rgba(38,198,218,0.02); }

        /* Issue layout: info left, buttons right — stacks on mobile */
        .issue-main { display: flex; justify-content: space-between; align-items: flex-start; gap: 14px; }
        .issue-info { flex: 1; min-width: 0; }
        .issue-btns { display: flex; gap: 8px; flex-shrink: 0; align-items: flex-start; }
        .issue-header-row { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
        .issue-title { font-size: 15px; font-weight: 600; color: var(--primary-text-color); word-break: break-word; }
        .issue-entity {
          font-size: 12px; color: var(--secondary-text-color);
          font-family: 'SFMono-Regular', Consolas, monospace;
          background: var(--secondary-background-color);
          padding: 2px 6px; border-radius: 4px;
          display: inline-block; max-width: 100%;
          overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        }
        .issue-message { margin: 10px 0 0; line-height: 1.5; color: var(--primary-text-color); opacity: 0.9; font-size: 14px; }
        .issue-reco {
          margin-top: 10px; font-size: 13px; color: var(--secondary-text-color);
          display: flex; align-items: flex-start; gap: 8px;
          background: rgba(0,0,0,0.03); padding: 8px 12px; border-radius: 8px;
        }

        .fix-btn {
          background: var(--primary-color); color: white;
          padding: 8px 14px; font-size: 12px; font-weight: 600;
          border-radius: 10px;
          box-shadow: 0 4px 10px rgba(var(--rgb-primary-color),0.3); border: none;
        }
        .fix-btn:hover { background: var(--accent-color, #03a9f4); color: white !important; opacity: 0.9; }

        /* ── EMPTY STATE ──────────────────────────── */
        .empty-state { text-align: center; padding: 52px 20px; color: var(--secondary-text-color); }
        .empty-state ha-icon { --mdc-icon-size: 60px; opacity: 0.3; margin-bottom: 14px; display: block; }

        /* ── TABLES ───────────────────────────────── */
        .table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
        .data-table { width: 100%; border-collapse: separate; border-spacing: 0; min-width: 480px; }
        .data-table th { padding: 14px 16px; text-align: left; font-size: 12px; text-transform: uppercase; color: var(--secondary-text-color); font-weight: 700; border-bottom: 2px solid var(--divider-color); white-space: nowrap; }
        .data-table td { padding: 14px 16px; border-bottom: 1px solid var(--divider-color); vertical-align: middle; }
        .data-table tr:last-child td { border-bottom: none; }

        /* ── MOBILE CARD LIST (backup/report rows) ── */
        .mobile-cards { display: none; }
        .m-card {
          border: 1px solid var(--divider-color);
          border-radius: 12px; padding: 14px; margin: 10px 16px;
          background: var(--secondary-background-color);
        }
        .m-card-title { font-weight: 600; font-size: 14px; word-break: break-all; display: flex; align-items: flex-start; gap: 8px; margin-bottom: 4px; }
        .m-card-meta { font-size: 12px; color: var(--secondary-text-color); margin-bottom: 10px; }
        .m-card-btns { display: flex; gap: 8px; flex-wrap: wrap; }
        .m-card-btns button { flex: 1; min-width: 100px; justify-content: center; }
        /* Format pills in report cards */
        .fmt-pills { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }
        .fmt-pill { border: 1px solid var(--divider-color); border-radius: 10px; padding: 8px 10px; background: var(--card-background-color); }
        .fmt-pill-label { font-size: 10px; font-weight: 800; color: var(--primary-color); text-transform: uppercase; display: block; margin-bottom: 5px; }
        .fmt-pill-btns { display: flex; gap: 5px; }
        .fmt-pill-btns button { padding: 5px; background: var(--secondary-background-color) !important; border: 1px solid var(--divider-color) !important; border-radius: 7px !important; }

        /* ── FILTER BAR ───────────────────────────── */
        .filter-bar {
          display: flex; align-items: center; gap: 10px;
          padding: 12px 22px; border-bottom: 1px solid var(--divider-color);
          background: var(--secondary-background-color); flex-wrap: wrap;
        }
        .filter-label { font-size: 12px; font-weight: 700; text-transform: uppercase; color: var(--secondary-text-color); letter-spacing: 0.5px; }
        .filter-chips { display: flex; gap: 6px; flex-wrap: wrap; }
        .filter-chip {
          padding: 5px 14px; border-radius: 20px; border: 1px solid var(--divider-color);
          background: var(--card-background-color); color: var(--secondary-text-color);
          font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.2s ease;
        }
        .filter-chip:hover { border-color: var(--primary-color); color: var(--primary-color); transform: none; box-shadow: none; }
        .filter-chip.active-all    { background: var(--primary-color); color: white; border-color: var(--primary-color); }
        .filter-chip.active-high   { background: var(--error-color, #ef5350); color: white; border-color: var(--error-color, #ef5350); }
        .filter-chip.active-medium { background: var(--warning-color, #ffa726); color: white; border-color: var(--warning-color, #ffa726); }
        .filter-chip.active-low    { background: var(--info-color, #26c6da); color: white; border-color: var(--info-color, #26c6da); }
        .export-csv-btn {
          margin-left: auto; padding: 5px 14px; border-radius: 20px;
          border: 1px solid var(--divider-color); background: var(--card-background-color);
          color: var(--secondary-text-color); font-size: 12px; font-weight: 600; cursor: pointer;
          display: flex; align-items: center; gap: 6px; transition: all 0.2s ease;
        }
        .export-csv-btn:hover { border-color: var(--success-color, #4caf50); color: var(--success-color, #4caf50); transform: none; box-shadow: none; }

        /* ── MODAL ────────────────────────────────── */
        .haca-modal-card { border-radius: 20px !important; overflow: hidden !important; border: 1px solid rgba(255,255,255,0.1); }

        /* ── LOADER ───────────────────────────────── */
        .loader {
          width: 48px; height: 48px;
          border: 5px solid rgba(0,0,0,0.08);
          border-bottom-color: var(--primary-color);
          border-radius: 50%; display: inline-block;
          box-sizing: border-box;
          animation: rotation 1s linear infinite; margin: 20px auto;
        }
        @keyframes rotation { 0%{transform:rotate(0deg)} 100%{transform:rotate(360deg)} }

        /* ═══════════════════════════════════════════
           TABLET  ≤ 900px  — hide tab text
           ═══════════════════════════════════════════ */
        @media (max-width: 900px) {
          .tab-label { display: none; }
          .tabs .tab { gap: 0; padding: 10px; }
        }

        /* ═══════════════════════════════════════════
           MOBILE  ≤ 600px
           ═══════════════════════════════════════════ */
        @media (max-width: 600px) {
          :host { padding: 10px; }

          /* Header */
          .header { padding: 14px 16px; border-radius: 12px; gap: 12px; }
          .header-title ha-icon { --mdc-icon-size: 30px; }
          .header h1 { font-size: 20px; }
          .header-sub { display: none; }
          .actions { width: 100%; }
          .actions button { flex: 1; justify-content: center; }

          /* Stats: 2-col grid */
          .stats { grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 18px; }
          .stat-card { padding: 12px; gap: 4px; }
          .stat-value { font-size: 28px; }
          .stat-label { font-size: 10px; }
          .stat-desc { display: none; }

          /* Tabs: icon-only */
          .tab-label { display: none; }
          .tabs .tab { gap: 0; padding: 10px 8px; }
          .tabs .tab ha-icon { --mdc-icon-size: 20px; }
          .tabs { gap: 2px; }
          .tabs-container { padding: 6px 0; }

          /* Issues */
          .issue-list { padding: 6px 10px 16px; }
          .issue-item { padding: 12px; margin: 10px 0; }
          .issue-main { flex-direction: column; gap: 10px; }
          .issue-btns { width: 100%; }
          .issue-btns button { flex: 1; justify-content: center; }
          .issue-title { font-size: 14px; }
          .issue-message { font-size: 13px; }

          /* Section headers */
          .section-header { padding: 12px 14px; }
          .section-header h2 { font-size: 14px; }
          .section-header-btns { width: 100%; }
          .section-header-btns button { flex: 1; justify-content: center; }

          /* Filter bar */
          .filter-bar { padding: 8px 12px; gap: 8px; }
          .export-csv-btn { margin-left: 0; width: 100%; justify-content: center; }

          /* Tables → card view */
          .table-wrap { display: none; }
          .mobile-cards { display: block; }

          /* Modals: bottom-sheet style */
          .haca-modal {
            align-items: flex-end !important;
          }
          .haca-modal > div {
            width: 100% !important;
            max-width: 100% !important;
            max-height: 95vh !important;
            border-radius: 16px 16px 0 0 !important;
          }
        }
      </style>
      
      <div class="container">
        <div class="header">
          <div class="header-title">
            <ha-icon icon="mdi:shield-check-outline"></ha-icon>
            <div>
                <h1>${this.t('title')}</h1>
                <div class="header-sub">${this.t('subtitle')} - ${this.t('version')}</div>
            </div>
          </div>
          <div class="actions">
            <button id="scan-all"><ha-icon icon="mdi:magnify-scan"></ha-icon> ${this.t('buttons.scan_all')}</button>
          </div>
        </div>
        
        <div class="stats">
          <div class="stat-card">
            <div class="stat-header">
                <span class="stat-label">${this.t('stats.health_score')}</span>
                <ha-icon icon="mdi:heart-pulse" class="stat-icon"></ha-icon>
            </div>
            <div class="stat-value" id="health-score">--</div>
            <div class="stat-desc">${this.t('stats.health_score_desc')}</div>
          </div>
          <div class="stat-card" style="border-left: 5px solid var(--error-color, #ef5350);">
            <div class="stat-header">
                <span class="stat-label">${this.t('stats.security')}</span>
                <ha-icon icon="mdi:shield-lock" style="color: var(--error-color, #ef5350);"></ha-icon>
            </div>
            <div class="stat-value" id="security-count">0</div>
            <div class="stat-desc">${this.t('stats.security_desc')}</div>
          </div>
          <div class="stat-card">
            <div class="stat-header">
                <span class="stat-label">${this.t('stats.automations')}</span>
                <ha-icon icon="mdi:robot-confused" class="stat-icon"></ha-icon>
            </div>
            <div class="stat-value" id="auto-count">0</div>
            <div class="stat-desc">${this.t('stats.automations_desc')}</div>
          </div>
          <div class="stat-card">
            <div class="stat-header">
                <span class="stat-label">${this.t('stats.scripts')}</span>
                <ha-icon icon="mdi:script-text" class="stat-icon"></ha-icon>
            </div>
            <div class="stat-value" id="script-count">0</div>
            <div class="stat-desc">${this.t('stats.scripts_desc')}</div>
          </div>
          <div class="stat-card">
            <div class="stat-header">
                <span class="stat-label">${this.t('stats.scenes')}</span>
                <ha-icon icon="mdi:palette" class="stat-icon"></ha-icon>
            </div>
            <div class="stat-value" id="scene-count">0</div>
            <div class="stat-desc">${this.t('stats.scenes_desc')}</div>
          </div>
          <div class="stat-card">
            <div class="stat-header">
                <span class="stat-label">${this.t('stats.entities')}</span>
                <ha-icon icon="mdi:lightning-bolt" class="stat-icon"></ha-icon>
            </div>
            <div class="stat-value" id="entity-count">0</div>
            <div class="stat-desc">${this.t('stats.entities_desc')}</div>
          </div>
          <div class="stat-card">
            <div class="stat-header">
                <span class="stat-label">${this.t('stats.performance')}</span>
                <ha-icon icon="mdi:speedometer-slow" class="stat-icon"></ha-icon>
            </div>
            <div class="stat-value" id="perf-count">0</div>
            <div class="stat-desc">${this.t('stats.performance_desc')}</div>
          </div>
          <div class="stat-card blueprint">
            <div class="stat-header">
                <span class="stat-label">${this.t('stats.blueprints')}</span>
                <ha-icon icon="mdi:file-document-outline" style="color: var(--info-color, #26c6da);"></ha-icon>
            </div>
            <div class="stat-value" id="blueprint-count">0</div>
            <div class="stat-desc">${this.t('stats.blueprints_desc')}</div>
          </div>
        </div>
        
        <div class="tabs-container">
          <div class="tabs">
            <button class="tab active" data-tab="all"><ha-icon icon="mdi:view-list"></ha-icon> <span class="tab-label">${this.t('tabs.all')}</span></button>
            <button class="tab" data-tab="automations"><ha-icon icon="mdi:robot"></ha-icon> <span class="tab-label">${this.t('tabs.automations')}</span></button>
            <button class="tab" data-tab="scripts"><ha-icon icon="mdi:script-text"></ha-icon> <span class="tab-label">${this.t('tabs.scripts')}</span></button>
            <button class="tab" data-tab="scenes"><ha-icon icon="mdi:palette"></ha-icon> <span class="tab-label">${this.t('tabs.scenes')}</span></button>
            <button class="tab" data-tab="entities"><ha-icon icon="mdi:lightning-bolt"></ha-icon> <span class="tab-label">${this.t('tabs.entities')}</span></button>
            <button class="tab" data-tab="security"><ha-icon icon="mdi:shield-lock"></ha-icon> <span class="tab-label">${this.t('tabs.security')}</span></button>
            <button class="tab" data-tab="performance"><ha-icon icon="mdi:gauge"></ha-icon> <span class="tab-label">${this.t('tabs.performance')}</span></button>
            <button class="tab" data-tab="blueprints"><ha-icon icon="mdi:file-document-outline"></ha-icon> <span class="tab-label">${this.t('tabs.blueprints')}</span></button>
            <button class="tab" data-tab="backups"><ha-icon icon="mdi:history"></ha-icon> <span class="tab-label">${this.t('tabs.backups')}</span></button>
            <button class="tab" data-tab="reports"><ha-icon icon="mdi:file-chart"></ha-icon> <span class="tab-label">${this.t('tabs.reports')}</span></button>
          </div>
        </div>
        
        <div class="section-card">
          <div id="tab-all" class="tab-content active">
            <div class="section-header">
                <h2><ha-icon icon="mdi:alert-circle-outline"></ha-icon> ${this.t('sections.all_issues')}</h2>
            </div>
            
          <div class="filter-bar" id="filter-bar-issues-all">
            <span class="filter-label">${this.t('filter.label')}</span>
            <div class="filter-chips">
              <button class="filter-chip active-all" data-filter="all" data-target="issues-all">${this.t('filter.all')}</button>
              <button class="filter-chip" data-filter="high" data-target="issues-all">${this.t('filter.high')}</button>
              <button class="filter-chip" data-filter="medium" data-target="issues-all">${this.t('filter.medium')}</button>
              <button class="filter-chip" data-filter="low" data-target="issues-all">${this.t('filter.low')}</button>
            </div>
            <button class="export-csv-btn" data-target="issues-all"><ha-icon icon="mdi:file-delimited-outline" style="--mdc-icon-size:16px;"></ha-icon> ${this.t('filter.export_csv')}</button>
          </div>
          <div id="issues-all" class="issue-list"></div>
          </div>
          
          <div id="tab-security" class="tab-content">
            <div class="section-header">
                <h2><ha-icon icon="mdi:shield-lock"></ha-icon> ${this.t('sections.security_issues')}</h2>
            </div>
            
          <div class="filter-bar" id="filter-bar-issues-security">
            <span class="filter-label">${this.t('filter.label')}</span>
            <div class="filter-chips">
              <button class="filter-chip active-all" data-filter="all" data-target="issues-security">${this.t('filter.all')}</button>
              <button class="filter-chip" data-filter="high" data-target="issues-security">${this.t('filter.high')}</button>
              <button class="filter-chip" data-filter="medium" data-target="issues-security">${this.t('filter.medium')}</button>
              <button class="filter-chip" data-filter="low" data-target="issues-security">${this.t('filter.low')}</button>
            </div>
            <button class="export-csv-btn" data-target="issues-security"><ha-icon icon="mdi:file-delimited-outline" style="--mdc-icon-size:16px;"></ha-icon> ${this.t('filter.export_csv')}</button>
          </div>
          <div id="issues-security" class="issue-list"></div>
          </div>
          
          <div id="tab-automations" class="tab-content">
            <div class="section-header">
                <h2><ha-icon icon="mdi:robot"></ha-icon> ${this.t('sections.automation_issues')}</h2>
            </div>
            
          <div class="filter-bar" id="filter-bar-issues-automations">
            <span class="filter-label">${this.t('filter.label')}</span>
            <div class="filter-chips">
              <button class="filter-chip active-all" data-filter="all" data-target="issues-automations">${this.t('filter.all')}</button>
              <button class="filter-chip" data-filter="high" data-target="issues-automations">${this.t('filter.high')}</button>
              <button class="filter-chip" data-filter="medium" data-target="issues-automations">${this.t('filter.medium')}</button>
              <button class="filter-chip" data-filter="low" data-target="issues-automations">${this.t('filter.low')}</button>
            </div>
            <button class="export-csv-btn" data-target="issues-automations"><ha-icon icon="mdi:file-delimited-outline" style="--mdc-icon-size:16px;"></ha-icon> ${this.t('filter.export_csv')}</button>
          </div>
          <div id="issues-automations" class="issue-list"></div>
          </div>
          
          <div id="tab-scripts" class="tab-content">
            <div class="section-header">
                <h2><ha-icon icon="mdi:script-text"></ha-icon> ${this.t('sections.script_issues')}</h2>
            </div>
            
          <div class="filter-bar" id="filter-bar-issues-scripts">
            <span class="filter-label">${this.t('filter.label')}</span>
            <div class="filter-chips">
              <button class="filter-chip active-all" data-filter="all" data-target="issues-scripts">${this.t('filter.all')}</button>
              <button class="filter-chip" data-filter="high" data-target="issues-scripts">${this.t('filter.high')}</button>
              <button class="filter-chip" data-filter="medium" data-target="issues-scripts">${this.t('filter.medium')}</button>
              <button class="filter-chip" data-filter="low" data-target="issues-scripts">${this.t('filter.low')}</button>
            </div>
            <button class="export-csv-btn" data-target="issues-scripts"><ha-icon icon="mdi:file-delimited-outline" style="--mdc-icon-size:16px;"></ha-icon> ${this.t('filter.export_csv')}</button>
          </div>
          <div id="issues-scripts" class="issue-list"></div>
          </div>
          
          <div id="tab-scenes" class="tab-content">
            <div class="section-header">
                <h2><ha-icon icon="mdi:palette"></ha-icon> ${this.t('sections.scene_issues')}</h2>
            </div>
            
          <div class="filter-bar" id="filter-bar-issues-scenes">
            <span class="filter-label">${this.t('filter.label')}</span>
            <div class="filter-chips">
              <button class="filter-chip active-all" data-filter="all" data-target="issues-scenes">${this.t('filter.all')}</button>
              <button class="filter-chip" data-filter="high" data-target="issues-scenes">${this.t('filter.high')}</button>
              <button class="filter-chip" data-filter="medium" data-target="issues-scenes">${this.t('filter.medium')}</button>
              <button class="filter-chip" data-filter="low" data-target="issues-scenes">${this.t('filter.low')}</button>
            </div>
            <button class="export-csv-btn" data-target="issues-scenes"><ha-icon icon="mdi:file-delimited-outline" style="--mdc-icon-size:16px;"></ha-icon> ${this.t('filter.export_csv')}</button>
          </div>
          <div id="issues-scenes" class="issue-list"></div>
          </div>
          
          <div id="tab-entities" class="tab-content">
            <div class="section-header">
                <h2><ha-icon icon="mdi:lightning-bolt"></ha-icon> ${this.t('sections.entity_issues')}</h2>
            </div>
            
          <div class="filter-bar" id="filter-bar-issues-entities">
            <span class="filter-label">${this.t('filter.label')}</span>
            <div class="filter-chips">
              <button class="filter-chip active-all" data-filter="all" data-target="issues-entities">${this.t('filter.all')}</button>
              <button class="filter-chip" data-filter="high" data-target="issues-entities">${this.t('filter.high')}</button>
              <button class="filter-chip" data-filter="medium" data-target="issues-entities">${this.t('filter.medium')}</button>
              <button class="filter-chip" data-filter="low" data-target="issues-entities">${this.t('filter.low')}</button>
            </div>
            <button class="export-csv-btn" data-target="issues-entities"><ha-icon icon="mdi:file-delimited-outline" style="--mdc-icon-size:16px;"></ha-icon> ${this.t('filter.export_csv')}</button>
          </div>
          <div id="issues-entities" class="issue-list"></div>
          </div>
          
          <div id="tab-performance" class="tab-content">
            <div class="section-header">
                <h2><ha-icon icon="mdi:gauge"></ha-icon> ${this.t('sections.performance_issues')}</h2>
            </div>
            
          <div class="filter-bar" id="filter-bar-issues-performance">
            <span class="filter-label">${this.t('filter.label')}</span>
            <div class="filter-chips">
              <button class="filter-chip active-all" data-filter="all" data-target="issues-performance">${this.t('filter.all')}</button>
              <button class="filter-chip" data-filter="high" data-target="issues-performance">${this.t('filter.high')}</button>
              <button class="filter-chip" data-filter="medium" data-target="issues-performance">${this.t('filter.medium')}</button>
              <button class="filter-chip" data-filter="low" data-target="issues-performance">${this.t('filter.low')}</button>
            </div>
            <button class="export-csv-btn" data-target="issues-performance"><ha-icon icon="mdi:file-delimited-outline" style="--mdc-icon-size:16px;"></ha-icon> ${this.t('filter.export_csv')}</button>
          </div>
          <div id="issues-performance" class="issue-list"></div>
          </div>
          
          <div id="tab-blueprints" class="tab-content">
            <div class="section-header">
                <h2><ha-icon icon="mdi:file-document-outline"></ha-icon> ${this.t('sections.blueprint_issues')}</h2>
            </div>
            
          <div class="filter-bar" id="filter-bar-issues-blueprints">
            <span class="filter-label">${this.t('filter.label')}</span>
            <div class="filter-chips">
              <button class="filter-chip active-all" data-filter="all" data-target="issues-blueprints">${this.t('filter.all')}</button>
              <button class="filter-chip" data-filter="high" data-target="issues-blueprints">${this.t('filter.high')}</button>
              <button class="filter-chip" data-filter="medium" data-target="issues-blueprints">${this.t('filter.medium')}</button>
              <button class="filter-chip" data-filter="low" data-target="issues-blueprints">${this.t('filter.low')}</button>
            </div>
            <button class="export-csv-btn" data-target="issues-blueprints"><ha-icon icon="mdi:file-delimited-outline" style="--mdc-icon-size:16px;"></ha-icon> ${this.t('filter.export_csv')}</button>
          </div>
          <div id="issues-blueprints" class="issue-list"></div>
          </div>
          
          <div id="tab-backups" class="tab-content">
            <div class="section-header">
                <h2><ha-icon icon="mdi:history"></ha-icon> ${this.t('sections.backup_management')}</h2>
                <div class="section-header-btns"><button id="create-backup" style="background: var(--primary-color);"><ha-icon icon="mdi:plus"></ha-icon> ${this.t('actions.create_backup')}</button></div>
            </div>
            <div id="backups-list" style="padding: 0;">${this.t('messages.loading')}</div>
          </div>
          
          <div id="tab-reports" class="tab-content">
            <div class="section-header">
                <h2><ha-icon icon="mdi:file-chart"></ha-icon> ${this.t('sections.report_management')}</h2>
                <div class="section-header-btns">
                  <button id="create-report" style="background: var(--success-color, #4caf50); color: white;"><ha-icon icon="mdi:file-document-plus"></ha-icon> ${this.t('buttons.report')}</button>
                  <button id="refresh-reports" style="background: var(--primary-color); color: white;"><ha-icon icon="mdi:refresh"></ha-icon> ${this.t('buttons.refresh')}</button>
                </div>
            </div>
            <div id="reports-list" style="padding: 0;">${this.t('messages.loading')}</div>
          </div>
        </div>
      </div>
    `;
  }

  attachListeners() {
    this.querySelector('#scan-all').addEventListener('click', () => this.scanAll());

    // Backup listeners
    this.querySelector('#create-backup').addEventListener('click', () => this.createBackup());

    // Report listeners
    this.querySelector('#create-report')?.addEventListener('click', () => this.generateReport());

    // Gestion des onglets
    this.querySelectorAll('.tabs .tab').forEach(tab => {
      tab.addEventListener('click', () => {
        const tabName = tab.dataset.tab;
        this.switchTab(tabName);
        if (tabName === 'backups') {
          this.loadBackups();
        } else if (tabName === 'reports') {
          this.loadReports();
        }
      });
    });

    this.querySelector('#refresh-reports')?.addEventListener('click', () => this.loadReports());

    // Subscribe to new issues event from backend
    this._subscribeToNewIssues();

    // Severity filter chips
    this.querySelectorAll('.filter-chip').forEach(chip => {
      chip.addEventListener('click', (e) => {
        const btn = e.currentTarget;
        const filter = btn.dataset.filter;
        const targetId = btn.dataset.target;
        // Update active chip style in this filter bar
        const bar = this.querySelector(`#filter-bar-${targetId}`);
        if (bar) {
          bar.querySelectorAll('.filter-chip').forEach(c => {
            c.className = 'filter-chip'; // reset
          });
          btn.classList.add(`active-${filter}`);
        }
        // Re-render with filter
        const container = this.querySelector(`#${targetId}`);
        const allIssues = container?._allIssues || [];
        this.renderIssues(allIssues, targetId, filter);
      });
    });

    // CSV export buttons
    this.querySelectorAll('.export-csv-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const targetId = e.currentTarget.dataset.target;
        const container = this.querySelector(`#${targetId}`);
        const issues = container?._allIssues || [];
        this.exportCSV(issues, targetId);
      });
    });
  }

  _subscribeToNewIssues() {
    // Subscribe to HACA new issues event
    if (this.hass && this.hass.connection) {
      this.hass.connection.subscribeEvents((event) => {
        console.log('[HACA] New issues detected event:', event);
        if (event.event_type === 'haca_new_issues_detected') {
          const data = event.data || {};
          this.showNewIssuesNotification(data);
        }
      }, 'haca_new_issues_detected');
    }
  }

  // Show Home Assistant persistent notification
  async showHANotification(title, message, notificationId = 'haca_notification') {
    try {
      await this.hass.callService('persistent_notification', 'create', {
        title: title,
        message: message,
        notification_id: notificationId
      });
    } catch (error) {
      console.error('[HACA] Error creating notification:', error);
    }
  }

  showNewIssuesNotification(data) {
    const count = data.count || 0;
    const issues = data.issues || [];

    if (count === 0) return;

    // Use Home Assistant persistent notification
    const title = count === 1 ? this.t('notifications.new_issue') : `${count} ${this.t('notifications.new_issues')}`;
    let message = this.t('notifications.config_modified') + '\n\n';

    if (issues.length > 0) {
      for (let i = 0; i < Math.min(issues.length, 3); i++) {
        const issue = issues[i];
        message += `• **${issue.alias || issue.entity_id}** - ${issue.type || 'Issue'}\n`;
      }
      if (issues.length > 3) {
        message += this.t('notifications.and_others', { count: issues.length - 3 });
      }
    }

    message += `\n\n${this.t('notifications.reported_by')}`;

    this.showHANotification(title, message, 'haca_new_issues');

    // Also update the UI
    this.updateFromHass();
  }

  async loadBackups() {
    const container = this.querySelector('#backups-list');
    container.innerHTML = this.t('backup.loading');
    try {
      const result = await this.hass.callWS({
        type: 'call_service',
        domain: 'config_auditor',
        service: 'list_backups',
        service_data: {},
        return_response: true
      });

      console.log('[HACA] Backups result:', result);

      // Handle potential response wrapping (some HA versions wrap in 'response')
      let data = result;
      if (result && result.response) {
        data = result.response;
      }

      const backups = data.backups || data || [];

      // Safety check if backups is not an array
      if (!Array.isArray(backups)) {
        console.error('[HACA] Invalid backups data format:', backups);
        throw new Error(this.t('backup.error_loading'));
      }

      this.renderBackups(backups);

    } catch (error) {
      console.error('[HACA] Error loading backups:', error);
      container.innerHTML = `<div class="empty-state">❌ ${this.t('notifications.error')}: ${error.message}</div>`;
    }
  }

  renderBackups(backups) {
    const container = this.querySelector('#backups-list');
    if (backups.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
            <ha-icon icon="mdi:archive-off-outline"></ha-icon>
            <p>${this.t('messages.no_backups')}</p>
        </div>`;
      return;
    }

    container.innerHTML = `
      <div class="table-wrap">
        <table class="data-table">
          <thead><tr>
            <th>${this.t('tables.name')}</th>
            <th>${this.t('tables.date')}</th>
            <th>${this.t('tables.size')}</th>
            <th>${this.t('tables.action')}</th>
          </tr></thead>
          <tbody>
            ${backups.map(b => `
              <tr>
                <td style="font-weight:500;">
                  <div style="display:flex;align-items:center;gap:10px;">
                    <ha-icon icon="mdi:zip-box-outline" style="color:var(--secondary-text-color);flex-shrink:0;"></ha-icon>
                    <span style="word-break:break-all;">${this.escapeHtml(b.name)}</span>
                  </div>
                </td>
                <td style="white-space:nowrap;">${new Date(b.created).toLocaleString()}</td>
                <td><span style="background:var(--secondary-background-color);padding:4px 8px;border-radius:6px;font-size:12px;white-space:nowrap;">${Math.round(b.size / 1024)} KB</span></td>
                <td>
                  <div style="display:flex;gap:8px;">
                    <button class="restore-btn" data-path="${b.path}" style="background:var(--warning-color,#ff9800);color:black;">
                      <ha-icon icon="mdi:backup-restore"></ha-icon> ${this.t('actions.restore')}
                    </button>
                    <button class="delete-backup-btn" data-path="${b.path}" data-name="${b.name}" style="background:var(--error-color,#ef5350);color:white;">
                      <ha-icon icon="mdi:delete-outline"></ha-icon>
                    </button>
                  </div>
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
      <div class="mobile-cards">
        ${backups.map(b => `
          <div class="m-card">
            <div class="m-card-title">
              <ha-icon icon="mdi:zip-box-outline" style="color:var(--secondary-text-color);flex-shrink:0;margin-top:1px;"></ha-icon>
              ${this.escapeHtml(b.name)}
            </div>
            <div class="m-card-meta">📅 ${new Date(b.created).toLocaleString()} · ${Math.round(b.size / 1024)} KB</div>
            <div class="m-card-btns">
              <button class="restore-btn" data-path="${b.path}" style="background:var(--warning-color,#ff9800);color:black;">
                <ha-icon icon="mdi:backup-restore"></ha-icon> ${this.t('actions.restore')}
              </button>
              <button class="delete-backup-btn" data-path="${b.path}" data-name="${b.name}" style="background:var(--error-color,#ef5350);color:white;">
                <ha-icon icon="mdi:delete-outline"></ha-icon> ${this.t('actions.delete')}
              </button>
            </div>
          </div>
        `).join('')}
      </div>
    `;

    container.querySelectorAll('.restore-btn').forEach(btn => {
      btn.addEventListener('click', (e) => this.restoreBackup(e.currentTarget.dataset.path));
    });

    container.querySelectorAll('.delete-backup-btn').forEach(btn => {
      btn.addEventListener('click', (e) => this.deleteBackup(e.currentTarget.dataset.path, e.currentTarget.dataset.name));
    });
  }

  async createBackup() {
    if (!confirm(this.t('backup.confirm_create'))) return;
    try {
      const result = await this.hass.callWS({
        type: 'call_service',
        domain: 'config_auditor',
        service: 'create_backup',
        service_data: {},
        return_response: true
      });

      this.showHANotification(this.t('notifications.report_generated'), this.t('notifications.backup_created_success'), 'haca_backup');
      this.loadBackups();
    } catch (error) {
      this.showHANotification(this.t('notifications.error'), error.message, 'haca_error');
    }
  }

  async restoreBackup(path) {
    if (!confirm(this.t('backup.confirm_restore'))) return;
    try {
      await this.hass.callService('config_auditor', 'restore_backup', { backup_path: path });
      this.showHANotification(this.t('notifications.report_generated'), this.t('notifications.backup_restored_success'), 'haca_restore');
    } catch (error) {
      this.showHANotification(this.t('notifications.error'), error.message, 'haca_error');
    }
  }

  async deleteBackup(path, name) {
    if (!confirm(this.t('backup.confirm_delete') + '\n\n' + name)) return;

    try {
      const result = await this.hass.callWS({
        type: 'call_service',
        domain: 'config_auditor',
        service: 'delete_backup',
        service_data: { backup_path: path },
        return_response: true
      });

      const response = result.response || result;

      if (response.success) {
        this.showHANotification(
          this.t('notifications.backup_deleted'),
          response.message || `${response.deleted_file}`,
          'haca_backup_deleted'
        );
        // Refresh the backups list
        this.loadBackups();
      } else {
        this.showHANotification(
          this.t('notifications.error'),
          response.error || this.t('fix.error_unknown'),
          'haca_error'
        );
      }
    } catch (error) {
      this.showHANotification(
        this.t('notifications.error'),
        error.message,
        'haca_error'
      );
    }
  }

  switchTab(tabName) {
    // Activer l'onglet
    this.querySelectorAll('.tabs .tab').forEach(t => t.classList.remove('active'));
    this.querySelector(`.tabs .tab[data-tab="${tabName}"]`).classList.add('active');

    // Afficher le contenu
    this.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    this.querySelector(`#tab-${tabName}`).classList.add('active');
  }

  async loadData() {
    try {
      console.log('[HACA] Loading data...');
      const result = await this.hass.callWS({ type: 'haca/get_data' });
      console.log('[HACA] Data received:', result);
      this.updateUI(result);
    } catch (error) {
      console.error('[HACA] Error loading data:', error);
      this.querySelector('#issues-list').innerHTML = `<div class="empty-state">❌ ${error.message}</div>`;
    }
  }

  updateUI(data) {
    console.log('[HACA] updateUI called with:', data);

    const safeSetText = (id, val) => {
      const el = this.querySelector(`#${id}`);
      if (el) el.textContent = val;
    };

    safeSetText('health-score', (data.health_score || 0) + '%');
    safeSetText('auto-count', data.automation_issues || 0);
    safeSetText('script-count', data.script_issues || 0);
    safeSetText('scene-count', data.scene_issues || 0);
    safeSetText('entity-count', data.entity_issues || 0);
    safeSetText('perf-count', data.performance_issues || 0);
    safeSetText('security-count', data.security_issues || 0);
    safeSetText('blueprint-count', data.blueprint_issues || 0);

    const autoIssues = data.automation_issue_list || [];
    const scriptIssues = data.script_issue_list || [];
    const sceneIssues = data.scene_issue_list || [];
    const entityIssues = data.entity_issue_list || [];
    const perfIssues = data.performance_issue_list || [];
    const securityIssues = data.security_issue_list || [];
    const blueprintIssues = data.blueprint_issue_list || [];
    const allIssues = [...autoIssues, ...scriptIssues, ...sceneIssues, ...entityIssues, ...perfIssues, ...securityIssues, ...blueprintIssues];

    console.log('[HACA] Automations:', autoIssues.length, 'Scripts:', scriptIssues.length, 'Scenes:', sceneIssues.length, 'Entities:', entityIssues.length, 'Performance:', perfIssues.length, 'Security:', securityIssues.length, 'Blueprints:', blueprintIssues.length);

    // Afficher dans chaque section
    this.renderIssues(allIssues, 'issues-all');
    this.renderIssues(autoIssues, 'issues-automations');
    this.renderIssues(scriptIssues, 'issues-scripts');
    this.renderIssues(sceneIssues, 'issues-scenes');
    this.renderIssues(entityIssues, 'issues-entities');
    this.renderIssues(perfIssues, 'issues-performance');
    this.renderIssues(securityIssues, 'issues-security');
    this.renderIssues(blueprintIssues, 'issues-blueprints');
  }

  // Helper method to get Home Assistant edit URL for an entity
  getHAEditUrl(entityId) {
    if (!entityId) return null;

    const entityIdParts = entityId.split('.');
    const entityType = entityIdParts[0];

    // Get the item ID from state attributes
    const state = this.hass?.states?.[entityId];
    const itemId = state?.attributes?.id;

    // Map entity types to their edit URLs
    if (entityType === 'automation' && itemId) {
      return `/config/automation/edit/${itemId}`;
    } else if (entityType === 'script' && itemId) {
      return `/config/script/edit/${itemId}`;
    } else if (entityType === 'scene' && itemId) {
      return `/config/scene/edit/${itemId}`;
    } else if (entityType === 'automation') {
      // Fallback: try to use entity_id without the prefix
      return `/config/automation/edit/${entityIdParts[1]}`;
    } else if (entityType === 'script') {
      return `/config/script/edit/${entityIdParts[1]}`;
    } else if (entityType === 'scene') {
      return `/config/scene/edit/${entityIdParts[1]}`;
    }

    return null;
  }

  renderIssues(issues, containerId, severityFilter) {
    const container = this.querySelector(`#${containerId}`);
    if (!container) return;

    // Store full list on container for filtering/export
    if (!severityFilter) {
      container._allIssues = issues;
    }

    const filtered = severityFilter && severityFilter !== 'all'
      ? issues.filter(i => i.severity === severityFilter)
      : issues;

    if (filtered.length === 0) {
      const msg = (severityFilter && severityFilter !== 'all')
        ? this.t('messages.no_issues_filtered')
        : this.t('messages.no_issues');
      container.innerHTML = `
        <div class="empty-state">
            <ha-icon icon="mdi:check-decagram-outline"></ha-icon>
            <p>${msg}</p>
        </div>`;
      return;
    }

    container.innerHTML = filtered.map(i => {
      const isFixable = ['device_id_in_trigger', 'device_id_in_action', 'device_id_in_target', 'device_trigger_platform', 'device_id_in_condition', 'device_condition_platform', 'incorrect_mode_motion_single', 'template_simple_state', 'no_description', 'no_alias', 'broken_device_reference'].includes(i.type) || i.fix_available;
      const icon = i.severity === 'high' ? 'mdi:alert-decagram' : (i.severity === 'medium' ? 'mdi:alert' : 'mdi:information');
      const isSecurity = i.type.includes('security') || i.type.includes('secret') || i.type === 'sensitive_data_exposure';

      // Get edit URL for Home Assistant
      const editUrl = this.getHAEditUrl(i.entity_id);

      return `
      <div class="issue-item ${i.severity}" style="${isSecurity ? 'border-left-color: var(--error-color, #ef5350);' : ''}">
        <div class="issue-main">
            <div class="issue-info">
                <div class="issue-header-row">
                    <ha-icon icon="${isSecurity ? 'mdi:shield-alert' : icon}" style="--mdc-icon-size: 17px; flex-shrink:0; ${isSecurity ? 'color: var(--error-color, #ef5350);' : ''}"></ha-icon>
                    <div class="issue-title">${this.escapeHtml(i.alias || i.entity_id || '')}</div>
                </div>
                <div class="issue-entity">${this.escapeHtml(i.entity_id || '')}</div>
            </div>
            <div class="issue-btns">
                ${editUrl ? `<a href="${editUrl}" target="_blank" style="text-decoration: none;"><button class="edit-ha-btn" style="background: var(--secondary-background-color); color: var(--primary-text-color); border: 1px solid var(--divider-color);"><ha-icon icon="mdi:pencil"></ha-icon> ${this.t('actions.edit_ha')}</button></a>` : ''}
                <button class="explain-btn" data-issue='${JSON.stringify(i).replace(/'/g, "'")}' style="background: var(--accent-color, #03a9f4); color: white;">
                    <ha-icon icon="mdi:robot"></ha-icon> IA
                </button>
                ${isFixable ? `<button class="fix-btn" data-issue='${JSON.stringify(i).replace(/'/g, "'")}'><ha-icon icon="mdi:magic-staff"></ha-icon> ${this.t('actions.fix')}</button>` : ''}
            </div>
        </div>
        <div class="issue-message">${this.escapeHtml(i.message || '')}</div>
        ${i.recommendation ? `
            <div class="issue-reco">
                <ha-icon icon="mdi:lightbulb-outline" style="--mdc-icon-size: 16px; flex-shrink:0; margin-top:1px;"></ha-icon>
                <span>${this.escapeHtml(i.recommendation)}</span>
            </div>
        ` : ''}
      </div>
    `}).join('');

    container.querySelectorAll('.fix-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const issue = JSON.parse(e.currentTarget.dataset.issue);
        this.showFixPreview(issue);
      });
    });

    container.querySelectorAll('.explain-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const issue = JSON.parse(e.currentTarget.dataset.issue);
        this.explainWithAI(issue);
      });
    });
  }

  async explainWithAI(issue) {
    const card = this.createModal(`
        <div style="padding: 40px; text-align: center; display: flex; flex-direction: column; align-items: center;">
            <div class="loader"></div>
            <div style="margin-top: 20px; font-size: 18px; font-weight: 500; color: var(--primary-text-color);">🤖 ${this.t('ai.analyzing')}</div>
            <div style="margin-top: 8px; font-size: 14px; color: var(--secondary-text-color);">${this.t('seconds')}</div>
        </div>
    `);

    try {
      const response = await this.hass.callWS({
        type: 'call_service',
        domain: 'config_auditor',
        service: 'explain_issue_ai',
        service_data: { issue: issue },
        return_response: true
      });

      console.log('[HACA] AI Explanation result:', response);
      let explanation = this.t('ai.no_explanation');

      if (response && response.response && response.response.explanation) {
        explanation = response.response.explanation;
      } else if (response && response.explanation) {
        explanation = response.explanation;
      }

      card._updateContent(`
        <div style="padding: 24px;">
            <div style="display: flex; align-items: center; gap: 16px; margin-bottom: 24px; border-bottom: 1px solid var(--divider-color); padding-bottom: 16px;">
                <ha-icon icon="mdi:robot" style="--mdc-icon-size: 48px; color: var(--primary-color);"></ha-icon>
                <div>
                    <h2 style="margin: 0;">${this.t('modals.ai_analysis')}</h2>
                    <div style="font-size: 14px; opacity: 0.7;">${issue.alias || issue.entity_id}</div>
                </div>
            </div>
            
            <div style="background: var(--secondary-background-color); padding: 20px; border-radius: 12px; line-height: 1.6; font-size: 15px; color: var(--primary-text-color); white-space: pre-wrap; max-height: 400px; overflow-y: auto;">${explanation}</div>
            
            <div style="margin-top: 24px; display: flex; justify-content: flex-end;">
                <button class="close-btn" style="background: var(--primary-color); color: white;">${this.t('actions.close')}</button>
            </div>
        </div>
      `);

      card.querySelector('.close-btn').addEventListener('click', () => {
        if (card._closeModal) card._closeModal();
        else card.parentElement.remove();
      });

    } catch (error) {
      card._updateContent(`<div style="padding: 24px; color: var(--error-color);">❌ ${this.t('notifications.error')}: ${error.message}</div>`);
      setTimeout(() => card.parentElement.remove(), 4000);
    }
  }

  async showFixPreview(issue) {
    // Handle description/alias issues with AI suggestion
    if (['no_description', 'no_alias'].includes(issue.type)) {
      this.fixDescriptionAI(issue);
      return;
    }

    // Handle broken device reference - cannot be auto-fixed, show explanation
    if (issue.type === 'broken_device_reference') {
      // Determine edit URL based on entity type and ID
      let editUrl = '';
      const entityId = issue.entity_id || '';
      const entityIdParts = entityId.split('.');
      const entityType = entityIdParts[0];

      // Get the automation/script/scene ID from state attributes
      const state = this.hass.states[entityId];
      const itemId = state?.attributes?.id;

      if (entityType === 'automation' && itemId) {
        editUrl = `/config/automation/edit/${itemId}`;
      } else if (entityType === 'script' && itemId) {
        editUrl = `/config/script/edit/${itemId}`;
      } else if (entityType === 'scene' && itemId) {
        editUrl = `/config/scene/edit/${itemId}`;
      }

      const card = this.createModal(`
        <div style="padding: 24px;">
            <div style="display: flex; align-items: center; gap: 16px; margin-bottom: 24px; border-bottom: 1px solid var(--divider-color); padding-bottom: 16px;">
                <ha-icon icon="mdi:alert-circle" style="--mdc-icon-size: 48px; color: var(--error-color);"></ha-icon>
                <div>
                    <h2 style="margin: 0;">${this.t('modals.broken_device_ref')}</h2>
                    <div style="font-size: 14px; opacity: 0.7;">${issue.entity_id}</div>
                </div>
            </div>
            
            <div style="background: rgba(239, 83, 80, 0.1); padding: 20px; border-radius: 12px; border-left: 4px solid var(--error-color); margin-bottom: 20px;">
                <div style="font-weight: 600; margin-bottom: 8px; color: var(--error-color);">⚠️ ${this.t('modals.cannot_auto_fix')}</div>
                <div style="line-height: 1.6;">${issue.message}</div>
            </div>
            
            <div style="background: var(--secondary-background-color); padding: 20px; border-radius: 12px; margin-bottom: 20px;">
                <div style="font-weight: 600; margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">
                    <ha-icon icon="mdi:lightbulb-outline" style="color: var(--primary-color);"></ha-icon>
                    ${this.t('modals.how_to_fix')}
                </div>
                <ol style="margin: 0; padding-left: 20px; line-height: 1.8;">
                    <li>${this.t('instructions.open_yaml_editor')}</li>
                    <li>${this.t('instructions.find_device_ref')}: <code style="background: rgba(0,0,0,0.1); padding: 2px 6px; border-radius: 4px;">${issue.device_id || 'device_id inconnu'}</code></li>
                    <li>${this.t('instructions.replace_entity')}</li>
                    <li>${this.t('instructions.save_reload')}</li>
                </ol>
            </div>
            
            <div style="margin-top: 24px; display: flex; justify-content: flex-end; gap: 12px;">
                <button class="close-btn" style="background: var(--secondary-background-color); color: var(--primary-text-color); border: 1px solid var(--divider-color);">${this.t('actions.close')}</button>
                ${editUrl ? `<a href="${editUrl}" target="_blank" style="text-decoration: none;"><button class="edit-btn" style="background: var(--primary-color); color: white;"><ha-icon icon="mdi:pencil"></ha-icon> ${this.t('modals.open_editor')}</button></a>` : ''}
            </div>
        </div>
      `);
      card.querySelector('.close-btn').addEventListener('click', () => card.parentElement.remove());
      return;
    }

    // Determine service payload based on issue type
    let service = '';
    let serviceData = {};

    if (['device_id_in_trigger', 'device_id_in_action', 'device_id_in_target', 'device_trigger_platform', 'device_id_in_condition', 'device_condition_platform'].includes(issue.type)) {
      service = 'preview_device_id';

      // Extract automation_id from entity_id
      // Try multiple strategies to find the automation ID
      let automation_id = null;

      // Strategy 1: Get from state attributes
      const state = this.hass.states[issue.entity_id];
      if (state && state.attributes.id) {
        automation_id = state.attributes.id;
      }

      // Strategy 2: Extract from entity_id (automation.xxx -> xxx)
      if (!automation_id && issue.entity_id && issue.entity_id.startsWith('automation.')) {
        const entity_name = issue.entity_id.replace('automation.', '');
        // Try to find automation by alias that matches the entity name
        automation_id = entity_name;
      }

      // Strategy 3: Use the entity_id itself as fallback
      if (!automation_id) {
        automation_id = issue.entity_id;
      }

      if (automation_id) {
        serviceData = { automation_id: automation_id };
      } else {
        console.warn("Could not find automation ID for", issue.entity_id);
        this.showHANotification(this.t('fix.cannot_find_automation'), issue.entity_id || '', 'haca_error');
        return;
      }

    } else if (issue.type === 'incorrect_mode_motion_single') {
      service = 'preview_mode';
      const state = this.hass.states[issue.entity_id];
      if (state && state.attributes.id) {
        serviceData = { automation_id: state.attributes.id, mode: 'restart' };
      } else {
        this.showHANotification(this.t('fix.cannot_find_automation'), issue.entity_id || '', 'haca_error');
        return;
      }
    } else if (issue.type === 'template_simple_state') {
      service = 'preview_template';
      const state = this.hass.states[issue.entity_id];
      if (state && state.attributes.id) {
        serviceData = { automation_id: state.attributes.id };
      } else {
        this.showHANotification(this.t('fix.cannot_find_automation'), issue.entity_id || '', 'haca_error');
        return;
      }
    }

    // Show loading modal
    const modal = this.createModal(this.t('reports.loading_proposal'));

    try {
      const result = await this.hass.callWS({
        type: 'call_service',
        domain: 'config_auditor',
        service: service,
        service_data: serviceData,
        return_response: true
      });

      const response = result.response || result;

      if (response.success) {
        this.renderDiffModal(modal, response, issue, service, serviceData);
      } else {
        modal._updateContent(`<div style="padding:20px;color:red">${this.t('notifications.error')}: ${response.error || this.t('fix.error_unknown')}</div>`);
        setTimeout(() => modal._closeModal && modal._closeModal(), 3000);
      }
    } catch (e) {
      modal._updateContent(`<div style="padding:20px;color:red">${this.t('notifications.error')}: ${e.message}</div>`);
      setTimeout(() => modal._closeModal && modal._closeModal(), 3000);
    }
  }

  createModal(content) {
    const existing = this.querySelector('.haca-modal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.className = 'haca-modal';
    const _isMobile = window.innerWidth <= 600;
    modal.style.cssText = `
        position: fixed; top: 0; left: 0; right: 0; bottom: 0;
        background: rgba(0,0,0,0.8); z-index: 9999;
        display: flex; justify-content: center; align-items: ${_isMobile ? 'flex-end' : 'center'};
      `;

    const card = document.createElement('div');
    card.className = 'haca-modal-card';
    const _mobile = window.innerWidth <= 600;
    card.style.cssText = _mobile
      ? `background: var(--card-background-color); width: 100%; max-width: 100%;
         max-height: 95vh; overflow: auto; border-radius: 16px 16px 0 0; padding: 0;
         box-shadow: 0 -4px 24px rgba(0,0,0,0.3); display: flex; flex-direction: column; position: relative;`
      : `background: var(--card-background-color); width: 92%; max-width: 1000px;
         max-height: 90vh; overflow: auto; border-radius: 16px; padding: 0;
         box-shadow: 0 4px 20px rgba(0,0,0,0.5); display: flex; flex-direction: column; position: relative;`;

    // Add close button absolutely positioned in top right of modal card
    const closeBtn = document.createElement('button');
    closeBtn.className = 'modal-close-btn';
    closeBtn.innerHTML = '<ha-icon icon="mdi:close"></ha-icon>';
    closeBtn.style.cssText = `
        position: absolute;
        top: 14px;
        right: 9px;
        width: 20px;
        height: 20px;
        border-radius: 50%;
        border: none;
        background: var(--secondary-background-color);
        color: #333;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all 0.2s ease;
        box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        z-index: 100;
        flex-shrink: 0;
      `;

    // Function to close modal
    const closeModal = () => {
      modal.remove();
    };

    closeBtn.addEventListener('click', closeModal);
    closeBtn.addEventListener('mouseenter', () => {
      closeBtn.style.background = 'var(--error-color, #ef5350)';
      closeBtn.style.color = 'white';
    });
    closeBtn.addEventListener('mouseleave', () => {
      closeBtn.style.background = 'var(--secondary-background-color)';
      closeBtn.style.color = 'black';
    });

    card.appendChild(closeBtn);

    const contentWrapper = document.createElement('div');
    contentWrapper.className = 'modal-content-wrapper';
    contentWrapper.innerHTML = typeof content === 'string' ? content : '';
    if (typeof content !== 'string') contentWrapper.appendChild(content);
    card.appendChild(contentWrapper);

    modal.appendChild(card);
    this.appendChild(modal);

    // Close on background click
    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeModal();
    });

    // Close on Escape key
    const handleEscape = (e) => {
      if (e.key === 'Escape') {
        closeModal();
        document.removeEventListener('keydown', handleEscape);
      }
    };
    document.addEventListener('keydown', handleEscape);

    // Store reference to closeModal function and closeBtn on the card
    card._closeModal = closeModal;
    card._closeBtn = closeBtn;

    // Helper method to update content while preserving close button
    card._updateContent = (html) => {
      contentWrapper.innerHTML = html;
    };

    return card;
  }

  async fixDescriptionAI(issue) {
    const card = this.createModal(`
        <div style="padding: 40px; text-align: center; display: flex; flex-direction: column; align-items: center;">
            <div class="loader"></div>
            <div style="margin-top: 20px; font-size: 18px; font-weight: 500; color: var(--primary-text-color);">🤖 ${this.t('ai.generating')}</div>
            <div style="margin-top: 8px; font-size: 14px; color: var(--secondary-text-color);">${this.t('ai.searching')}</div>
        </div>
    `);

    try {
      const result = await this.hass.callWS({
        type: 'call_service',
        domain: 'config_auditor',
        service: 'suggest_description_ai',
        service_data: { entity_id: issue.entity_id || issue.alias },
        return_response: true
      });

      const response = result.response || result;
      if (!response.success) throw new Error(response.error || this.t('ai.no_explanation'));

      card._updateContent(`
            <div style="padding: 24px;">
                <div style="display: flex; align-items: center; gap: 16px; margin-bottom: 24px; border-bottom: 1px solid var(--divider-color); padding-bottom: 16px;">
                    <ha-icon icon="mdi:robot-confused-outline" style="--mdc-icon-size: 40px; color: var(--primary-color);"></ha-icon>
                    <div>
                        <h2 style="margin: 0;">${this.t('modals.suggest_description')}</h2>
                        <div style="font-size: 14px; opacity: 0.7;">${issue.alias || issue.entity_id}</div>
                    </div>
                </div>

                <div style="color: var(--primary-text-color); margin-bottom: 12px; font-weight: 500;">${this.t('modals.ai_proposition')}</div>
                <textarea id="desc-input" style="width: 100%; height: 100px; padding: 12px; border-radius: 8px; border: 1px solid var(--divider-color); background: var(--secondary-background-color); color: var(--primary-text-color); font-family: inherit; font-size: 14px; box-sizing: border-box; resize: none; margin-bottom: 4px;">${response.suggestion}</textarea>
                <div style="font-size: 12px; color: var(--secondary-text-color); margin-bottom: 20px;">${this.t('modals.edit_text')}</div>
                
                <div style="margin-top: 24px; display: flex; justify-content: flex-end; gap: 12px;">
                    <button class="close-btn" style="background: var(--secondary-background-color); color: var(--primary-text-color); border: 1px solid var(--divider-color);">${this.t('actions.cancel')}</button>
                    <button class="apply-btn" style="background: var(--primary-color); color: white;">${this.t('actions.apply')}</button>
                </div>
            </div>
        `);

      card.querySelector('.close-btn').addEventListener('click', () => card.parentElement.remove());
      card.querySelector('.apply-btn').addEventListener('click', async () => {
        const desc = card.querySelector('#desc-input').value;
        card._updateContent(`
                <div style="padding: 40px; text-align: center;">
                    <div class="loader"></div>
                    <p style="margin-top: 20px;">${this.t('messages.yaml_updating')}</p>
                </div>`);

        try {
          await this.hass.callService('config_auditor', 'fix_description', {
            entity_id: issue.entity_id || issue.alias,
            description: desc
          });

          // Trigger a new scan so the issue disappears from the list
          await this.hass.callService('config_auditor', 'scan_automations');

          // Wait for backend processing and sensor updates
          setTimeout(() => {
            this.updateFromHass();
            card.parentElement.remove();
          }, 1500);

        } catch (err) {
          this.showHANotification(
            '❌ ' + this.t('notifications.error'),
            err.message,
            'haca_error'
          );
          if (card._closeModal) card._closeModal();
          else card.parentElement?.remove();
        }
      });

    } catch (e) {
      card._updateContent(`
            <div style="padding: 24px;">
                <h2 style="color: var(--error-color);">❌ ${this.t('notifications.error')}</h2>
                <p>${e.message}</p>
                <div style="margin-top: 24px; display: flex; justify-content: flex-end;">
                    <button class="close-btn" style="background: var(--primary-color);">${this.t('actions.close')}</button>
                </div>
            </div>
        `);
      card.querySelector('.close-btn').addEventListener('click', () => card.parentElement.remove());
    }
  }

  renderDiffModal(card, result, issue, previewService, serviceData) {
    card._updateContent(`
        <div class="section-header" style="background: var(--secondary-background-color); border-bottom: 1px solid var(--divider-color); padding: 20px 24px;">
            <h2 style="margin:0; font-size: 20px; display: flex; align-items: center; gap: 12px;">
                <ha-icon icon="mdi:magic-staff"></ha-icon> ${this.t('modals.correction_proposal')}
            </h2>
            <button style="background: var(--secondary-background-color); color: var(--primary-text-color); border: 1px solid var(--divider-color);" onclick="this.closest('.haca-modal').remove()">${this.t('actions.close')}</button>
        </div>
        <div style="padding: 24px; flex: 1; overflow: auto;">
            <div style="margin-bottom: 24px; background: rgba(var(--rgb-primary-color), 0.05); padding: 16px; border-radius: 12px; border-left: 4px solid var(--primary-color);">
                <div style="margin-bottom: 8px; display: flex; align-items: center; gap: 8px;">
                    <ha-icon icon="mdi:robot" style="--mdc-icon-size: 18px; color: var(--primary-color);"></ha-icon>
                    <strong>${this.t('modals.automation')}:</strong> <span style="font-weight: 500;">${result.alias}</span> (${result.automation_id})
                </div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <ha-icon icon="mdi:alert-circle-outline" style="--mdc-icon-size: 18px; color: var(--error-color);"></ha-icon>
                    <strong>${this.t('modals.problem')}:</strong> ${issue.message}
                </div>
            </div>
            
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-bottom: 24px;">
                <div>
                    <h3 style="margin-top:0; color: var(--error-color); font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px; display: flex; align-items: center; gap: 8px;">
                        <ha-icon icon="mdi:minus-box-outline"></ha-icon> ${this.t('modals.before')}
                    </h3>
                    <pre style="background: var(--secondary-background-color); padding: 16px; overflow: auto; border-radius: 12px; font-size: 12px; border: 1px solid var(--divider-color); max-height: 400px;">${this.escapeHtml(result.current_yaml)}</pre>
                </div>
                <div>
                    <h3 style="margin-top:0; color: var(--success-color, #4caf50); font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px; display: flex; align-items: center; gap: 8px;">
                        <ha-icon icon="mdi:plus-box-outline"></ha-icon> ${this.t('modals.after')}
                    </h3>
                    <pre style="background: var(--secondary-background-color); padding: 16px; overflow: auto; border-radius: 12px; font-size: 12px; border: 1px solid var(--divider-color); max-height: 400px; outline: 1px solid var(--success-color, #4caf50); outline-offset: -1px;">${this.highlightDiff(result.new_yaml, result.current_yaml)}</pre>
                </div>
            </div>
            
            <div style="background: var(--secondary-background-color); padding: 20px; border-radius: 12px; border: 1px solid var(--divider-color);">
                <div style="font-weight: 700; margin-bottom: 12px; display: flex; align-items: center; gap: 10px;">
                    <ha-icon icon="mdi:playlist-check"></ha-icon>
                    ${this.t('modals.changes_identified')} (${result.changes_count}):
                </div>
                <ul style="margin: 0; padding-left: 24px; line-height: 1.6; color: var(--primary-text-color);">
                    ${result.changes.map(c => `<li style="margin-bottom: 4px;">${c.description}</li>`).join('')}
                </ul>
            </div>
        </div>
        <div style="padding: 20px 24px; border-top: 1px solid var(--divider-color); text-align: right; display: flex; justify-content: flex-end; gap: 16px; background: var(--secondary-background-color);">
            <button style="background: var(--secondary-background-color); color: var(--primary-text-color); border: 1px solid var(--divider-color);" onclick="this.closest('.haca-modal').remove()"><ha-icon icon="mdi:close"></ha-icon> ${this.t('actions.cancel')}</button>
            <button id="apply-fix-btn" style="background: var(--primary-color); color: white; padding: 12px 24px; border-radius: 12px; box-shadow: 0 4px 10px rgba(var(--rgb-primary-color), 0.3);">
                <ha-icon icon="mdi:check-circle-outline"></ha-icon> ${this.t('modals.apply_correction')}
            </button>
        </div>
      `);

    card.querySelector('#apply-fix-btn').addEventListener('click', () => {
      this.applyFix(issue, previewService, serviceData, card);
    });
  }

  async applyFix(issue, previewService, serviceData, card) {
    const btn = card.querySelector('#apply-fix-btn');
    btn.disabled = true;
    btn.innerHTML = `<span class="btn-loader"></span> ${this.t('fix.applying')}`;

    // Determine apply service based on preview service
    let applyService = '';
    if (previewService === 'preview_device_id') applyService = 'fix_device_id';
    else if (previewService === 'preview_mode') applyService = 'fix_mode';
    else if (previewService === 'preview_template') applyService = 'fix_template';


    try {
      const result = await this.hass.callWS({
        type: 'call_service',
        domain: 'config_auditor',
        service: applyService,
        service_data: serviceData,
        return_response: true
      });

      const response = result.response || result;

      if (response.success) {
        card._updateContent(`
                <div style="padding: 48px 32px; text-align: center; animation: fadeIn 0.4s ease-out;">
                    <div style="font-size: 64px; margin-bottom: 24px; filter: drop-shadow(0 4px 12px rgba(76, 175, 80, 0.4));">✅</div>
                    <h2 style="font-size: 24px; font-weight: 700; margin-bottom: 12px; color: var(--primary-text-color);">${this.t('fix.success')}</h2>
                    <p style="color: var(--secondary-text-color); margin-bottom: 24px; line-height: 1.6;">${response.message}</p>
                    ${response.backup_path ? `
                        <div style="background: var(--secondary-background-color); padding: 12px; border-radius: 12px; margin-bottom: 32px; display: inline-flex; align-items: center; gap: 10px; border: 1px solid var(--divider-color);">
                            <ha-icon icon="mdi:zip-box-outline" style="color: var(--primary-color);"></ha-icon>
                            <span style="font-family: monospace; font-size: 12px;">${this.t('backup.backup_created')}: ${response.backup_path.split(/[\\/]/).pop()}</span>
                        </div>
                    ` : ''}
                    <div>
                        <button style="background: var(--primary-color); color: white; padding: 12px 32px; font-weight: 600;" onclick="this.closest('.haca-modal').remove()">${this.t('actions.close')}</button>
                    </div>
                </div>
              `);

        // Refresh data
        setTimeout(() => this.scanAutomations(), 1000);
      } else {
        this.showHANotification('❌ ' + this.t('notifications.error'), response.error || this.t('fix.error_unknown'), 'haca_error');
        btn.disabled = false;
        btn.innerHTML = `<ha-icon icon="mdi:check-circle-outline"></ha-icon> ${this.t('modals.apply_correction')}`;
      }
    } catch (e) {
      this.showHANotification('❌ ' + this.t('notifications.error'), e.message, 'haca_error');
      btn.disabled = false;
      btn.innerHTML = `<ha-icon icon="mdi:check-circle-outline"></ha-icon> ${this.t('modals.apply_correction')}`;
    }
  }

  escapeHtml(text) {
    if (!text) return '';
    return text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  highlightDiff(newText, oldText) {
    // Real line-by-line diff implementation
    const oldLines = oldText.split('\n');
    const newLines = newText.split('\n');

    // Build LCS (Longest Common Subsequence) matrix
    const lcs = this._buildLCSMatrix(oldLines, newLines);

    // Generate diff output
    const diffLines = [];
    this._generateDiffLines(oldLines, newLines, lcs, oldLines.length, newLines.length, diffLines);

    // Format diff with colors
    return diffLines.map(line => {
      const escapedLine = this.escapeHtml(line.text);
      if (line.type === 'added') {
        return `<div style="background: rgba(76, 175, 80, 0.15); border-left: 3px solid #4caf50; padding-left: 8px; margin-left: -3px;"><span style="color: #4caf50; font-weight: bold;">+</span> ${escapedLine}</div>`;
      } else if (line.type === 'removed') {
        return `<div style="background: rgba(244, 67, 54, 0.15); border-left: 3px solid #f44336; padding-left: 8px; margin-left: -3px;"><span style="color: #f44336; font-weight: bold;">-</span> ${escapedLine}</div>`;
      } else {
        return `<div style="padding-left: 11px;"><span style="color: var(--secondary-text-color);"> </span> ${escapedLine}</div>`;
      }
    }).join('');
  }

  // Build LCS matrix for diff algorithm
  _buildLCSMatrix(oldLines, newLines) {
    const m = oldLines.length;
    const n = newLines.length;
    const dp = Array(m + 1).fill(null).map(() => Array(n + 1).fill(0));

    for (let i = 1; i <= m; i++) {
      for (let j = 1; j <= n; j++) {
        if (oldLines[i - 1] === newLines[j - 1]) {
          dp[i][j] = dp[i - 1][j - 1] + 1;
        } else {
          dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
        }
      }
    }

    return dp;
  }

  // Generate diff lines by backtracking through LCS matrix
  _generateDiffLines(oldLines, newLines, lcs, i, j, result) {
    if (i > 0 && j > 0 && oldLines[i - 1] === newLines[j - 1]) {
      this._generateDiffLines(oldLines, newLines, lcs, i - 1, j - 1, result);
      result.push({ type: 'unchanged', text: oldLines[i - 1] });
    } else if (j > 0 && (i === 0 || lcs[i][j - 1] >= lcs[i - 1][j])) {
      this._generateDiffLines(oldLines, newLines, lcs, i, j - 1, result);
      result.push({ type: 'added', text: newLines[j - 1] });
    } else if (i > 0 && (j === 0 || lcs[i][j - 1] < lcs[i - 1][j])) {
      this._generateDiffLines(oldLines, newLines, lcs, i - 1, j, result);
      result.push({ type: 'removed', text: oldLines[i - 1] });
    }
  }

  updateFromHass() {
    // Issue lists are no longer stored in sensor attributes (would exceed HA's 16384 bytes limit).
    // All data (counts + full issue lists) is fetched via the WebSocket API haca/get_data.
    if (!this._hass) return;
    console.log('[HACA] updateFromHass: fetching data via WebSocket...');
    this.loadData();
  }

  // Helper method to show loader on a button
  _setButtonLoading(btn, loading, originalContent) {
    if (!btn) return;

    if (loading) {
      btn.classList.add('scanning');
      btn.disabled = true;
      btn.innerHTML = `<span class="btn-loader"></span> ${this.t('messages.scan_in_progress')}`;
    } else {
      btn.classList.remove('scanning');
      btn.disabled = false;
      btn.innerHTML = originalContent;
    }
  }

  async scanAll() {
    if (this._scanAllInProgress) return;
    this._scanAllInProgress = true;
    const btn = this.querySelector('#scan-all');
    const originalContent = `<ha-icon icon="mdi:magnify-scan"></ha-icon> ${this.t('buttons.scan_all')}`;
    this._setButtonLoading(btn, true, originalContent);
    try {
      await this.hass.callService('config_auditor', 'scan_all');
      setTimeout(() => {
        this.updateFromHass();
        this._scanAllInProgress = false;
        this._setButtonLoading(btn, false, originalContent);
      }, 3000);
    } catch (error) {
      console.error('[HACA] Scan error:', error);
      this.showHANotification('❌ ' + this.t('notifications.error'), error.message, 'haca_error');
      this._scanAllInProgress = false;
      this._setButtonLoading(btn, false, originalContent);
    }
  }

  async scanAutomations() {
    if (this._scanAutoInProgress) return;
    this._scanAutoInProgress = true;
    const btn = this.querySelector('#scan-auto');
    const originalContent = `<ha-icon icon="mdi:robot"></ha-icon> ${this.t('buttons.automations')}`;
    this._setButtonLoading(btn, true, originalContent);
    try {
      await this.hass.callService('config_auditor', 'scan_automations');
      setTimeout(() => {
        this.updateFromHass();
        this._scanAutoInProgress = false;
        this._setButtonLoading(btn, false, originalContent);
      }, 3000);
    } catch (error) {
      this.showHANotification('❌ ' + this.t('notifications.error'), error.message, 'haca_error');
      this._scanAutoInProgress = false;
      this._setButtonLoading(btn, false, originalContent);
    }
  }

  async scanEntities() {
    if (this._scanEntityInProgress) return;
    this._scanEntityInProgress = true;
    const btn = this.querySelector('#scan-entity');
    const originalContent = `<ha-icon icon="mdi:lightning-bolt"></ha-icon> ${this.t('buttons.entities')}`;
    this._setButtonLoading(btn, true, originalContent);
    try {
      await this.hass.callService('config_auditor', 'scan_entities');
      setTimeout(() => {
        this.updateFromHass();
        this._scanEntityInProgress = false;
        this._setButtonLoading(btn, false, originalContent);
      }, 3000);
    } catch (error) {
      this.showHANotification('❌ ' + this.t('notifications.error'), error.message, 'haca_error');
      this._scanEntityInProgress = false;
      this._setButtonLoading(btn, false, originalContent);
    }
  }

  showToastNotification(options = {}) {
    const {
      title = 'Notification',
      message = '',
      icon = 'mdi:information',
      iconColor = 'var(--primary-color, #03a9f4)',
      iconBg = 'linear-gradient(135deg, var(--primary-color, #03a9f4) 0%, #0288d1 100%)',
      autoDismiss = 5000,
      actionButton = null
    } = options;

    // Add animation keyframes if not exists
    if (!document.querySelector('#haca-toast-styles')) {
      const style = document.createElement('style');
      style.id = 'haca-toast-styles';
      style.textContent = `
        @keyframes slideInRight {
          from { transform: translateX(100%); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
        @keyframes slideOutRight {
          from { transform: translateX(0); opacity: 1; }
          to { transform: translateX(100%); opacity: 0; }
        }
      `;
      document.head.appendChild(style);
    }

    const toast = document.createElement('div');
    toast.className = 'haca-toast';
    toast.style.cssText = `
      position: fixed;
      bottom: 24px;
      right: 24px;
      background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
      color: white;
      padding: 20px 24px;
      border-radius: 16px;
      box-shadow: 0 12px 40px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.1);
      z-index: 10000;
      display: flex;
      flex-direction: column;
      gap: 12px;
      animation: slideInRight 0.3s ease-out;
      max-width: 420px;
      min-width: 320px;
    `;

    toast.innerHTML = `
      <div style="display: flex; align-items: center; gap: 12px;">
        <div style="background: ${iconBg}; padding: 10px; border-radius: 12px; box-shadow: 0 4px 12px rgba(3, 169, 244, 0.3);">
          <ha-icon icon="${icon}" style="--mdc-icon-size: 24px; color: ${iconColor};"></ha-icon>
        </div>
        <div style="flex: 1;">
          <div style="font-weight: 700; font-size: 16px;">${title}</div>
          <div style="font-size: 12px; opacity: 0.7;">${message}</div>
        </div>
        <button class="close-toast" style="background: rgba(255,255,255,0.1); border: none; color: white; padding: 6px; border-radius: 8px; cursor: pointer;">
          <ha-icon icon="mdi:close" style="--mdc-icon-size: 18px;"></ha-icon>
        </button>
      </div>
      ${actionButton ? `
        <div style="display: flex; align-items: center; justify-content: space-between; padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.1);">
          <div style="font-size: 11px; opacity: 0.6; display: flex; align-items: center; gap: 4px;">
            <ha-icon icon="mdi:shield-check-outline" style="--mdc-icon-size: 14px;"></ha-icon>
            ${this.t('notifications.reported_by')}
          </div>
          ${actionButton}
        </div>
      ` : `
        <div style="font-size: 11px; opacity: 0.6; display: flex; align-items: center; gap: 4px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.1);">
          <ha-icon icon="mdi:shield-check-outline" style="--mdc-icon-size: 14px;"></ha-icon>
          ${this.t('notifications.reported_by')}
        </div>
      `}
    `;

    document.body.appendChild(toast);

    // Close button
    toast.querySelector('.close-toast').addEventListener('click', () => {
      toast.style.animation = 'slideOutRight 0.3s ease-out forwards';
      setTimeout(() => toast.remove(), 300);
    });

    // Auto-dismiss
    setTimeout(() => {
      if (toast.parentElement) {
        toast.style.animation = 'slideOutRight 0.3s ease-out forwards';
        setTimeout(() => toast.remove(), 300);
      }
    }, autoDismiss);

    return toast;
  }

  async generateReport() {
    try {
      await this.hass.callService('config_auditor', 'generate_report');

      // Use Home Assistant persistent notification system with enhanced message
      this.showHANotification(
        this.t('notifications.report_generated'),
        this.t('notifications.report_generated_full'),
        'haca_report_generated'
      );

      if (this.querySelector('.tab[data-tab="reports"]').classList.contains('active')) {
        this.loadReports();
      }
    } catch (error) {
      this.showHANotification(
        this.t('notifications.error'),
        error.message,
        'haca_error'
      );
    }
  }

  async loadReports() {
    const container = this.querySelector('#reports-list');
    container.innerHTML = this.t('reports.loading');
    try {
      const result = await this.hass.callWS({
        type: 'call_service',
        domain: 'config_auditor',
        service: 'list_reports',
        service_data: {},
        return_response: true
      });

      let data = result.response || result;
      let rawReports = data.reports || [];

      // Fallback grouping (if backend hasn't been restarted/updated yet)
      // If the first item has 'format' instead of 'formats', it's the old format
      if (rawReports.length > 0 && rawReports[0].format && !rawReports[0].formats) {
        console.log('[HACA] Backend returned old format, grouping in frontend...');
        const sessions = {};
        const pattern = /report_(\d{8}_\d{6})/;

        rawReports.forEach(r => {
          const match = r.name.match(pattern);
          if (!match) return;
          const sessionId = match[1];
          if (!sessions[sessionId]) {
            sessions[sessionId] = {
              session_id: sessionId,
              created: r.created,
              formats: {}
            };
          }
          sessions[sessionId].formats[r.format] = {
            name: r.name,
            size: r.size
          };
        });
        rawReports = Object.values(sessions).sort((a, b) => b.session_id.localeCompare(a.session_id));
      }

      this.renderReports(rawReports);
    } catch (error) {
      container.innerHTML = `<div class="empty-state">❌ ${this.t('notifications.error')}: ${error.message}</div>`;
    }
  }

  renderReports(reports) {
    console.log('[HACA] renderReports called with:', reports);
    const container = this.querySelector('#reports-list');

    if (!reports || !Array.isArray(reports) || reports.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
            <ha-icon icon="mdi:file-search-outline"></ha-icon>
            <p>${this.t('messages.no_reports')}</p>
        </div>`;
      return;
    }

    try {
      container.innerHTML = `
        <!-- Desktop table -->
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr>
              <th>${this.t('tables.audit_date')}</th>
              <th>${this.t('tables.available_formats')}</th>
              <th style="width:80px;">${this.t('tables.action')}</th>
            </tr></thead>
            <tbody>
              ${reports.filter(s => s && s.formats).map(s => `
                <tr>
                  <td>
                    <div style="display:flex;align-items:center;gap:12px;">
                      <div style="background:var(--primary-color);color:white;width:36px;height:36px;border-radius:10px;display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                        <ha-icon icon="mdi:calendar-check"></ha-icon>
                      </div>
                      <div>
                        <div style="font-weight:600;font-size:14px;white-space:nowrap;">${new Date(s.created).toLocaleString()}</div>
                        <div style="font-size:11px;color:var(--secondary-text-color);font-family:monospace;">ID: ${s.session_id}</div>
                      </div>
                    </div>
                  </td>
                  <td>
                    <div style="display:flex;gap:10px;flex-wrap:wrap;">
                      ${Object.entries(s.formats).map(([ext, info]) => `
                        <div style="display:flex;flex-direction:column;align-items:center;gap:5px;padding:8px;border:1px solid var(--divider-color);border-radius:10px;background:var(--secondary-background-color);flex-shrink:0;">
                          <span style="font-size:10px;font-weight:800;color:var(--primary-color);">${ext.toUpperCase()}</span>
                          <div style="display:flex;gap:5px;">
                            <button class="view-report-btn" data-name="${info.name}" title="${this.t('actions.view')}" style="padding:5px;background:white;color:var(--primary-color);border:1px solid var(--divider-color);border-radius:7px;">
                              <ha-icon icon="mdi:eye-outline" style="--mdc-icon-size:16px;"></ha-icon>
                            </button>
                            <button class="dl-report-btn" data-name="${info.name}" title="${this.t('actions.download')}" style="padding:5px;background:white;color:var(--success-color,#4caf50);border:1px solid var(--divider-color);border-radius:7px;">
                              <ha-icon icon="mdi:download-outline" style="--mdc-icon-size:16px;"></ha-icon>
                            </button>
                          </div>
                          <span style="font-size:10px;color:var(--secondary-text-color);">${Math.round(info.size / 1024)} KB</span>
                        </div>
                      `).join('')}
                    </div>
                  </td>
                  <td>
                    <button class="delete-report-btn" data-session="${s.session_id}" style="padding:8px;background:var(--error-color,#ef5350);color:white;border:none;border-radius:8px;">
                      <ha-icon icon="mdi:delete-outline" style="--mdc-icon-size:18px;"></ha-icon>
                    </button>
                  </td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
        <!-- Mobile cards -->
        <div class="mobile-cards">
          ${reports.filter(s => s && s.formats).map(s => `
            <div class="m-card">
              <div class="m-card-title">
                <ha-icon icon="mdi:calendar-check" style="color:var(--primary-color);flex-shrink:0;margin-top:1px;"></ha-icon>
                ${new Date(s.created).toLocaleString()}
              </div>
              <div class="m-card-meta">ID: ${s.session_id}</div>
              <div class="fmt-pills">
                ${Object.entries(s.formats).map(([ext, info]) => `
                  <div class="fmt-pill">
                    <span class="fmt-pill-label">${ext.toUpperCase()} · ${Math.round(info.size / 1024)} KB</span>
                    <div class="fmt-pill-btns">
                      <button class="view-report-btn" data-name="${info.name}" style="color:var(--primary-color);">
                        <ha-icon icon="mdi:eye-outline" style="--mdc-icon-size:16px;"></ha-icon>
                      </button>
                      <button class="dl-report-btn" data-name="${info.name}" style="color:var(--success-color,#4caf50);">
                        <ha-icon icon="mdi:download-outline" style="--mdc-icon-size:16px;"></ha-icon>
                      </button>
                    </div>
                  </div>
                `).join('')}
              </div>
              <div class="m-card-btns">
                <button class="delete-report-btn" data-session="${s.session_id}" style="background:var(--error-color,#ef5350);color:white;">
                  <ha-icon icon="mdi:delete-outline"></ha-icon> ${this.t('actions.delete')}
                </button>
              </div>
            </div>
          `).join('')}
        </div>
      `;

      container.querySelectorAll('.view-report-btn').forEach(btn => {
        btn.addEventListener('click', (e) => this.viewReport(e.currentTarget.dataset.name));
      });
      container.querySelectorAll('.dl-report-btn').forEach(btn => {
        btn.addEventListener('click', (e) => this.downloadReport(e.currentTarget.dataset.name));
      });
      container.querySelectorAll('.delete-report-btn').forEach(btn => {
        btn.addEventListener('click', (e) => this.deleteReport(e.currentTarget.dataset.session));
      });
    } catch (err) {
      console.error('[HACA] Error rendering reports:', err);
      container.innerHTML = `<div class="empty-state">❌ ${this.t('reports.error_display')}: ${err.message}</div>`;
    }
  }

  async viewReport(name) {
    if (name.endsWith('.pdf')) {
      const card = this.createModal('');
      // Enlarge modal for PDF to almost full screen
      card.style.width = '95%';
      card.style.height = '95%';
      card.style.maxWidth = '1600px';
      card.style.maxHeight = '95vh';

      card._updateContent(`
          <div style="padding: 16px 70px 16px 20px; border-bottom: 1px solid var(--divider-color); display: flex; justify-content: space-between; align-items: center; background: var(--secondary-background-color); gap: 12px; flex-wrap: wrap;">
              <h2 style="margin:0; font-size: 16px; display: flex; align-items: center; gap: 10px; min-width: 0; flex: 1;">
                <ha-icon icon="mdi:file-pdf-box" style="color: var(--error-color); flex-shrink: 0;"></ha-icon>
                <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${name}</span>
              </h2>
              <div style="display: flex; gap: 8px; flex-shrink: 0;">
                <a href="/haca_reports/${name}" target="_blank" style="text-decoration: none;">
                  <button style="background: var(--primary-color); color: white; padding: 8px 12px; font-size: 12px;">
                    <ha-icon icon="mdi:fullscreen"></ha-icon> ${this.t('actions.fullscreen')}
                  </button>
                </a>
              </div>
          </div>
          <div style="flex: 1; height: 100%; background: #525659;">
              <iframe src="/haca_reports/${name}" style="width: 100%; height: 85vh; border: none;"></iframe>
          </div>
      `);
      return;
    }

    const card = this.createModal(this.t('reports.loading_report'));
    try {
      const result = await this.hass.callWS({
        type: 'call_service',
        domain: 'config_auditor',
        service: 'get_report_content',
        service_data: { filename: name },
        return_response: true
      });

      const data = result.response || result;
      if (data.success) {
        card._updateContent(`
            <div style="padding: 16px 60px 16px 16px; border-bottom: 1px solid var(--divider-color); display: flex; justify-content: space-between; align-items: center;">
                <h2 style="margin:0">${name}</h2>
            </div>
            <div style="padding: 16px; flex: 1; max-height: 60vh; overflow-y: auto; background: var(--secondary-background-color); font-family: monospace; white-space: pre-wrap; font-size: 13px;">
                ${data.type === 'json' ? JSON.stringify(data.content, null, 2) : data.content}
            </div>
        `);
      } else {
        card._updateContent(`<div style="padding:20px;color:red">${this.t('notifications.error')}: ${data.error}</div>`);
      }
    } catch (e) {
      card._updateContent(`<div style="padding:20px;color:red">${this.t('notifications.error')}: ${e.message}</div>`);
    }
  }

  async downloadReport(name) {
    const a = document.createElement('a');
    a.href = `/haca_reports/${name}`;
    a.download = name;
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      document.body.removeChild(a);
    }, 100);
  }

  async deleteReport(sessionId) {
    if (!confirm(this.t('report.confirm_delete') + '\n\nID: ' + sessionId)) return;

    try {
      const result = await this.hass.callWS({
        type: 'call_service',
        domain: 'config_auditor',
        service: 'delete_report',
        service_data: { session_id: sessionId },
        return_response: true
      });

      const response = result.response || result;

      if (response.success) {
        this.showHANotification(
          this.t('notifications.report_deleted'),
          `${response.deleted_count} ${this.t('notifications.files_deleted')}`,
          'haca_report_deleted'
        );
        // Refresh the reports list
        this.loadReports();
      } else {
        this.showHANotification(
          this.t('notifications.error'),
          response.error || this.t('fix.error_unknown'),
          'haca_error'
        );
      }
    } catch (error) {
      this.showHANotification(
        this.t('notifications.error'),
        error.message,
        'haca_error'
      );
    }
  }

  exportCSV(issues, containerId) {
    if (!issues || issues.length === 0) {
      this.showHANotification(
        this.t('notifications.error'),
        'No issues to export',
        'haca_csv_empty'
      );
      return;
    }
    const headers = ['entity_id', 'alias', 'type', 'severity', 'message', 'location', 'recommendation'];
    const rows = [headers];
    issues.forEach(i => {
      rows.push(headers.map(h => {
        const val = String(i[h] || '');
        return '"' + val.replace(/"/g, '""') + '"';
      }));
    });
    const csv = rows.map(r => r.join(',')).join('\n');
    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    const date = new Date().toISOString().slice(0, 10);
    a.download = `haca-${containerId}-${date}.csv`;
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(a.href); }, 200);
  }
}

customElements.define('haca-panel', HacaPanel);
console.log('[HACA] Custom element registered');
