# H.A.C.A - Home Assistant Config Auditor

[![GitHub Release](https://img.shields.io/github/v/release/JeanMarc-Labs/ha-config-auditor?style=flat-square)](https://github.com/JeanMarc-Labs/ha-config-auditor/releases)
[![License](https://img.shields.io/github/license/JeanMarc-Labs/ha-config-auditor?style=flat-square)](LICENSE)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange?style=flat-square)](https://hacs.xyz/)

[English 🇬🇧](README.md)

---

**Home Assistant Config Auditor (H.A.C.A)** est une intégration puissante conçue pour vous aider à maintenir une installation Home Assistant saine, sécurisée et performante. Elle analyse en profondeur vos fichiers de configuration, identifie les violations des bonnes pratiques et fournit des outils de refactoring automatisés pour corriger les problèmes en un clic.

> [!WARNING]
> **H.A.C.A est actuellement en cours de développement actif.**
> Toute modification effectuée via cet outil doit être réalisée en connaissance de cause. **Effectuez toujours une sauvegarde complète de Home Assistant avant d'utiliser les outils de refactoring.**
> L'équipe H.A.C.A décline toute responsabilité en cas de plantage de Home Assistant, de perte de données ou de problèmes de configuration résultant de l'utilisation de cette intégration. Utilisation à vos propres risques.
>
> **H.A.C.A n'est pas affilié, approuvé, recommandé ou soutenu par le projet Home Assistant.**
>
> Cette intégration personnalisée est fournie telle quelle, sans aucune garantie.

## ✨ Fonctionnalités Clés

### 🔍 Analyseurs Spécialisés
*   **Analyseur d'Automation** : Analyse votre fichier `automations.yaml` pour détecter l'utilisation de `device_id` périmés, les modes inefficaces (ex: utiliser `parallel` quand `restart` est préférable) et les références à des entités "zombies".
*   **Analyseur de Performance** : Surveille les taux de déclenchement et identifie les entités "bruyantes" qui saturent votre base de données. Il détecte les boucles d'automatisation potentielles et suggère des optimisations.
*   **Auditeur de Sécurité** : Signale automatiquement les secrets, clés API et mots de passe écrits "en dur" qui devraient être dans `secrets.yaml`. Il avertit également de l'exposition de données sensibles dans les services de notification.
*   **Moniteur de Santé des Entités** : Suit les entités indisponibles ou inconnues dans tout votre système, vous aidant à garder vos tableaux de bord et automatisations propres.

### 🤖 IA Assistante & Refactoring
*   **IA Explique** : Intégrée au moteur de conversation de Home Assistant (OpenAI, Gemini, etc.), HACA peut expliquer *pourquoi* une erreur est signalée et fournir des conseils personnalisés.
*   **Assistant de Refactoring** : Appliquez des corrections directement depuis l'interface. Convertissez les automatisations basées sur les appareils en automatisations basées sur les entités, ou optimisez les modes d'automatisation automatiquement.
*   **Sauvegarde & Sécurité** : Chaque correction automatisée crée une sauvegarde de votre configuration, permettant une restauration facile si nécessaire.

## 💾 Installation Pas à Pas

### Méthode 1 : HACS (Recommandée)
1.  Assurez-vous que [HACS](https://hacs.xyz/) est installé et configuré.
2.  Ouvrez **HACS** dans votre barre latérale.
3.  Cliquez sur **Intégrations**.
4.  Cliquez sur les **trois points** en haut à droite et sélectionnez **Dépôts personnalisés**.
5.  Collez l'URL suivante : `https://github.com/JeanMarc-Labs/ha-config-auditor`
6.  Sélectionnez **Intégration** comme catégorie et cliquez sur **Ajouter**.
7.  Cliquez sur **Installer** sur la carte H.A.C.A qui apparaît.
8.  **Redémarrez** Home Assistant.

### Méthode 2 : Installation Manuelle
1.  Téléchargez la dernière version depuis la [page des releases](https://github.com/JeanMarc-Labs/ha-config-auditor/releases).
2.  Extrayez l'archive et copiez le dossier `custom_components/config_auditor` dans le répertoire `custom_components` de votre instance Home Assistant.
3.  **Redémarrez** Home Assistant.

### ⚙️ Configuration Finale
Après l'installation et le redémarrage :
1.  Allez dans **Paramètres** > **Appareils et services**.
2.  Cliquez sur **+ Ajouter l'intégration**.
3.  Recherchez **HACA** (ou **Home Assistant Config Auditor**).
4.  Suivez les étapes de configuration.

## 🚀 Utilisation

### Le Panneau H.A.C.A
Une fois configuré, un nouvel élément **H.A.C.A** apparaîtra dans votre barre latérale.
*   **Vue d'ensemble** : Consultez votre **Score de Santé** global.
*   **Liste des Problèmes** : Parcourez les rapports détaillés de tous les analyseurs.
*   **Détails** : Cliquez sur n'importe quel problème pour voir une analyse approfondie, des recommandations et (si disponible) une correction automatisée.

### Assistance IA
Si vous avez un agent de conversation IA configuré dans Home Assistant (comme OpenAI ou Google Generative AI), H.A.C.A affichera un bouton **"Expliquer par l'IA"**. En cliquant, vous obtiendrez une explication en langage naturel du problème technique.

### Capteurs
HACA fournit plusieurs capteurs de diagnostic, notamment :
*   `sensor.haca_health_score` : Un pourcentage représentant la santé globale de votre configuration.
*   `sensor.haca_total_issues` : Le nombre total de problèmes détectés.
