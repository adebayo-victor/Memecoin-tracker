import json
import os
import requests
import time
from tabulate import tabulate
from flask import Flask, render_template, request, redirect, session, url_for, jsonify, send_file, make_response
import threading
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()
#tracking bucket and state monitor
TRACKER_RUNNING = False
LIVE_TX_BUFFER = []

app = Flask(__name__)
#credentials
API_KEY = os.getenv("API_KEY")
# wallet saving function
def save_wallets(data):
    with open("wallets.json", "w") as file:
        json.dump(data, file, indent=4)

# wallet loading function
def get_wallets():
    if not os.path.exists("wallets.json"):
        return {"wallets": []}
    try:
        with open("wallets.json", "r") as file:
            return json.load(file)
    except:
        return {"wallets": []}

# wallet adding function
def insert_wallet(address, tag):
    
    data = get_wallets()

    data["wallets"].append({"address": address, "tag": tag})
    save_wallets(data)
    print(f"Wallet saved as {tag}")

# wallet removal function
def commot_wallet(tag):
    data = get_wallets()

    new_list = [w for w in data["wallets"] if w["tag"] != tag]

    if len(new_list) == len(data["wallets"]):
        return "No wallet found with that tag."
    else:
        data["wallets"] = new_list
        save_wallets(data)
        return f"Wallet tagged '{tag}' removed."
    
    

# tag change function
def tag_change(old_tag, new_tag):
    data = get_wallets()
    

    updated = False

    for wallet in data['wallets']:
        if wallet['tag'] == old_tag:
            wallet['tag'] = new_tag
            updated = True
            save_wallets(data)

    if updated:
        return f"Wallet tag changed from {old_tag} → {new_tag}"
    else:
        return "No wallet found with that tag."

    
#wallet tracking function
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
        print(res)
        if res.get("status") != "1":
            return []
        return res["result"]
    except Exception as e:
        print("Error fetching transactions:", e)
        return []

def track_wallets_worker(refresh=2, duration=60):
    global TRACKER_RUNNING, LIVE_TX_BUFFER

    wallets_data = get_wallets()
    wallets = wallets_data.get("wallets", [])

    if not wallets:
        TRACKER_RUNNING = False
        return

    last_seen = {w["address"]: 0 for w in wallets}
    start_time = time.time()

    while TRACKER_RUNNING:
        all_tx = []

        for w in wallets:
            txs = fetch_wallet_transactions(w["address"])
            for tx in txs:
                ts = int(tx["timeStamp"])
                if ts > last_seen[w["address"]]:
                    last_seen[w["address"]] = max(last_seen[w["address"]], ts)

                    event = {
                        "type": "tx",
                        "tag": w["tag"],
                        "wallet": w["address"],
                        "token": tx["tokenSymbol"],
                        "value": int(tx["value"]),
                        "time": time.strftime('%H:%M:%S', time.localtime(ts)),
                        "timestamp": ts
                    }

                    all_tx.append(event)
                    LIVE_TX_BUFFER.append(event)

        # coordinated detection
        grouped = {}
        for tx in all_tx:
            grouped.setdefault(tx["token"], []).append(tx)

        for token, tx_list in grouped.items():
            if len(tx_list) >= 2:
                tx_list.sort(key=lambda x: x["timestamp"])
                for i in range(len(tx_list) - 1):
                    t1, t2 = tx_list[i], tx_list[i + 1]
                    if t1["wallet"] != t2["wallet"] and abs(t1["timestamp"] - t2["timestamp"]) <= 60:
                        alert = {
                            "type": "alert",
                            "token": token,
                            "wallets": [t1["tag"], t2["tag"]],
                            "timestamp": int(time.time())
                        }
                        LIVE_TX_BUFFER.append(alert)

        if time.time() - start_time >= duration:
            TRACKER_RUNNING = False
            break

        time.sleep(refresh)
@app.route("/")
def index():
    return render_template("index.html")
@app.route("/tracker")
def tracker():
    return render_template("tracker1.html")
@app.route("/add_wallet", methods=["POST"])
def add_wallet():
    if request.method == "POST":
        try:
            data = request.json
            address = data["address"]
            tag = data["tag"]
            insert_wallet(address, tag)
            return jsonify({"status_code":"200", "message":"successful"})
        except Exception as e:
            return jsonify({"status_code":"500", "error":f"{e}"})    
@app.route("/remove_wallet", methods=["POST"])
def remove_wallet():
    if request.method == "POST":
        try:
            data = request.json
            print(data)
            tag = data['tag']
            message = commot_wallet(tag)
            return jsonify({"status_code":"200", "message":message})
        except Exception as e:
            return jsonify({"status_code":"500", "error":f"{e}"})  
@app.route("/change_tag", methods=["POST"])
def change_tag():
    if request.method == "POST":
        try:
            data = request.json
            tag = data["tag"]
            new_tag = data["new_tag"]
            message = tag_change(tag, new_tag)
            return jsonify({"status_code":"200", "message":message})
        except Exception as e:
            return jsonify({"status_code":"500", "error":f"{e}"}) 
@app.route("/load_wallets", methods=["POST"])
def load_wallets():
    if request.method == "POST":
        try:
            wallets = get_wallets()
            return jsonify({"status_code":"200", "message":"successful", "data":wallets})
        except Exception as e:
            return jsonify({"status_code":"500", "error":f"{e}"}) 
@app.route("/start_tracking", methods=["POST"])
def start_tracking():
    global TRACKER_RUNNING

    if TRACKER_RUNNING:
        return jsonify({
            "status_code": "409",
            "message": "Tracker loop initiated"
        })

    data = request.json or {}
    refresh = int(data.get("refresh", 2))
    duration = int(data.get("duration", 60))

    TRACKER_RUNNING = True

    thread = threading.Thread(
        target=track_wallets_worker,
        args=(refresh, duration),
        daemon=True
    )
    thread.start()

    return jsonify({
        "status_code": "200",
        "message": "Tracking started"
    })
@app.route("/fetch_live_tx", methods=["POST"])
def fetch_live_tx():
    global LIVE_TX_BUFFER
    if request.method == "POST":
        data = LIVE_TX_BUFFER.copy()
        LIVE_TX_BUFFER.clear()

        return jsonify({
            "status_code": "200",
            "events": data
        })

if __name__ == "__main__":
    app.run(port=7000, debug=True)
# main loop
'''while True:
    print("__MEME COIN TRACKER__\n1. Track wallets\n2. Manage wallets\n3. Exit program")
    user_input = input("=>")

    if user_input == "1":
        track_wallets()
    
    elif user_input == "2":
        while True:
            print("__MEME COIN TRACKER__\n__MANAGE WALLETS__\n1. Add wallet\n2. Remove wallet\n3. Change wallet tag\n4. Load wallets\n5. <- Back")
            wallet_input = input("=>")

            if wallet_input == "1":
                add_wallet()
            elif wallet_input == "2":
                remove_wallet()
            elif wallet_input == "3":
                tag_change()
            elif wallet_input == "4":
                data = get_wallets()
                print(data)
                count = 0
                for item in data["wallets"]:
                    count += 1
                    print("-" * 100)
                    print(f"{count}")
                    print("Address:", item.get("address"))
                    print("Tag:", item.get("tag"))
                    print("-" * 100)
                input("Press Enter to exit...")
            elif wallet_input == "5":
                break
            else:
                print("Invalid input")
    
    elif user_input == "3":
        print("SHUTTING DOWN PROGRAM")
        break

    else:
        print("Invalid input") '''
