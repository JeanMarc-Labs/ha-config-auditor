# H.A.C.A - Home Assistant Config Auditor

[![GitHub Release](https://img.shields.io/github/v/release/JeanMarc-Labs/ha-config-auditor?style=flat-square)](https://github.com/yourusername/ha-config-auditor/releases)
[![License](https://img.shields.io/github/license/JeanMarc-Labs/ha-config-auditor?style=flat-square)](LICENSE)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange?style=flat-square)](https://hacs.xyz/)

[Français 🇫🇷](README.fr.md)

---

**Home Assistant Config Auditor (H.A.C.A)** is a powerful integration designed to help you maintain a healthy, secure, and high-performing Home Assistant installation. It scans your configurations and provides actionable insights and automated fixes.

### ✨ Key Features
- **Automation Scanner**: Detects stale `device_id` usage, inefficient modes, and zombie entity references.
- **Health Monitor**: Tracks unavailable, unknown, or stale entities across your entire system.
- **Performance Analyzer**: Identifies high-frequency triggers, potential automation loops, and database-bloating sensors.
- **Security Auditor**: Finds hardcoded secrets, API keys, and insecure data exposure in your configs.
- **AI Assist**: Powered by Home Assistant's conversation engine (OpenAI/Gemini) to explain complex issues and suggest fixes.
- **Refactoring Assistant**: One-click fixes for common automation smells.
- **Bilingual Support**: Full English and French support for UI and AI explanations.

### 💾 Installation
1.  **HACS (Recommended)**:
    - Go to HACS > Integrations.
    - Click the three dots in the top right > Custom Repositories.
    - Add `https://github.com/JeanMarc-Labs/ha-config-auditor` as an **Integration**.
    - Search for **HACA** and install.
2.  **Manual**:
    - Copy the `config_auditor` folder to your `custom_components` directory.
3.  **Setup**:
    - Restart Home Assistant.
    - Go to Settings > Devices & Services > Add Integration > Search for **HACA**.

### 🚀 Usage
Access the **H.A.C.A** panel from your sidebar to see your Health Score and detailed issues. Use the "AI Explain" button to get personalized advice.
