"""
╔══════════════════════════════════════════════════════════════╗
║  RADAR CVD — Web Dashboard Backend                          ║
║  Cumulative Volume Delta (Lee-Ready) + Basis (/ES vs SPX)   ║
║                                                              ║
║  Backend : WebSocket ws://localhost:8765                      ║
║  Frontend: ouvrir radar.html dans le navigateur              ║
╚══════════════════════════════════════════════════════════════╝

Usage :
  python radar_cvd.py

Ctrl+C pour arrêter.
"""

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

import os
from dotenv import load_dotenv

load_dotenv()

TASTY_PROVIDER_SECRET = os.getenv("TASTY_PROVIDER_SECRET", "")
TASTY_REFRESH_TOKEN = os.getenv("TASTY_REFRESH_TOKEN", "")
SPX_SYMBOL = "SPX"

# ═══════════════════════════════════════════════════════════════
# IMPORTS
# ═══════════════════════════════════════════════════════════════

import asyncio
import calendar
import csv
import json
import sys
import webbrowser
from datetime import datetime, date, time as dtime
from decimal import Decimal
from zoneinfo import ZoneInfo
from collections import deque
from pathlib import Path

from tastytrade import Session, DXLinkStreamer
from tastytrade.dxfeed import Quote, Trade
from tastytrade.instruments import Future

import websockets
from websockets.asyncio.server import serve as ws_serve

# ═══════════════════════════════════════════════════════════════
# CONSTANTES
# ═══════════════════════════════════════════════════════════════

CET = ZoneInfo("Europe/Paris")

# Sessions CET
MORNING_START = dtime(8, 0)
MORNING_END = dtime(14, 0)
MORNING_CVD_RESET = dtime(9, 0)

EVENING_START = dtime(15, 30)
EVENING_END = dtime(22, 0)
EVENING_CVD_RESET = dtime(15, 30)

# WebSocket
WS_HOST = "localhost"
WS_PORT = 8765
TICK_BROADCAST_INTERVAL = 0.25  # secondes

# Whale tracking
WHALE_MIN_SIZE = 20  # taille min pour considérer un ordre comme "baleine"

# Snapshots
SNAPSHOT_INTERVAL = 30
MAX_HISTORY_ROWS = 60
FIRST_SNAPSHOT_DELAY = 5

# CSV logging
CSV_DIR = Path(__file__).parent / "logs"
CSV_HEADERS = [
    "date", "time", "es_mid", "cvd", "cvd_delta",
    "vol_30s", "avg_size", "whale_delta",
    "basis", "basis_type", "buy_pct", "trades",
]

# Reconnexion DXLink
RECONNECT_BASE_DELAY = 1
RECONNECT_MAX_DELAY = 60

# /ES month codes
ES_MONTH_CODES = {3: "H", 6: "M", 9: "U", 12: "Z"}

# Clients WebSocket connectés
ws_clients: set = set()


def log(msg: str):
    ts = datetime.now(CET).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ═══════════════════════════════════════════════════════════════
# DÉTECTION FRONT-MONTH /ES
# ═══════════════════════════════════════════════════════════════

def get_third_friday(year: int, month: int) -> date:
    """Retourne le 3ème vendredi du mois (jour d'expiration /ES)."""
    cal = calendar.monthcalendar(year, month)
    # Vendredi = index 4 dans monthcalendar
    fridays = [week[4] for week in cal if week[4] != 0]
    return date(year, month, fridays[2])  # 3ème vendredi (index 2)


def get_front_month_es_symbol() -> str:
    """Calcul local du front-month en utilisant le vrai 3ème vendredi.
    Le jour de l'expiration, on bascule déjà sur le contrat suivant
    car le volume a migré.
    """
    today = date.today()
    year = today.year
    delivery_months = [3, 6, 9, 12]

    for dm in delivery_months:
        expiry = get_third_friday(year, dm)
        # On bascule sur le contrat suivant DÈS le jour d'expiration
        if expiry > today:
            month_code = ES_MONTH_CODES[dm]
            year_digit = year % 10
            return f"/ES{month_code}{year_digit}"

    # Tous les contrats de l'année sont expirés → mars année suivante
    next_year = year + 1
    next_year_digit = next_year % 10
    return f"/ESH{next_year_digit}"


