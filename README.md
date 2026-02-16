# H.A.C.A - Home Assistant Config Auditor

[![GitHub Release](https://img.shields.io/github/v/release/JeanMarc-Labs/ha-config-auditor?style=flat-square)](https://github.com/JeanMarc-Labs/ha-config-auditor/releases)
[![License](https://img.shields.io/github/license/JeanMarc-Labs/ha-config-auditor?style=flat-square)](LICENSE)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange?style=flat-square)](https://hacs.xyz/)

[Français 🇫🇷](README.fr.md)

---

**Home Assistant Config Auditor (H.A.C.A)** is a powerful integration designed to help you maintain a healthy, secure, and high-performing Home Assistant installation. It deep-scans your configuration files, identifies best-practice violations, and provides automated refactoring tools to fix issues with a single click.

> [!WARNING]
> **H.A.C.A is currently in active development.**
> Any modifications made through this tool should be performed with full knowledge of the changes being applied. **Always perform a full Home Assistant backup before using the refactoring tools.**
> The H.A.C.A team declines all responsibility for any Home Assistant crashes, data loss, or configuration issues resulting from the use of this integration. Use at your own risk.

## ✨ Key Features

### 🔍 Specialized Analyzers
*   **Automation Analyzer**: Deep-scans your `automations.yaml` to detect stale `device_id` usage, inefficient modes (e.g., using `parallel` when `restart` is better), and "zombie" entity references.
*   **Performance Analyzer**: Monitors trigger rates and identifies "noisy" entities that cause database bloat. It detects potential automation loops and suggests optimizations for high-frequency updates.
*   **Security Auditor**: Automatically flags hardcoded secrets, API keys, and passwords that should be in `secrets.yaml`. It also warns about sensitive data exposure in notification services.
*   **Entity Health Monitor**: Tracks unavailable or unknown entities across your entire system, helping you keep your Dashboards and Automations "clean".

### 🤖 AI Assist & Refactoring
*   **AI Explainer**: Integrated with Home Assistant's conversation engine (OpenAI, Gemini, etc.), HACA can explain *why* something is flagged and provide personalized advice.
*   **Refactoring Assistant**: Apply fixes directly from the UI. Convert problematic device-based automations to entity-based ones, or optimize automation modes automatically.
*   **Backup & Safety**: Every automated fix creates a backup of your configuration, allowing for easy restoration if needed.

## 💾 Step-by-Step Installation

### Method 1: HACS (Recommended)
1.  Ensure [HACS](https://hacs.xyz/) is installed and configured.
2.  Open **HACS** from your sidebar.
3.  Click on **Integrations**.
4.  Click the **three dots** in the top right corner and select **Custom repositories**.
5.  Paste the following URL: `https://github.com/JeanMarc-Labs/ha-config-auditor`
6.  Select **Integration** as the category and click **Add**.
7.  Click **Install** on the H.A.C.A card that appears.
8.  **Restart** Home Assistant.

### Method 2: Manual Installation
1.  Download the latest release from the [releases page](https://github.com/JeanMarc-Labs/ha-config-auditor/releases).
2.  Extract the archive and copy the `custom_components/config_auditor` folder into your Home Assistant's `custom_components` directory.
3.  **Restart** Home Assistant.

### ⚙️ Final Setup
After installation and restart:
1.  Go to **Settings** > **Devices & Services**.
2.  Click **+ Add Integration**.
3.  Search for **HACA** (or **Home Assistant Config Auditor**).
4.  Follow the configuration steps.

## 🚀 Usage

### The H.A.C.A Panel
Once configured, a new **H.A.C.A** item will appear in your sidebar.
*   **Overview**: View your global **Health Score**.
*   **Issues List**: Browse detailed reports from all analyzers.
*   **Details**: Click on any issue to see a deep dive, recommendation, and (if available) an automated fix.

### AI Assistance
If you have an AI conversation agent configured in Home Assistant (like OpenAI or Google Generative AI), H.A.C.A will show an **"AI Explain"** button. Clicking this will give you a human-readable explanation of the technical issue.

### Sensors
HACA provides several diagnostic sensors, including:
*   `sensor.haca_health_score`: A percentage representing your overall config health.
*   `sensor.haca_total_issues`: Total number of issues across all analyzers.
