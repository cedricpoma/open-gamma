# Routine de Trading Opti-Gamma (SPX)

Cette routine exploite les données CBOE pour anticiper les flux des Market Makers selon la méthode "No Graph First".

## 🕒 Calendrier d'Exécution (Heure Paris)

### 1. Stratégie Matinale (09h00 - 11h00)
*   **Action** : Télécharger le CSV et générer le dashboard.
*   **Objectif** : Identifier la structure "résiduelle" (ce qui reste de la veille).
*   **Analyse** : Repère les gros niveaux (Put Walls / Call Walls) qui ne sont pas 0DTE. Ce sont tes grandes zones hebdomadaires. C'est ta "forêt" pour la journée.

### 2. Le Plan de Combat (15h15 - 15h45) 🚨 **CRUCIAL**
*   **Action** : Télécharger le nouveau CSV juste avant ou pendant l'ouverture US.
*   **Objectif** : Capturer l'apparition des nouvelles options **0DTE**.
*   **Analyse** : C'est ici que le **Zero Gamma (Pivot)** définitif de la journée se dessine. C'est l'étape la plus importante de ta routine.

### 3. Ajustement de Séance (17h00 - 19h00)
*   **Action** : Rafraîchir le CSV si le marché a bougé de plus de 0.5%.
*   **Objectif** : Voir si les Dealers ont déplacé leurs "murs" pour s'ajuster au prix.
*   **Analyse** : Un Magnet qui se déplace dans le sens du prix confirme la tendance. Un Magnet qui reste fixe malgré le mouvement fatigue la tendance.

### 4. Anticipation du "Fixing" (20h30 - 21h30)
*   **Action** : Dernier rafraîchissement avant la fin de séance.
*   **Objectif** : Analyser le **Panneau CHARM** pour les 60 dernières minutes.
*   **Analyse** : 
    *   Si le Charm est **Turquoise** : Probabilité de rachat forcé (Pump de fin de séance).
    *   Si le Charm est **Orange** : Probabilité de liquidation (Dump de fin de séance).

### 5. Debrief Post-Clôture (22h30)
*   **Action** : Générer le dashboard après le fixing final.
*   **Objectif** : Voir qui a gagné la bataille.
*   **Analyse** : Est-ce qu'on clôture en zone Bleue (Calme) ou Orange (Instable) ? Cela définit le biais pour l'ouverture du lendemain matin.

---

## 📊 Rappel des Codes Visuels

| Élément | Couleur / Visuel | Signification |
| :--- | :--- | :--- |
| **Zone Bleue** | Haut du panneau Gamma | **Long Gamma** : Marché stable, frein au mouvement. |
| **Zone Orange** | Bas du panneau Gamma | **Short Gamma** : Marché explosif, accélération. |
| **Ligne Noire** | Pointillé (Heatmaps) | **Zero Gamma/Charm** : Le pivot mathématique (Flip Point). |
| **Zone Turquoise** | Panneau Charm | **Achat mécanique** lié au temps qui passe. |
| **Zone Or/Jaune** | Panneau Charm | **Vente mécanique** liée au temps qui passe. |
| **Ligne Rouge** | Pointillé Horizontal | **Ton Prix (Spot)**. Ta position dans la structure. |

---
*Note : Les données CBOE gratuites ont un délai de 15 minutes. Ton graphique temps réel te montre où tu es, le dashboard te montre ce qu'il va se passer si tu y restes.*
