
import os
import asyncio
from dotenv import load_dotenv
import httpx
from tastytrade import Session, DXLinkStreamer
from tastytrade.instruments import NestedOptionChain
from tastytrade.dxfeed import Quote, Greeks, Summary
from tastytrade import API_URL, API_VERSION
from datetime import date

load_dotenv()
USERNAME = os.getenv("TASTY_USERNAME")
PASSWORD = os.getenv("TASTY_PASSWORD")

def create_manual_session(username, password):
    resp = httpx.post(
        "https://api.tastyworks.com/sessions",
        json={"login": username, "password": password, "remember-me": True},
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        timeout=10
    )
    if resp.status_code != 201:
        print(f"Login failed: {resp.status_code}")
        return None
    data = resp.json().get('data', {})
    session_token = data.get('session-token')
    session = Session.__new__(Session)
    session.session_token = session_token
    session.base_url = API_URL
    session.is_test = False
    session.proxy = None
    session.provider_secret = ""
    session.refresh_token = data.get('remember-token', '')
    headers = {
        "Accept": "application/json", 
        "Content-Type": "application/json",
        "Authorization": f"{session_token}",
        "Accept-Version": API_VERSION
    }
    session.client = httpx.Client(base_url=API_URL, headers=headers)
    session.async_client = httpx.AsyncClient(base_url=API_URL, headers=headers)
    
    t_resp = session.client.get("/api-quote-tokens")
    if t_resp.status_code == 200:
        token_data = t_resp.json()['data']
        session.streamer_token = token_data.get('token')
        session.dxlink_url = token_data.get('dxlink-url')
    return session

async def test_fetch():
    session = create_manual_session(USERNAME, PASSWORD)
    if not session:
        print("Failed to create session")
        return
    
    symbol = "SPX"
    chains = NestedOptionChain.get(session, symbol)
    chain = chains[0]
    exp = chain.expirations[0]
    strike = exp.strikes[0]
    syms = [strike.call_streamer_symbol, strike.put_streamer_symbol, symbol]
    
    async with DXLinkStreamer(session) as streamer:
        await streamer.subscribe(Quote, [symbol])
        await streamer.subscribe(Greeks, syms)
        await asyncio.sleep(5)
        
        print(f"Quotes: {len(streamer.quotes)}")
        print(f"Greeks: {len(streamer.greeks)}")
        if symbol in streamer.quotes:
            print(f"Spot: {streamer.quotes[symbol].bidPrice}")

if __name__ == "__main__":
    asyncio.run(test_fetch())
