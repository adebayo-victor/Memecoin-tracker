import requests
import time
from tabulate import tabulate
import os
import json

API_KEY = "8SY2NPH52ESRP5XAVG3EZNBTHRWTTHB94Y"

def get_wallets():
    """Load wallets from wallets.json"""
    if not os.path.exists("wallets.json"):
        return {"wallets": []}
    try:
        with open("wallets.json", "r") as f:
            return json.load(f)
    except:
        return {"wallets": []}

def fetch_wallet_transactions(address, limit=5):
    """Fetch last `limit` ERC20 transactions"""
    url = "https://api.etherscan.io/v2/api"
    params = {
        "module": "account",
        "action": "tokentx",
        "address": address,
        "sort": "desc",
        "page": 1,
        "offset": limit,
        "chainid": "1",
        "apikey": API_KEY
    }
    try:
        res = requests.get(url, params=params).json()
        if res.get("status") != "1":
            return []
        return res["result"]
    except Exception as e:
        print("Error fetching transactions:", e)
        return []

def track_wallets():
    wallets_data = get_wallets()
    wallets = wallets_data.get("wallets", [])

    if not wallets:
        print("No wallets saved!")
        return

    last_seen = {w["address"]: 0 for w in wallets}  # track last tx per wallet

    try:
        refresh_input = input("Refresh time (seconds) [default 2]: ").strip()
        duration_input = input("Track duration (seconds) [default 60]: ").strip()
        refresh = int(refresh_input) if refresh_input else 2
        duration = int(duration_input) if duration_input else 60
    except:
        refresh = 2
        duration = 60

    start_time = time.time()

    while True:
        all_tx = []

        for w in wallets:
            txs = fetch_wallet_transactions(w["address"])
            for tx in txs:
                ts = int(tx["timeStamp"])
                if ts > last_seen[w["address"]]:
                    last_seen[w["address"]] = max(last_seen[w["address"]], ts)
                    all_tx.append({
                        "Tag": w["tag"],
                        "Wallet": w["address"],
                        "Token": tx["tokenSymbol"],
                        "Value": int(tx["value"]),
                        "Time": time.strftime('%H:%M:%S', time.localtime(ts)),
                        "timestamp": ts
                    })

        os.system('cls' if os.name == 'nt' else 'clear')

        if all_tx:
            print(tabulate(all_tx, headers="keys", tablefmt="fancy_grid"))
        else:
            print("No new transactions found.")

        # Detect coordinated moves between DIFFERENT wallets only
        grouped = {}
        for tx in all_tx:
            grouped.setdefault(tx["Token"], []).append(tx)

        for token, tx_list in grouped.items():
            if len(tx_list) >= 2:
                tx_list.sort(key=lambda x: x["timestamp"])
                for i in range(len(tx_list)-1):
                    t1 = tx_list[i]
                    t2 = tx_list[i+1]
                    if t1["Wallet"] != t2["Wallet"] and abs(t1["timestamp"] - t2["timestamp"]) <= 60:
                        print(f"\n🚨 Coordinated move detected for token {token} between {t1['Tag']} and {t2['Tag']}")

        if time.time() - start_time >= duration:
            print("\n--- Tracking Ended ---")
            break

        time.sleep(refresh)

if __name__ == "__main__":
    track_wallets()
