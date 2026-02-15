# H.A.C.A - Home Assistant Config Auditor

[![GitHub Release](https://img.shields.io/github/v/release/JeanMarc-Labs/ha-config-auditor?style=flat-square)](https://github.com/yourusername/ha-config-auditor/releases)
[![License](https://img.shields.io/github/license/JeanMarc-Labs/ha-config-auditor?style=flat-square)](LICENSE)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange?style=flat-square)](https://hacs.xyz/)

[English 🇬🇧](README.md)

---

**Home Assistant Config Auditor (H.A.C.A)** est une intégration puissante conçue pour vous aider à maintenir une installation Home Assistant saine, sécurisée et performante. Elle analyse vos configurations, fournit des rapports détaillés et propose des solutions automatisées.

### ✨ Fonctionnalités Clés
- **Scanner d'Automation**: Détecte l'utilisation de `device_id` périmés, les modes inefficaces et les références à des entités disparues.
- **Moniteur de Santé**: Suit les entités indisponibles, inconnues ou figées dans tout votre système.
- **Analyseur de Performance**: Identifie les déclenchements trop fréquents, les boucles potentielles et les capteurs qui saturent votre base de données.
- **Auditeur de Sécurité**: Trouve les secrets en clair (mots de passe, clés API) et les expositions de données sensibles.
- **IA Assistante**: Utilise le moteur de conversation de Home Assistant (OpenAI/Gemini) pour expliquer les problèmes complexes et suggérer des actions.
- **Assistant de Refactoring**: Corrections en un clic pour les problèmes d'automation courants.
- **Support Bilingue**: Support complet de l'anglais et du français pour l'interface et les explications IA.

### 💾 Installation
1.  **HACS (Recommandé)**:
    - Allez dans HACS > Intégrations.
    - Cliquez sur les trois points en haut à droite > Dépôts personnalisés.
    - Ajoutez `https://github.com/JeanMarc-Labs/ha-config-auditor` en tant qu'**Intégration**.
    - Recherchez **HACA** et installez.
2.  **Manuel**:
    - Copiez le dossier `config_auditor` dans votre répertoire `custom_components`.
3.  **Configuration**:
    - Redémarrez Home Assistant.
    - Allez dans Paramètres > Appareils et services > Ajouter l'intégration > Recherchez **HACA**.

### 🚀 Utilisation
Accédez au panneau **H.A.C.A** depuis votre barre latérale pour voir votre Score de Santé et le détail des problèmes. Utilisez le bouton "Expliquer par l'IA" pour obtenir des conseils personnalisés.
