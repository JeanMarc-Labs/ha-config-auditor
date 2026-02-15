class HacaPanel extends HTMLElement {
  set panel(panelInfo) {
    this._panel = panelInfo;
    this.hass = panelInfo.hass;

    if (!this._initialized) {
      this._initialized = true;
      console.log('[HACA] Panel initialized with hass');
      this.render();
      this.attachListeners();
      // Attendre que hass.states soit rempli
      setTimeout(() => {
        console.log('[HACA] Loading initial data...');
        this.updateFromHass();
      }, 500);
    }
  }

  set hass(hass) {
    this._hass = hass;
    // NE RIEN FAIRE - pas de rechargement automatique
    // updateFromHass() est appelé seulement :
    // 1. Au démarrage (dans set panel)
    // 2. Après un scan (dans scanAll/scanAutomations/scanEntities)
  }

  get hass() {
    return this._hass;
  }

  render() {
    this.innerHTML = `
      <style>
        :host {
          display: block;
          padding: 24px;
          background: var(--primary-background-color);
          color: var(--primary-text-color);
          font-family: 'Roboto', 'Outfit', sans-serif;
        }
        .container { max-width: 1400px; margin: 0 auto; animation: fadeIn 0.5s ease-out; }
        
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: translateY(0); }
        }

        .header {
          background: linear-gradient(135deg, var(--primary-color) 0%, var(--accent-color, #03a9f4) 100%);
          color: white;
          padding: 32px;
          border-radius: 16px;
          margin-bottom: 24px;
          box-shadow: 0 8px 32px rgba(0,0,0,0.15);
          display: flex;
          justify-content: space-between;
          align-items: center;
          flex-wrap: wrap;
          gap: 20px;
        }
        
        .header-title { display: flex; align-items: center; gap: 16px; }
        .header-title ha-icon { --mdc-icon-size: 48px; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3)); }
        .header h1 { margin: 0; font-size: 32px; font-weight: 500; letter-spacing: -0.5px; }
        
        .actions { display: flex; gap: 12px; flex-wrap: wrap; }
        
        button {
          background: rgba(255, 255, 255, 0.15);
          color: white;
          border: 1px solid rgba(255, 255, 255, 0.3);
          padding: 10px 20px;
          border-radius: 12px;
          cursor: pointer;
          font-size: 14px;
          font-weight: 500;
          display: flex;
          align-items: center;
          gap: 8px;
          backdrop-filter: blur(8px);
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        
        button:hover {
          background: rgba(255, 255, 255, 0.25);
          transform: translateY(-2px);
          box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        }
        
        button:active { transform: translateY(0); }
        button:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
        
        button#scan-all { background: white; color: var(--primary-color); font-weight: 700; border: none; }
        button#scan-all:hover { background: rgba(255,255,255,0.9); }
        
        .stats {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
          gap: 20px;
          margin-bottom: 32px;
        }
        
        .stat-card {
          background: var(--card-background-color);
          padding: 24px;
          border-radius: 16px;
          box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgba(0,0,0,0.05));
          border: 1px solid var(--divider-color);
          display: flex;
          flex-direction: column;
          gap: 8px;
          transition: transform 0.3s ease;
        }
        
        .stat-card:hover { transform: translateY(-4px); }
        
        .stat-header { display: flex; justify-content: space-between; align-items: center; }
        .stat-label { color: var(--secondary-text-color); font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; }
        .stat-icon { color: var(--primary-color); opacity: 0.8; }
        .stat-value { font-size: 42px; font-weight: 700; color: var(--primary-text-color); margin-top: 4px; }
        
        .tabs-container { 
          margin-bottom: 24px; 
          position: sticky; 
          top: 0; 
          z-index: 10; 
          background: var(--primary-background-color);
          padding: 10px 0;
        }
        
        .tabs { 
          display: flex; 
          gap: 8px; 
          background: var(--secondary-background-color); 
          padding: 6px; 
          border-radius: 14px; 
          overflow-x: auto;
          scrollbar-width: none;
        }
        
        .tabs::-webkit-scrollbar { display: none; }
        
        .tabs .tab { 
          flex: 1; 
          padding: 12px 20px; 
          background: transparent; 
          cursor: pointer; 
          border-radius: 10px; 
          border: none;
          color: var(--secondary-text-color);
          font-weight: 600;
          white-space: nowrap;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 10px;
          transition: all 0.2s ease;
        }
        
        .tabs .tab ha-icon { --mdc-icon-size: 20px; }
        .tabs .tab:hover { color: var(--primary-text-color); background: rgba(0,0,0,0.05); }
        .tabs .tab.active { background: var(--card-background-color); color: var(--primary-color); box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
        
        .tab-content { display: none; animation: fadeIn 0.3s ease-out; }
        .tab-content.active { display: block; }
        
        .section-card {
          background: var(--card-background-color);
          padding: 0;
          border-radius: 16px;
          box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgba(0,0,0,0.05));
          border: 1px solid var(--divider-color);
          overflow: hidden;
        }
        
        .section-header {
          padding: 20px 24px;
          border-bottom: 1px solid var(--divider-color);
          display: flex;
          justify-content: space-between;
          align-items: center;
          background: var(--secondary-background-color);
        }
        
        .section-header h2 { margin: 0; font-size: 18px; font-weight: 600; display: flex; align-items: center; gap: 12px; }
        
        .issue-list { padding: 8px 24px 24px 24px; }
        
        .issue-item {
          padding: 20px;
          margin: 16px 0;
          background: var(--card-background-color);
          border: 1px solid var(--divider-color);
          border-left: 6px solid var(--primary-color);
          border-radius: 12px;
          transition: all 0.2s ease;
        }
        
        .issue-item:hover { transform: scale(1.01); box-shadow: 0 4px 12px rgba(0,0,0,0.05); }
        .issue-item.high { border-left-color: var(--error-color, #ef5350); background: rgba(239, 83, 80, 0.02); }
        .issue-item.medium { border-left-color: var(--warning-color, #ffa726); background: rgba(255, 167, 38, 0.02); }
        .issue-item.low { border-left-color: var(--info-color, #26c6da); background: rgba(38, 198, 218, 0.02); }
        
        .issue-main { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
        .issue-title { font-size: 16px; font-weight: 600; color: var(--primary-text-color); margin-bottom: 4px; }
        .issue-entity { font-size: 12px; color: var(--secondary-text-color); font-family: 'SFMono-Regular', Consolas, monospace; background: var(--secondary-background-color); padding: 2px 6px; border-radius: 4px; }
        .issue-message { margin: 12px 0; line-height: 1.5; color: var(--primary-text-color); opacity: 0.9; }
        
        .fix-btn {
          background: var(--primary-color);
          color: white;
          padding: 8px 16px;
          font-size: 13px;
          font-weight: 600;
          border-radius: 10px;
          box-shadow: 0 4px 10px rgba(var(--rgb-primary-color), 0.3);
        }
        
        .empty-state { text-align: center; padding: 60px; color: var(--secondary-text-color); }
        .empty-state ha-icon { --mdc-icon-size: 64px; opacity: 0.3; margin-bottom: 16px; }
        
        .data-table { width: 100%; border-collapse: separate; border-spacing: 0; }
        .data-table th { padding: 16px; text-align: left; font-size: 13px; text-transform: uppercase; color: var(--secondary-text-color); font-weight: 700; border-bottom: 2px solid var(--divider-color); }
        .data-table td { padding: 16px; border-bottom: 1px solid var(--divider-color); vertical-align: middle; }
        .data-table tr:last-child td { border-bottom: none; }
        
        .haca-modal-card { border-radius: 20px !important; overflow: hidden !important; border: 1px solid rgba(255,255,255,0.1); }
      </style>
      
      <div class="container">
        <div class="header">
          <div class="header-title">
            <ha-icon icon="mdi:shield-check-outline"></ha-icon>
            <div>
                <h1>H.A.C.A</h1>
                <div style="font-size: 14px; opacity: 0.8; font-weight: 400;">Home Assistant Config Auditor - V1.3.0</div>
            </div>
          </div>
          <div class="actions">
            <button id="scan-all"><ha-icon icon="mdi:magnify-scan"></ha-icon> Scan Complet</button>
            <button id="scan-auto"><ha-icon icon="mdi:robot"></ha-icon> Automations</button>
            <button id="scan-entity"><ha-icon icon="mdi:lightning-bolt"></ha-icon> Entités</button>
            <button id="scan-security" style="background: var(--error-color, #ef5350);"><ha-icon icon="mdi:shield-alert"></ha-icon> Sécurité</button>
            <button class="secondary" id="report"><ha-icon icon="mdi:file-document-outline"></ha-icon> Rapport</button>
            <button class="secondary" id="refresh"><ha-icon icon="mdi:refresh"></ha-icon> Actualiser</button>
          </div>
        </div>
        
        <div class="stats">
          <div class="stat-card">
            <div class="stat-header">
                <span class="stat-label">Health Score</span>
                <ha-icon icon="mdi:heart-pulse" class="stat-icon"></ha-icon>
            </div>
            <div class="stat-value" id="health-score">--</div>
            <div style="font-size: 12px; color: var(--secondary-text-color);">Score de santé global</div>
          </div>
          <div class="stat-card" style="border-left: 5px solid var(--error-color, #ef5350);">
            <div class="stat-header">
                <span class="stat-label">Sécurité</span>
                <ha-icon icon="mdi:shield-lock" style="color: var(--error-color, #ef5350);"></ha-icon>
            </div>
            <div class="stat-value" id="security-count">0</div>
            <div style="font-size: 12px; color: var(--secondary-text-color);">Secrets et vulnérabilités</div>
          </div>
          <div class="stat-card">
            <div class="stat-header">
                <span class="stat-label">Automations</span>
                <ha-icon icon="mdi:robot-confused" class="stat-icon"></ha-icon>
            </div>
            <div class="stat-value" id="auto-count">0</div>
            <div style="font-size: 12px; color: var(--secondary-text-color);">Issues d'automations</div>
          </div>
          <div class="stat-card">
            <div class="stat-header">
                <span class="stat-label">Entités</span>
                <ha-icon icon="mdi:lightning-bolt" class="stat-icon"></ha-icon>
            </div>
            <div class="stat-value" id="entity-count">0</div>
            <div style="font-size: 12px; color: var(--secondary-text-color);">Entités indisponibles/zombies</div>
          </div>
          <div class="stat-card">
            <div class="stat-header">
                <span class="stat-label">Performance</span>
                <ha-icon icon="mdi:speedometer-slow" class="stat-icon"></ha-icon>
            </div>
            <div class="stat-value" id="perf-count">0</div>
            <div style="font-size: 12px; color: var(--secondary-text-color);">Boucles et impact DB</div>
          </div>
        </div>
        
        <div class="tabs-container">
          <div class="tabs">
            <button class="tab active" data-tab="all"><ha-icon icon="mdi:view-list"></ha-icon> Toutes</button>
            <button class="tab" data-tab="automations"><ha-icon icon="mdi:robot"></ha-icon> Automations</button>
            <button class="tab" data-tab="entities"><ha-icon icon="mdi:lightning-bolt"></ha-icon> Entités</button>
            <button class="tab" data-tab="security"><ha-icon icon="mdi:shield-lock"></ha-icon> Sécurité</button>
            <button class="tab" data-tab="performance"><ha-icon icon="mdi:gauge"></ha-icon> Performance</button>
            <button class="tab" data-tab="backups"><ha-icon icon="mdi:history"></ha-icon> Backups</button>
            <button class="tab" data-tab="reports"><ha-icon icon="mdi:file-chart"></ha-icon> Rapports</button>
          </div>
        </div>
        
        <div class="section-card">
          <div id="tab-all" class="tab-content active">
            <div class="section-header">
                <h2><ha-icon icon="mdi:alert-circle-outline"></ha-icon> Toutes les Issues</h2>
            </div>
            <div id="issues-all" class="issue-list"></div>
          </div>
          
          <div id="tab-security" class="tab-content">
            <div class="section-header">
                <h2><ha-icon icon="mdi:shield-lock"></ha-icon> Issues de Sécurité</h2>
            </div>
            <div id="issues-security" class="issue-list"></div>
          </div>
          
          <div id="tab-automations" class="tab-content">
            <div class="section-header">
                <h2><ha-icon icon="mdi:robot"></ha-icon> Issues d'Automations</h2>
            </div>
            <div id="issues-automations" class="issue-list"></div>
          </div>
          
          <div id="tab-entities" class="tab-content">
            <div class="section-header">
                <h2><ha-icon icon="mdi:lightning-bolt"></ha-icon> Issues d'Entités</h2>
            </div>
            <div id="issues-entities" class="issue-list"></div>
          </div>
          
          <div id="tab-performance" class="tab-content">
            <div class="section-header">
                <h2><ha-icon icon="mdi:gauge"></ha-icon> Issues de Performance</h2>
            </div>
            <div id="issues-performance" class="issue-list"></div>
          </div>
          
          <div id="tab-backups" class="tab-content">
            <div class="section-header">
                <h2><ha-icon icon="mdi:history"></ha-icon> Gestion des Backups</h2>
                <button id="create-backup" style="background: var(--primary-color);"><ha-icon icon="mdi:plus"></ha-icon> Créer un Backup</button>
            </div>
            <div id="backups-list" style="padding: 0;">Chargement...</div>
          </div>
          
          <div id="tab-reports" class="tab-content">
            <div class="section-header">
                <h2><ha-icon icon="mdi:file-chart"></ha-icon> Gestion des Rapports</h2>
                <button id="refresh-reports" class="secondary"><ha-icon icon="mdi:refresh"></ha-icon> Actualiser</button>
            </div>
            <div id="reports-list" style="padding: 0;">Chargement...</div>
          </div>
        </div>
      </div>
    `;
  }

  attachListeners() {
    this.querySelector('#scan-all').addEventListener('click', () => this.scanAll());
    this.querySelector('#scan-auto').addEventListener('click', () => this.scanAutomations());
    this.querySelector('#scan-entity').addEventListener('click', () => this.scanEntities());
    this.querySelector('#scan-security').addEventListener('click', () => this.scanAll()); // Utilise scanAll pour simplifier
    this.querySelector('#report').addEventListener('click', () => this.generateReport());
    this.querySelector('#refresh').addEventListener('click', () => {
      this.updateFromHass();
      alert('✅ Données actualisées');
    });

    // Backup listeners
    this.querySelector('#create-backup').addEventListener('click', () => this.createBackup());

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
  }

  async loadBackups() {
    const container = this.querySelector('#backups-list');
    container.innerHTML = 'Chargement...';
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
        throw new Error('Format de données invalide');
      }

      this.renderBackups(backups);

    } catch (error) {
      console.error('[HACA] Error loading backups:', error);
      container.innerHTML = `<div class="empty-state">❌ Erreur: ${error.message}</div>`;
    }
  }

  renderBackups(backups) {
    const container = this.querySelector('#backups-list');
    if (backups.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
            <ha-icon icon="mdi:archive-off-outline"></ha-icon>
            <p>Aucun backup disponible</p>
        </div>`;
      return;
    }

    container.innerHTML = `
        <table class="data-table">
            <thead>
                <tr>
                    <th>Nom</th>
                    <th>Date</th>
                    <th>Taille</th>
                    <th>Action</th>
                </tr>
            </thead>
            <tbody>
                ${backups.map(b => `
                    <tr>
                        <td style="font-weight: 500;">
                            <div style="display:flex; align-items:center; gap:10px;">
                                <ha-icon icon="mdi:zip-box-outline" style="color:var(--secondary-text-color)"></ha-icon>
                                ${b.name}
                            </div>
                        </td>
                        <td>${new Date(b.created).toLocaleString()}</td>
                        <td><span style="background: var(--secondary-background-color); padding: 4px 8px; border-radius: 6px; font-size: 12px;">${Math.round(b.size / 1024)} KB</span></td>
                        <td>
                            <button class="restore-btn" data-path="${b.path}" style="background: var(--warning-color, #ff9800); color: black;">
                                <ha-icon icon="mdi:backup-restore"></ha-icon> Restaurer
                            </button>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;

    container.querySelectorAll('.restore-btn').forEach(btn => {
      btn.addEventListener('click', (e) => this.restoreBackup(e.currentTarget.dataset.path));
    });
  }

  async createBackup() {
    if (!confirm('Créer un nouveau backup ?')) return;
    try {
      const result = await this.hass.callWS({
        type: 'call_service',
        domain: 'config_auditor',
        service: 'create_backup',
        service_data: {},
        return_response: true
      });

      if (result && result.success) {
        alert('✅ Backup créé: ' + (result.message || 'Succès'));
      } else {
        alert('✅ Backup créé');
      }
      this.loadBackups();
    } catch (error) {
      alert('❌ Erreur: ' + error.message);
    }
  }

  async restoreBackup(path) {
    if (!confirm('Voulez-vous vraiment restaurer ce backup ? \n⚠️ Une sauvegarde de l\'état actuel sera créée avant restauration.')) return;
    try {
      await this.hass.callService('config_auditor', 'restore_backup', { backup_path: path });
      alert('✅ Backup restauré. Redémarrez Home Assistant.');
    } catch (error) {
      alert('❌ Erreur: ' + error.message);
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
    safeSetText('entity-count', data.entity_issues || 0);
    safeSetText('perf-count', data.performance_issues || 0);
    safeSetText('security-count', data.security_issues || 0);

    const autoIssues = data.automation_issue_list || [];
    const entityIssues = data.entity_issue_list || [];
    const perfIssues = data.performance_issue_list || [];
    const securityIssues = data.security_issue_list || [];
    const allIssues = [...autoIssues, ...entityIssues, ...perfIssues, ...securityIssues];

    console.log('[HACA] Automations:', autoIssues.length, 'Entities:', entityIssues.length, 'Performance:', perfIssues.length, 'Security:', securityIssues.length);

    // Afficher dans chaque section
    this.renderIssues(allIssues, 'issues-all');
    this.renderIssues(autoIssues, 'issues-automations');
    this.renderIssues(entityIssues, 'issues-entities');
    this.renderIssues(perfIssues, 'issues-performance');
    this.renderIssues(securityIssues, 'issues-security');
  }

  renderIssues(issues, containerId) {
    const container = this.querySelector(`#${containerId}`);
    if (!container) return;

    if (issues.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
            <ha-icon icon="mdi:check-decagram-outline"></ha-icon>
            <p>Aucun problème détecté dans cette catégorie</p>
        </div>`;
      return;
    }

    container.innerHTML = issues.map(i => {
      const isFixable = ['device_id_in_trigger', 'device_id_in_action', 'device_id_in_target', 'incorrect_mode_motion_single', 'template_simple_state'].includes(i.type) || i.fix_available;
      const icon = i.severity === 'high' ? 'mdi:alert-decagram' : (i.severity === 'medium' ? 'mdi:alert' : 'mdi:information');
      const isSecurity = i.type.includes('security') || i.type.includes('secret') || i.type === 'sensitive_data_exposure';

      return `
      <div class="issue-item ${i.severity}" style="${isSecurity ? 'border-left-color: var(--error-color, #ef5350);' : ''}">
        <div class="issue-main">
            <div style="flex: 1;">
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 6px;">
                    <ha-icon icon="${isSecurity ? 'mdi:shield-alert' : icon}" style="--mdc-icon-size: 18px; ${isSecurity ? 'color: var(--error-color, #ef5350);' : ''}"></ha-icon>
                    <div class="issue-title">${i.alias || i.entity_id}</div>
                </div>
                <div class="issue-entity">${i.entity_id}</div>
            </div>
            <div style="display: flex; gap: 8px;">
                <button class="explain-btn" data-issue='${JSON.stringify(i).replace(/'/g, "&apos;")}' style="background: var(--accent-color, #03a9f4); color: white;">
                    <ha-icon icon="mdi:robot"></ha-icon> IA
                </button>
                ${isFixable ? `<button class="fix-btn" data-issue='${JSON.stringify(i).replace(/'/g, "&apos;")}'><ha-icon icon="mdi:magic-staff"></ha-icon> Corriger</button>` : ''}
            </div>
        </div>
        <div class="issue-message">${i.message}</div>
        ${i.recommendation ? `
            <div style="font-size: 13px; color: var(--secondary-text-color); margin-top: 12px; display: flex; align-items: center; gap: 8px; background: rgba(0,0,0,0.03); padding: 8px 12px; border-radius: 8px;">
                <ha-icon icon="mdi:lightbulb-outline" style="--mdc-icon-size: 16px;"></ha-icon>
                <span>${i.recommendation}</span>
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
    const modal = this.createModal('🤖 L\'IA analyse votre problème...');
    try {
      const response = await this.hass.callWS({
        type: 'call_service',
        domain: 'config_auditor',
        service: 'explain_issue_ai',
        service_data: { issue: issue },
        return_response: true
      });

      console.log('[HACA] AI Explanation result:', response);
      let explanation = "Désolé, l'IA n'a pas pu générer d'explication. Vérifiez si vous avez configuré OpenAI/Gemini dans Home Assistant.";

      if (response && response.response && response.response.explanation) {
        explanation = response.response.explanation;
      } else if (response && response.explanation) {
        explanation = response.explanation;
      }

      modal.innerHTML = `
        <div style="padding: 24px;">
            <div style="display: flex; align-items: center; gap: 16px; margin-bottom: 24px; border-bottom: 1px solid var(--divider-color); padding-bottom: 16px;">
                <ha-icon icon="mdi:robot" style="--mdc-icon-size: 48px; color: var(--primary-color);"></ha-icon>
                <div>
                    <h2 style="margin: 0;">Analyse par IA Assist</h2>
                    <div style="font-size: 14px; opacity: 0.7;">${issue.alias || issue.entity_id}</div>
                </div>
            </div>
            
            <div style="background: var(--secondary-background-color); padding: 20px; border-radius: 12px; line-height: 1.6; font-size: 15px; color: var(--primary-text-color); white-space: pre-wrap;">${explanation}</div>
            
            <div style="margin-top: 24px; display: flex; justify-content: flex-end;">
                <button class="close-btn" style="background: var(--primary-color);">Fermer</button>
            </div>
        </div>
      `;

      modal.querySelector('.close-btn').addEventListener('click', () => modal.parentElement.remove());

    } catch (error) {
      modal.innerHTML = `<div style="padding: 24px; color: var(--error-color);">❌ Erreur AI: ${error.message}</div>`;
    }
  }

  async showFixPreview(issue) {
    // Determine service payload based on issue type
    let service = '';
    let serviceData = {};

    if (['device_id_in_trigger', 'device_id_in_action', 'device_id_in_target', 'device_trigger_platform', 'device_id_in_condition', 'device_condition_platform'].includes(issue.type)) {
      service = 'preview_device_id';
      // Extract automation_id from entity_id (automation.xxx -> xxx) or use unique_id if available?
      // Analyzer uses entity_id mapping. refactoring_assistant expects automation_id (which is unique_id usually).
      // But analyzer stores config['id'] as automation_id in _automation_configs key mapping? 
      // Wait, refactoring assistant uses `_load_automation_by_id`.
      // If entity_id is passed, we might need value from registry. 
      // However, let's try passing entity_id first, maybe refactoring assistant handles it?
      // Checking refactoring_assistant.py: `_load_automation_by_id` iterates automations and checks `id`.
      // Analyzer ensures `id` is present or generated.
      // But we need the ID from the automation file, not the entity_id.
      // The issue object has `entity_id`.
      // We need to resolve entity_id to automation_id or hope they match?
      // Actually, HACA analyzer maps by entity_id.
      // Refactoring assistant needs the ID found in YAML.
      // Maybe we can pass entity_id? No, implementation iterates `id`.

      // Workaround: We need the automation ID.
      // Let's assume for now we can find it via entity registry in backend, but frontend only has issue data.
      // Let's look at `issue` object again.
      // It has `entity_id`.
      // We might need to ask backend to resolve it or add automation_id to issue.
      // For now, let's try guessing: get the state, and look for `id` attribute? 
      const state = this.hass.states[issue.entity_id];
      if (state && state.attributes.id) {
        serviceData = { automation_id: state.attributes.id };
      } else {
        // Fallback: try to pass entity_id stripping 'automation.'? No that's alias usually.
        // If we can't find ID, we can't fix.
        console.warn("Could not find automation ID for", issue.entity_id);
        alert("Impossible de trouver l'ID de l'automation. Correction impossible via UI pour le moment.");
        return;
      }

    } else if (issue.type === 'incorrect_mode_motion_single') {
      service = 'preview_mode';
      const state = this.hass.states[issue.entity_id];
      if (state && state.attributes.id) {
        serviceData = { automation_id: state.attributes.id, mode: 'restart' };
      } else {
        alert("Impossible de trouver l'ID de l'automation.");
        return;
      }
    } else if (issue.type === 'template_simple_state') {
      service = 'preview_template';
      const state = this.hass.states[issue.entity_id];
      if (state && state.attributes.id) {
        serviceData = { automation_id: state.attributes.id };
      } else {
        alert("Impossible de trouver l'ID de l'automation.");
        return;
      }
    }

    // Show loading
    // Show loading
    const modal = this.createModal('Chargement de la proposition...');

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
        modal.innerHTML = `<div style="padding:20px;color:red">Erreur: ${response.error || 'Erreur inconnue'}</div>`;
        setTimeout(() => modal.remove(), 3000);
      }
    } catch (e) {
      modal.innerHTML = `<div style="padding:20px;color:red">Erreur appel service: ${e.message}</div>`;
      setTimeout(() => modal.remove(), 3000);
    }
  }

  createModal(content) {
    const existing = this.querySelector('.haca-modal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.className = 'haca-modal';
    modal.style.cssText = `
        position: fixed; top: 0; left: 0; right: 0; bottom: 0;
        background: rgba(0,0,0,0.8); z-index: 9999;
        display: flex; justify-content: center; align-items: center;
      `;

    const card = document.createElement('div');
    card.className = 'haca-modal-card';
    card.style.cssText = `
        background: var(--card-background-color); width: 90%; max-width: 1000px;
        max-height: 90vh; overflow: auto; border-radius: 12px; padding: 0;
        box-shadow: 0 4px 20px rgba(0,0,0,0.5); display: flex; flex-direction: column;
      `;

    card.innerHTML = typeof content === 'string' ? `<div style="padding:20px">${content}</div>` : '';
    if (typeof content !== 'string') card.appendChild(content);

    modal.appendChild(card);
    this.appendChild(modal);

    // Close on background click
    modal.addEventListener('click', (e) => {
      if (e.target === modal) modal.remove();
    });

    return card;
  }

  renderDiffModal(card, result, issue, previewService, serviceData) {
    card.innerHTML = `
        <div class="section-header" style="background: var(--secondary-background-color); border-bottom: 1px solid var(--divider-color); padding: 20px 24px;">
            <h2 style="margin:0; font-size: 20px; display: flex; align-items: center; gap: 12px;">
                <ha-icon icon="mdi:magic-staff"></ha-icon> Proposition de Correction
            </h2>
            <button class="secondary" onclick="this.closest('.haca-modal').remove()">Fermer</button>
        </div>
        <div style="padding: 24px; flex: 1; overflow: auto;">
            <div style="margin-bottom: 24px; background: rgba(var(--rgb-primary-color), 0.05); padding: 16px; border-radius: 12px; border-left: 4px solid var(--primary-color);">
                <div style="margin-bottom: 8px; display: flex; align-items: center; gap: 8px;">
                    <ha-icon icon="mdi:robot" style="--mdc-icon-size: 18px; color: var(--primary-color);"></ha-icon>
                    <strong>Automation :</strong> <span style="font-weight: 500;">${result.alias}</span> (${result.automation_id})
                </div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <ha-icon icon="mdi:alert-circle-outline" style="--mdc-icon-size: 18px; color: var(--error-color);"></ha-icon>
                    <strong>Problème :</strong> ${issue.message}
                </div>
            </div>
            
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 24px;">
                <div>
                    <h3 style="margin-top:0; color: var(--error-color); font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px; display: flex; align-items: center; gap: 8px;">
                        <ha-icon icon="mdi:minus-box-outline"></ha-icon> Avant (Actuel)
                    </h3>
                    <pre style="background: var(--secondary-background-color); padding: 16px; overflow: auto; border-radius: 12px; font-size: 12px; border: 1px solid var(--divider-color); max-height: 400px;">${this.escapeHtml(result.current_yaml)}</pre>
                </div>
                <div>
                    <h3 style="margin-top:0; color: var(--success-color, #4caf50); font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px; display: flex; align-items: center; gap: 8px;">
                        <ha-icon icon="mdi:plus-box-outline"></ha-icon> Après (Proposition)
                    </h3>
                    <pre style="background: var(--secondary-background-color); padding: 16px; overflow: auto; border-radius: 12px; font-size: 12px; border: 1px solid var(--divider-color); max-height: 400px; outline: 1px solid var(--success-color, #4caf50); outline-offset: -1px;">${this.highlightDiff(result.new_yaml, result.current_yaml)}</pre>
                </div>
            </div>
            
            <div style="background: var(--secondary-background-color); padding: 20px; border-radius: 12px; border: 1px solid var(--divider-color);">
                <div style="font-weight: 700; margin-bottom: 12px; display: flex; align-items: center; gap: 10px;">
                    <ha-icon icon="mdi:playlist-check"></ha-icon>
                    Changements identifiés (${result.changes_count}) :
                </div>
                <ul style="margin: 0; padding-left: 24px; line-height: 1.6; color: var(--primary-text-color);">
                    ${result.changes.map(c => `<li style="margin-bottom: 4px;">${c.description}</li>`).join('')}
                </ul>
            </div>
        </div>
        <div style="padding: 20px 24px; border-top: 1px solid var(--divider-color); text-align: right; display: flex; justify-content: flex-end; gap: 16px; background: var(--secondary-background-color);">
            <button class="secondary" onclick="this.closest('.haca-modal').remove()"><ha-icon icon="mdi:close"></ha-icon> Annuler</button>
            <button id="apply-fix-btn" style="background: var(--primary-color); color: white; padding: 12px 24px; border-radius: 12px; box-shadow: 0 4px 10px rgba(var(--rgb-primary-color), 0.3);">
                <ha-icon icon="mdi:check-circle-outline"></ha-icon> Appliquer la Correction
            </button>
        </div>
      `;

    card.querySelector('#apply-fix-btn').addEventListener('click', () => {
      this.applyFix(issue, previewService, serviceData, card);
    });
  }

  async applyFix(issue, previewService, serviceData, card) {
    const btn = card.querySelector('#apply-fix-btn');
    btn.disabled = true;
    btn.textContent = 'Application en cours...';

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
        card.innerHTML = `
                <div style="padding: 48px 32px; text-align: center; animation: fadeIn 0.4s ease-out;">
                    <div style="font-size: 64px; margin-bottom: 24px; filter: drop-shadow(0 4px 12px rgba(76, 175, 80, 0.4));">✅</div>
                    <h2 style="font-size: 24px; font-weight: 700; margin-bottom: 12px; color: var(--primary-text-color);">Correction Appliquée !</h2>
                    <p style="color: var(--secondary-text-color); margin-bottom: 24px; line-height: 1.6;">${response.message}</p>
                    ${response.backup_path ? `
                        <div style="background: var(--secondary-background-color); padding: 12px; border-radius: 12px; margin-bottom: 32px; display: inline-flex; align-items: center; gap: 10px; border: 1px solid var(--divider-color);">
                            <ha-icon icon="mdi:zip-box-outline" style="color: var(--primary-color);"></ha-icon>
                            <span style="font-family: monospace; font-size: 12px;">Backup créé : ${response.backup_path.split(/[\\/]/).pop()}</span>
                        </div>
                    ` : ''}
                    <div>
                        <button style="background: var(--primary-color); color: white; padding: 12px 32px; font-weight: 600;" onclick="this.closest('.haca-modal').remove()">Fermer</button>
                    </div>
                </div>
              `;

        // Refresh data
        setTimeout(() => this.scanAutomations(), 1000);
      } else {
        alert('Erreur: ' + (response.error || 'Erreur inconnue'));
        btn.disabled = false;
        btn.textContent = '✅ Appliquer la Correction';
      }
    } catch (e) {
      alert('Erreur appel service: ' + e.message);
      btn.disabled = false;
      btn.textContent = '✅ Appliquer la Correction';
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
    // Simple highlighting for now: just return escapeHtml since real diff is complex
    // For a better experience, we could highlight lines that changed, but simple text is okay for V1.
    return this.escapeHtml(newText);
  }

  updateFromHass() {
    // Update when hass changes
    const states = Object.values(this.hass.states).filter(s => s.entity_id.startsWith('sensor.h_a_c_a_'));
    console.log('[HACA] updateFromHass: found', states.length, 'sensors');

    if (states.length > 0) {
      const data = {
        health_score: 0,
        automation_issues: 0,
        entity_issues: 0,
        performance_issues: 0,
        automation_issue_list: [],
        entity_issue_list: [],
        performance_issue_list: []
      };

      states.forEach(s => {
        if (s.entity_id.includes('health_score')) {
          data.health_score = parseInt(s.state) || 0;
        } else if (s.entity_id.includes('automation_issues')) {
          data.automation_issues = parseInt(s.state) || 0;
          data.automation_issue_list = s.attributes.automation_issue_list || [];
        } else if (s.entity_id.includes('entity_issues')) {
          data.entity_issues = parseInt(s.state) || 0;
          data.entity_issue_list = s.attributes.entity_issue_list || [];
        } else if (s.entity_id.includes('performance_issues')) {
          data.performance_issues = parseInt(s.state) || 0;
          data.performance_issue_list = s.attributes.performance_issue_list || [];
        }
      });

      console.log('[HACA] Data:', data);
      this.updateUI(data);
    } else {
      console.log('[HACA] No sensors found yet');
    }
  }

  async scanAll() {
    const btn = this.querySelector('#scan-all');
    btn.disabled = true;
    btn.textContent = '⏳ Scan...';
    try {
      await this.hass.callService('config_auditor', 'scan_all');
      setTimeout(() => this.updateFromHass(), 2000);
    } catch (error) {
      console.error('[HACA] Scan error:', error);
      alert('❌ ' + error.message);
    } finally {
      btn.disabled = false;
      btn.textContent = '🔍 Scan Complet';
    }
  }

  async scanAutomations() {
    const btn = this.querySelector('#scan-auto');
    btn.disabled = true;
    btn.textContent = '⏳...';
    try {
      await this.hass.callService('config_auditor', 'scan_automations');
      setTimeout(() => this.updateFromHass(), 2000);
    } catch (error) {
      alert('❌ ' + error.message);
    } finally {
      btn.disabled = false;
      btn.textContent = '🤖 Scan Automations';
    }
  }

  async scanEntities() {
    const btn = this.querySelector('#scan-entity');
    btn.disabled = true;
    btn.textContent = '⏳...';
    try {
      await this.hass.callService('config_auditor', 'scan_entities');
      setTimeout(() => this.updateFromHass(), 2000);
    } catch (error) {
      alert('❌ ' + error.message);
    } finally {
      btn.disabled = false;
      btn.textContent = '⚡ Scan Entités';
    }
  }

  async generateReport() {
    try {
      await this.hass.callService('config_auditor', 'generate_report');
      alert('✅ Rapports générés (MD, JSON, PDF) dans /config/.haca_reports/');
      if (this.querySelector('.tab[data-tab="reports"]').classList.contains('active')) {
        this.loadReports();
      }
    } catch (error) {
      alert('❌ ' + error.message);
    }
  }

  async loadReports() {
    const container = this.querySelector('#reports-list');
    container.innerHTML = 'Chargement...';
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
      container.innerHTML = `<div class="empty-state">❌ Erreur: ${error.message}</div>`;
    }
  }

  renderReports(reports) {
    console.log('[HACA] renderReports called with:', reports);
    const container = this.querySelector('#reports-list');

    if (!reports || !Array.isArray(reports) || reports.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
            <ha-icon icon="mdi:file-search-outline"></ha-icon>
            <p>Aucun rapport généré</p>
        </div>`;
      return;
    }

    try {
      container.innerHTML = `
        <table class="data-table">
            <thead>
                <tr>
                    <th>Date de l'Audit</th>
                    <th>Formats Disponibles</th>
                </tr>
            </thead>
            <tbody>
                ${reports.map(s => {
        if (!s || !s.formats) {
          return '';
        }
        return `
                    <tr>
                        <td>
                            <div style="display: flex; align-items: center; gap: 12px;">
                                <div style="background: var(--primary-color); color: white; width: 40px; height: 40px; border-radius: 10px; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 10px rgba(var(--rgb-primary-color), 0.2);">
                                    <ha-icon icon="mdi:calendar-check"></ha-icon>
                                </div>
                                <div>
                                    <div style="font-weight: 600; font-size: 15px;">${new Date(s.created).toLocaleString()}</div>
                                    <div style="font-size: 11px; color: var(--secondary-text-color); font-family: monospace;">ID: ${s.session_id}</div>
                                </div>
                            </div>
                        </td>
                        <td>
                            <div style="display: flex; gap: 12px; align-items: center;">
                                ${Object.entries(s.formats).map(([ext, info]) => `
                                    <div style="display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 10px; border: 1px solid var(--divider-color); border-radius: 12px; min-width: 90px; background: var(--secondary-background-color); transition: all 0.2s ease;">
                                        <span style="font-size: 11px; font-weight: 800; color: var(--primary-color);">${ext.toUpperCase()}</span>
                                        <div style="display: flex; gap: 6px;">
                                            <button class="view-report-btn" data-name="${info.name}" title="Voir" style="padding: 6px; background: white; color: var(--primary-color); border: 1px solid var(--divider-color); border-radius: 8px; cursor: pointer;">
                                                <ha-icon icon="mdi:eye-outline" style="--mdc-icon-size: 18px;"></ha-icon>
                                            </button>
                                            <button class="dl-report-btn" data-name="${info.name}" title="Télécharger" style="padding: 6px; background: white; color: var(--success-color, #4caf50); border: 1px solid var(--divider-color); border-radius: 8px; cursor: pointer;">
                                                <ha-icon icon="mdi:download-outline" style="--mdc-icon-size: 18px;"></ha-icon>
                                            </button>
                                        </div>
                                        <span style="font-size: 10px; color: var(--secondary-text-color); font-weight: 500;">${Math.round(info.size / 1024)} KB</span>
                                    </div>
                                `).join('')}
                            </div>
                        </td>
                    </tr>
                `}).join('')}
            </tbody>
        </table>
      `;

      container.querySelectorAll('.view-report-btn').forEach(btn => {
        btn.addEventListener('click', (e) => this.viewReport(e.currentTarget.dataset.name));
      });
      container.querySelectorAll('.dl-report-btn').forEach(btn => {
        btn.addEventListener('click', (e) => this.downloadReport(e.currentTarget.dataset.name));
      });
    } catch (err) {
      console.error('[HACA] Error rendering reports:', err);
      container.innerHTML = `<div class="empty-state">❌ Erreur d'affichage: ${err.message}</div>`;
    }
  }

  async viewReport(name) {
    if (name.endsWith('.pdf')) {
      const modal = this.createModal('');
      // Enlarge modal for PDF to almost full screen
      modal.style.width = '95%';
      modal.style.height = '95%';
      modal.style.maxWidth = '1600px';
      modal.style.maxHeight = '95vh';

      modal.innerHTML = `
          <div style="padding: 20px 24px; border-bottom: 1px solid var(--divider-color); display: flex; justify-content: space-between; align-items: center; background: var(--secondary-background-color);">
              <h2 style="margin:0; font-size: 18px; display: flex; align-items: center; gap: 12px;">
                <ha-icon icon="mdi:file-pdf-box" style="color: var(--error-color);"></ha-icon>
                ${name}
              </h2>
              <div style="display: flex; gap: 12px;">
                <a href="/haca_reports/${name}" target="_blank" style="text-decoration: none;">
                  <button style="background: var(--primary-color); color: white;">
                    <ha-icon icon="mdi:fullscreen"></ha-icon> Plein Écran
                  </button>
                </a>
                <button class="secondary" onclick="this.closest('.haca-modal').remove()">Fermer</button>
              </div>
          </div>
          <div style="flex: 1; height: 100%; background: #525659;">
              <iframe src="/haca_reports/${name}" style="width: 100%; height: 85vh; border: none;"></iframe>
          </div>
      `;
      return;
    }

    const modal = this.createModal('Chargement du rapport...');
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
        modal.innerHTML = `
            <div style="padding: 16px; border-bottom: 1px solid var(--divider-color); display: flex; justify-content: space-between; align-items: center;">
                <h2 style="margin:0">${name}</h2>
                <button onclick="this.closest('.haca-modal').remove()">Fermer</button>
            </div>
            <div style="padding: 16px; flex: 1; overflow: auto; background: var(--secondary-background-color); font-family: monospace; white-space: pre-wrap; font-size: 13px;">
                ${data.type === 'json' ? JSON.stringify(data.content, null, 2) : data.content}
            </div>
        `;
      } else {
        modal.innerHTML = `<div style="padding:20px;color:red">Erreur: ${data.error}</div>`;
      }
    } catch (e) {
      modal.innerHTML = `<div style="padding:20px;color:red">Erreur: ${e.message}</div>`;
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
}

customElements.define('haca-panel', HacaPanel);
console.log('[HACA] Custom element registered');