def get_front_month_via_api(session: Session) -> str:
    try:
        futures = Future.get(session, product_codes=["ES"])
        if futures:
            if not isinstance(futures, list):
                futures = [futures]
            today = date.today()
            active = [
                f for f in futures
                if f.expiration_date and f.expiration_date > today and f.active
            ]
            if active:
                active.sort(key=lambda f: f.expiration_date)
                symbol = active[0].streamer_symbol or active[0].symbol
                log(f"✓ Front-month via API : {symbol}")
                return symbol
    except Exception as e:
        log(f"⚠ API front-month failed: {e}")

    symbol = get_front_month_es_symbol()
    log(f"⚠ Fallback calcul local : {symbol}")
    return symbol


# ═══════════════════════════════════════════════════════════════
# DÉTECTION SESSION CET
# ═══════════════════════════════════════════════════════════════

def get_current_session() -> str:
    now = datetime.now(CET).time()
    if MORNING_START <= now < MORNING_END:
        return "morning"
    elif EVENING_START <= now < EVENING_END:
        return "evening"
    return "closed"


def get_cvd_reset_time() -> dtime:
    session = get_current_session()
    if session == "morning":
        return MORNING_CVD_RESET
    elif session == "evening":
        return EVENING_CVD_RESET
    return MORNING_CVD_RESET


# ═══════════════════════════════════════════════════════════════
# MOTEUR CVD (Lee-Ready Algorithm)
# ═══════════════════════════════════════════════════════════════

class CVDEngine:
    def __init__(self):
        self.reset()

    def reset(self):
        self.cvd: int = 0
        self.last_trade_price: Decimal = Decimal("0")
        self.trade_count: int = 0
        self.buy_volume: int = 0
        self.sell_volume: int = 0

        self.es_bid: Decimal = Decimal("0")
        self.es_ask: Decimal = Decimal("0")
        self.es_mid: float = 0.0

        self.spx_bid: Decimal = Decimal("0")
        self.spx_ask: Decimal = Decimal("0")
        self.spx_mid: float = 0.0

        self.static_basis: float | None = None
        self.last_reset_date: date | None = None
        self.last_reset_session: str = ""

        # ── Compteurs par période (reset chaque snapshot) ──
        self.reset_period()

    def reset_period(self):
        """Reset les compteurs spécifiques à la fenêtre 30s."""
        self.period_volume: int = 0       # VOL 30s total
        self.period_trades: int = 0       # nombre de trades dans la période
        self.whale_buy: int = 0           # volume achats ≥ WHALE_MIN_SIZE
        self.whale_sell: int = 0          # volume ventes ≥ WHALE_MIN_SIZE

    def update_es_quote(self, bid: Decimal, ask: Decimal):
        if bid and bid > 0:
            self.es_bid = bid
        if ask and ask > 0:
            self.es_ask = ask
        if self.es_bid > 0 and self.es_ask > 0:
            self.es_mid = float(self.es_bid + self.es_ask) / 2.0

    def update_spx_quote(self, bid: Decimal, ask: Decimal):
        if bid and bid > 0:
            self.spx_bid = bid
        if ask and ask > 0:
            self.spx_ask = ask
        if self.spx_bid > 0 and self.spx_ask > 0:
            self.spx_mid = float(self.spx_bid + self.spx_ask) / 2.0

    def process_trade(self, price: Decimal, size: int | None):
        if size is None or size == 0:
            return "NEUTRAL"

        volume = abs(size)
        self.trade_count += 1
        self.period_trades += 1
        self.period_volume += volume
        classification = "NEUTRAL"

        if self.es_bid > 0 and self.es_ask > 0:
            if price >= self.es_ask:
                self.cvd += volume
                self.buy_volume += volume
                classification = "BUY"
            elif price <= self.es_bid:
                self.cvd -= volume
                self.sell_volume += volume
                classification = "SELL"
            else:
                if self.last_trade_price > 0:
                    if price > self.last_trade_price:
                        self.cvd += volume
                        self.buy_volume += volume
                        classification = "BUY"
                    elif price < self.last_trade_price:
                        self.cvd -= volume
                        self.sell_volume += volume
                        classification = "SELL"

        # Whale tracking (≥ WHALE_MIN_SIZE lots)
        if classification == "BUY" and volume >= WHALE_MIN_SIZE:
            self.whale_buy += volume
        elif classification == "SELL" and volume >= WHALE_MIN_SIZE:
            self.whale_sell += volume

        self.last_trade_price = price
        return classification

    def get_basis(self, session: str) -> tuple[float | None, str]:
        if session == "morning":
            if self.static_basis is not None:
                return self.static_basis, "statique"
            return None, "no-basis"
        elif session == "evening":
            if self.es_mid > 0 and self.spx_mid > 0:
                return self.es_mid - self.spx_mid, "live"
            elif self.static_basis is not None:
                return self.static_basis, "statique (fallback)"
            return None, "en attente"
        return None, "fermé"

    def check_and_reset(self) -> bool:
        now = datetime.now(CET)
        today = now.date()
        current_session = get_current_session()
        current_time = now.time()

        should_reset = False
        if self.last_reset_date != today:
            should_reset = True
        if self.last_reset_session != current_session and current_session != "closed":
            should_reset = True

        if should_reset and current_session != "closed":
            reset_time = get_cvd_reset_time()
            if current_time >= reset_time:
                self.cvd = 0
                self.buy_volume = 0
                self.sell_volume = 0
                self.trade_count = 0
                self.last_reset_date = today
                self.last_reset_session = current_session
                return True
        return False


