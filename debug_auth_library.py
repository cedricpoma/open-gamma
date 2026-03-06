import os
from dotenv import load_dotenv
from tastytrade import Session

load_dotenv()
USERNAME = os.getenv("TASTY_USERNAME")
PASSWORD = os.getenv("TASTY_PASSWORD")

def test_library_login():
    print(f"Attempting login using tastytrade.Session for {USERNAME}...")
    try:
        session = Session(USERNAME, PASSWORD)
        print("Login Successful!")
        print(f"Session Token: {session.session_token[:10]}...")
        if session.streamer_token:
             print(f"Streamer Token: {session.streamer_token[:10]}...")
    except Exception as e:
        print(f"Login Failed via Library: {e}")

if __name__ == "__main__":
    if not USERNAME or not PASSWORD:
        print("Please set TASTY_USERNAME and TASTY_PASSWORD in .env")
    else:
        test_library_login()
