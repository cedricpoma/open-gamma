# ⚡ Guide d'Utilisation — RADAR CVD

## 1. Lancement

```powershell
cd c:\projet\open-gamma
.\venv\Scripts\python.exe radar_cvd.py
```

Au lancement, le radar :
1. Se connecte automatiquement à Tastytrade (OAuth2)
2. Détecte le contrat front-month `/ES` (via API)
3. Détecte la session CET en cours (Matin / Soir)
4. **Session Matin** : te demande la Base statique (ex: `3.73`)
5. Démarre l'affichage live + historique

**Ctrl+C** pour arrêter proprement.

---

## 2. Calcul de la Base Statique (Session Matin)

Le matin, le SPX est fermé. Tu dois entrer la Base manuellement :

```
Base = /ES (settlement vendredi) − SPX (clôture vendredi)
```

**Où trouver ces valeurs :**
| Donnée | Source |
|:---|:---|
| Settlement /ES | [cmegroup.com/settlements](https://www.cmegroup.com/markets/equities/sp/e-mini-sandp500.settlements.html) |
| Clôture SPX | [cboe.com](https://www.cboe.com/tradable_products/sp_500/) |

**Exemple :** /ES = 6743.75, SPX = 6740.02 → Base = **+3.73**

---

## 3. Lecture de l'Affichage

### Header Live (en haut)
Rafraîchi 4×/sec — montre l'état actuel :

| Champ | Description |
|:---|:---|
| **/ESH26:XCME** | Prix mid + spread (bid × ask) |
| **CVD** | Cumulative Volume Delta actuel + ratio Buy%/Sell% + nombre de trades |
| **BASIS** | Écart /ES − SPX (statique le matin, live le soir) |
| **SPX** | Affiché seulement en session soir (15h30-22h) |

### Tableau Historique (en bas)
Snapshot toutes les **15 secondes** (configurable), max 25 lignes :

| Colonne | Signification |
|:---|:---|
| **Heure** | Horodatage du snapshot |
| **/ES** | Prix mid à cet instant |
| **CVD** | CVD cumulé (🟢 positif = acheteurs dominent, 🔴 négatif = vendeurs dominent) |
| **ΔCVD** | ⭐ **Momentum** — variation du CVD depuis le snapshot précédent. `▲ vert` = pression acheteuse accélère, `▼ rouge` = pression vendeuse accélère |
| **Basis** | Valeur de la base à cet instant |
| **Buy%** | % des volumes classifiés comme achats agressifs (🟢 >55%, 🔴 <45%) |
| **Trades** | Nombre total de trades traités depuis le reset |

---

## 4. Signaux de Trading

### CVD — Pression directionnelle

| Pattern | Signal | Action |
|:---|:---|:---|
| CVD monte régulièrement (+) | Achats agressifs dominants | Biais haussier, confirme breakout |
| CVD chute régulièrement (−) | Ventes agressives dominantes | Biais baissier, confirme breakdown |
| CVD plat / oscille autour de 0 | Pas de direction claire | Range → Attendre |
| **Prix ↑ mais CVD ↓** | 🚨 **Divergence baissière** — rally sans achats | Fade potentiel |
| **Prix ↓ mais CVD ↑** | 🚨 **Divergence haussière** — absorption acheteuse | Rebond potentiel |

### ΔCVD — Momentum (colonne clé)

| Pattern | Lecture |
|:---|:---|
| Série de ▲ verts qui grossissent | Achats qui **accélèrent** → mouvement fort |
| ▲ verts qui diminuent | Achats qui **ralentissent** → essoufflement |
| Passage de ▲ vert à ▼ rouge | **Renversement de pression** → attention |
| Série de ▼ rouges qui grossissent | Ventes qui **accélèrent** → sell-off en cours |

### BASIS — Premium des futures

| Pattern | Lecture |
|:---|:---|
| Basis s'élargit (ex: +3 → +6) | Demand for leverage → anticipation haussière |
| Basis se comprime (ex: +5 → +2) | Réduction du premium → prudence |
| Basis négatif | 🚨 Stress extrême — futures sous le cash |

---

## 5. Intégration avec le Dashboard GEX

Le radar est ta **gâchette micro** (confirmation Order Flow) :

1. **Dashboard OpenGamma** → tu identifies un setup (Strike Reject, Expansion, Vanna Squeeze)
2. **Radar CVD** → tu confirmes le timing d'entrée :

| Setup GEX | Confirmation CVD requise |
|:---|:---|
| LONG | CVD positif + Buy% > 50% + ΔCVD ▲ vert |
| SHORT | CVD négatif + Sell% > 50% + ΔCVD ▼ rouge |
| Fade (Long Gamma) | Divergence CVD vs Prix |

> **Règle d'or : ne prends JAMAIS un trade contre le CVD.**
> Si ton setup GEX dit LONG mais le CVD est fortement négatif avec Sell > 60%, **attends**.

---

## 6. Sessions et Reset CVD

| Session | Horaires CET | Base | Reset CVD |
|:---|:---|:---|:---|
| ☀ **Matin** | 08h00 − 14h00 | Statique (saisie manuelle) | 09h00 |
| 🌙 **Soir** | 15h30 − 22h00 | Dynamique (Mid /ES − SPX live) | 15h30 |
| ⛔ **Fermé** | Autre | — | — |

Le CVD et l'historique se réinitialisent automatiquement au changement de session.

---

## 7. Configuration

Les paramètres sont modifiables en haut de `radar_cvd.py` :

```python
SNAPSHOT_INTERVAL = 15    # secondes entre chaque snapshot
MAX_HISTORY_ROWS = 25     # lignes max dans l'historique
FIRST_SNAPSHOT_DELAY = 5  # délai avant le premier snapshot
```