# ═══════════════════════════════════════════════════════════════
# AUTHENTIFICATION
# ═══════════════════════════════════════════════════════════════

def create_session() -> Session | None:
    if not TASTY_PROVIDER_SECRET or not TASTY_REFRESH_TOKEN:
        log("✗ Credentials OAuth2 manquants! Vérifiez .env")
        return None
    try:
        session = Session(
            provider_secret=TASTY_PROVIDER_SECRET,
            refresh_token=TASTY_REFRESH_TOKEN,
            is_test=False,
        )
        log("✓ Session OAuth2 établie")
        return session
    except Exception as e:
        log(f"✗ Échec auth OAuth2: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
# WEBSOCKET SERVER
# ═══════════════════════════════════════════════════════════════

async def broadcast(message: dict):
    """Broadcast JSON à tous les clients WebSocket connectés."""
    if not ws_clients:
        return
    data = json.dumps(message)
    disconnected = set()
    for client in ws_clients:
        try:
            await client.send(data)
        except Exception:
            disconnected.add(client)
    ws_clients.difference_update(disconnected)


async def ws_handler(websocket):
    """Gère une connexion WebSocket entrante."""
    ws_clients.add(websocket)
    log(f"🌐 Client connecté ({len(ws_clients)} total)")
    try:
        # Envoyer l'historique existant au nouveau client
        if hasattr(ws_handler, '_history'):
            snapshots = list(ws_handler._history)
            await websocket.send(json.dumps({
                "type": "history",
                "snapshots": snapshots
            }))
        async for _ in websocket:
            pass  # On ne reçoit rien du client, juste keep-alive
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        ws_clients.discard(websocket)
        log(f"🌐 Client déconnecté ({len(ws_clients)} restants)")


# ═══════════════════════════════════════════════════════════════
# SNAPSHOT + TICK DATA
# ═══════════════════════════════════════════════════════════════

def build_tick_data(engine: CVDEngine, es_symbol: str) -> dict:
    """Construit le payload JSON pour un tick live."""
    now = datetime.now(CET)
    session_name = get_current_session()
    basis_val, basis_type = engine.get_basis(session_name)
    total_vol = engine.buy_volume + engine.sell_volume
    buy_pct = (engine.buy_volume / total_vol * 100) if total_vol > 0 else 50.0

    return {
        "type": "tick",
        "es_symbol": es_symbol,
        "es_mid": engine.es_mid,
        "es_bid": float(engine.es_bid),
        "es_ask": float(engine.es_ask),
        "cvd": engine.cvd,
        "buy_pct": buy_pct,
        "basis": basis_val,
        "basis_type": basis_type,
        "spx_mid": engine.spx_mid,
        "session": session_name,
        "time": now.strftime("%H:%M:%S"),
        "trade_count": engine.trade_count,
    }


def take_snapshot(engine: CVDEngine, history: deque, last_cvd: list) -> dict:
    """Prend un snapshot et retourne les données."""
    now = datetime.now(CET)
    session_name = get_current_session()
    basis_val, basis_type = engine.get_basis(session_name)
    total_vol = engine.buy_volume + engine.sell_volume
    buy_pct = (engine.buy_volume / total_vol * 100) if total_vol > 0 else 50.0

    cvd_delta = engine.cvd - last_cvd[0]
    last_cvd[0] = engine.cvd

    # Métriques de période (30s) — conversion int() pour gérer les Decimal
    vol_30s = int(engine.period_volume)
    period_trades = int(engine.period_trades)
    avg_size = round(vol_30s / period_trades, 1) if period_trades > 0 else 0.0
    whale_delta = int(engine.whale_buy - engine.whale_sell)

    log(f"📊 period_vol={vol_30s}, period_trades={period_trades}, whale_buy={int(engine.whale_buy)}, whale_sell={int(engine.whale_sell)}")

    snapshot = {
        "type": "snapshot",
        "time": now.strftime("%H:%M:%S"),
        "es_mid": engine.es_mid,
        "cvd": int(engine.cvd),
        "cvd_delta": int(cvd_delta),
        "basis": basis_val,
        "basis_type": basis_type,
        "buy_pct": round(buy_pct, 1),
        "trades": int(engine.trade_count),
        "vol_30s": vol_30s,
        "avg_size": avg_size,
        "whale_delta": whale_delta,
    }
    history.append(snapshot)

    # Enregistrer dans le CSV
    save_snapshot_csv(snapshot)

    # Reset les compteurs de période pour la prochaine fenêtre
    engine.reset_period()

    return snapshot


def save_snapshot_csv(snapshot: dict):
    """Ajoute un snapshot au fichier CSV du jour."""
    today = datetime.now(CET).strftime("%Y-%m-%d")
    CSV_DIR.mkdir(exist_ok=True)
    csv_path = CSV_DIR / f"radar_{today}.csv"

    file_exists = csv_path.exists()
    try:
        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            if not file_exists:
                writer.writeheader()
            row = {
                "date": today,
                "time": snapshot.get("time", ""),
                "es_mid": snapshot.get("es_mid", ""),
                "cvd": snapshot.get("cvd", ""),
                "cvd_delta": snapshot.get("cvd_delta", ""),
                "vol_30s": snapshot.get("vol_30s", ""),
                "avg_size": snapshot.get("avg_size", ""),
                "whale_delta": snapshot.get("whale_delta", ""),
                "basis": snapshot.get("basis", ""),
                "basis_type": snapshot.get("basis_type", ""),
                "buy_pct": snapshot.get("buy_pct", ""),
                "trades": snapshot.get("trades", ""),
            }
            writer.writerow(row)
    except Exception as e:
        log(f"⚠ CSV write error: {e}")


# ═══════════════════════════════════════════════════════════════
# BOUCLE PRINCIPALE ASYNC
# ═══════════════════════════════════════════════════════════════

async def run_radar():
    """Boucle principale : CVD engine + broadcast WebSocket."""
    reconnect_delay = RECONNECT_BASE_DELAY
    engine = CVDEngine()

    # Demander la base statique si session matin
    session_name = get_current_session()
    if session_name == "morning":
        log("☀ SESSION MATIN détectée — Base statique")
        try:
            user_input = input("  Entrez la Base /ES-SPX (ex: 3.73) ou Entrée pour ignorer : ").strip()
            if user_input:
                engine.static_basis = float(user_input)
                log(f"✓ Base statique = {engine.static_basis}")
            else:
                log("⚠ Pas de base statique — colonne BASIS sera vide")
        except (ValueError, EOFError):
            log("⚠ Valeur invalide — pas de base statique")
    elif session_name == "evening":
        log("🌙 SESSION SOIR détectée — Base dynamique")
    else:
        log("⚠ Hors session — monitoring uniquement")

    # Historique
    history: deque = deque(maxlen=MAX_HISTORY_ROWS)
    ws_handler._history = history  # Rendre accessible au handler WS
    last_cvd = [0]

    while True:
        try:
            # 1. Auth
            log("Connexion à Tastytrade...")
            session = create_session()
            if not session:
                log(f"Retry dans {reconnect_delay}s...")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, RECONNECT_MAX_DELAY)
                continue

            # 2. Front-month
            es_symbol = get_front_month_via_api(session)
            log(f"✓ Contrat actif : {es_symbol}")

            # 3. DXLink
            async with DXLinkStreamer(session) as streamer:
                log("✓ DXLink connecté")

                await streamer.subscribe(Quote, [es_symbol])
                await streamer.subscribe(Trade, [es_symbol])
                await streamer.subscribe(Quote, [SPX_SYMBOL])

                log(f"✓ Abonnements : {es_symbol} (Quote+Trade), {SPX_SYMBOL} (Quote)")

                reconnect_delay = RECONNECT_BASE_DELAY

                last_snapshot_time = asyncio.get_running_loop().time() - SNAPSHOT_INTERVAL + FIRST_SNAPSHOT_DELAY
                last_tick_time = 0.0

                # 4. Boucle de réception
                while True:
                    # Reset CVD si nécessaire
                    if engine.check_and_reset():
                        history.clear()
                        last_cvd[0] = 0
                        await broadcast({"type": "reset"})
                        log("🔄 CVD reset (nouvelle session)")

                    # Poll events — drain ALL queued events to avoid
                    # missing trades during high-volatility bursts
                    while True:
                        q = streamer.get_event_nowait(Quote)
                        if not q:
                            break
                        if q.event_symbol == es_symbol:
                            engine.update_es_quote(q.bid_price, q.ask_price)
                        elif q.event_symbol == SPX_SYMBOL:
                            engine.update_spx_quote(q.bid_price, q.ask_price)

                    while True:
                        t = streamer.get_event_nowait(Trade)
                        if not t:
                            break
                        if t.event_symbol == es_symbol:
                            engine.process_trade(t.price, t.size)

                    now_loop = asyncio.get_running_loop().time()

                    # Broadcast tick (~4×/sec)
                    if (now_loop - last_tick_time) >= TICK_BROADCAST_INTERVAL:
                        tick_data = build_tick_data(engine, es_symbol)
                        await broadcast(tick_data)
                        last_tick_time = now_loop

                    # Snapshot périodique
                    if (now_loop - last_snapshot_time) >= SNAPSHOT_INTERVAL:
                        if engine.es_mid > 0:
                            snapshot = take_snapshot(engine, history, last_cvd)
                            await broadcast(snapshot)
                            log(f"📸 Snapshot #{len(history)} — CVD={engine.cvd:+d}, /ES={engine.es_mid:.2f}")
                        last_snapshot_time = now_loop

                    await asyncio.sleep(0.05)

        except KeyboardInterrupt:
            log("⚡ Radar arrêté.")
            break
        except asyncio.CancelledError:
            log("⚡ Radar annulé.")
            break
        except Exception as e:
            log(f"✗ Erreur: {e}")
            log(f"Reconnexion dans {reconnect_delay}s...")
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, RECONNECT_MAX_DELAY)


# ═══════════════════════════════════════════════════════════════
# POINT D'ENTRÉE
# ═══════════════════════════════════════════════════════════════

async def main():
    print("=" * 60)
    print("  ⚡ RADAR CVD — Web Dashboard")
    print(f"  WebSocket : ws://{WS_HOST}:{WS_PORT}")
    print(f"  Frontend  : radar.html")
    print("  Ctrl+C pour arrêter")
    print("=" * 60)

    # Démarrer le serveur WebSocket
    ws_server = await ws_serve(ws_handler, WS_HOST, WS_PORT)
    log(f"🌐 WebSocket server démarré sur ws://{WS_HOST}:{WS_PORT}")

    # Ouvrir le navigateur automatiquement
    html_path = Path(__file__).parent / "radar.html"
    if html_path.exists():
        webbrowser.open(f"file:///{html_path.resolve()}")
        log(f"🌐 Ouverture de {html_path.name} dans le navigateur")

    # Lancer le radar
    try:
        await run_radar()
    finally:
        ws_server.close()
        await ws_server.wait_closed()
        log("WebSocket server fermé")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBye!")
