from flask import Flask, render_template, request, redirect, url_for
from kiteconnect import KiteConnect
import threading
import time
import os
import pandas as pd
from datetime import datetime, timedelta

app = Flask(__name__)

# -------------------------
# Configuration
# -------------------------
API_KEY = "0qw10pvn638g9jid"
API_SECRET = "8bbev51ab3ov4jfkq0ddhmsw1itviexc"
ACCESS_TOKEN_FILE = "access_token.txt"
REQUEST_TOKEN_FILE = "request_token.txt"

DATA_DIR = "data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

kite = KiteConnect(api_key=API_KEY)

fetching = False
fetch_thread = None
symbol = None

# -------------------------
# Helper Functions
# -------------------------
def file_age_hours(filepath):
    """Return file age in hours."""
    if os.path.exists(filepath):
        mod_time = datetime.fromtimestamp(os.path.getmtime(filepath))
        return (datetime.now() - mod_time).total_seconds() / 3600
    return 9999  # large number means missing or expired


def get_kite():
    """Return Kite object with valid access token."""
    global kite
    if os.path.exists(ACCESS_TOKEN_FILE):
        with open(ACCESS_TOKEN_FILE, "r") as f:
            token = f.read().strip()
            kite.set_access_token(token)
    return kite


def fetch_data_continuously(symbol):
    """Background thread: fetch live data every 5s and save to Excel."""
    global fetching
    kite = get_kite()
    file_path = os.path.join(DATA_DIR, f"{symbol.replace(':', '_')}.csv")

    # Initialize Excel file if not exists
    if not os.path.exists(file_path):
        pd.DataFrame(columns=[
        "Time", "Last Price", "Net Change", "Buy Quantity", 
        "Sell Quantity", "Buy Sell Diff", "Total Bid Qty", "Total Offer Qty"
    ]).to_csv(file_path, index=False)
    # if not os.path.exists(file_path):
    #     pd.DataFrame(columns=["Time", "Last Price", "Total Bid Qty", "Total Offer Qty"]).to_excel(file_path, index=False)

    while fetching:
        try:
            quote = kite.quote(symbol)
            data = quote[symbol]
            bids = sum([b["quantity"] for b in data["depth"]["buy"]])
            offers = sum([s["quantity"] for s in data["depth"]["sell"]])
            last_price = data["last_price"]
            net_change = data["net_change"]
            buy_quantity = data["buy_quantity"]
            sell_quantity = data["sell_quantity"]
            buy_sell_diff = buy_quantity - sell_quantity
            volume = data["volume"]
            oi = data["oi"]
            new_row = {
                "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Last Price": last_price,
                "Net Change": net_change,
                "Volume": volume,
                "OI": oi,
                "Buy Quantity": buy_quantity,
                "Sell Quantity": sell_quantity,
                "Buy Sell Diff": buy_sell_diff,
                "Total Bid Qty": bids,
                "Total Offer Qty": offers
            }

            # Read old CSV if exists, else start new DataFrame
            if os.path.exists(file_path):
                df = pd.read_csv(file_path)
                # Append new data at top
                df = pd.concat([pd.DataFrame([new_row]), df], ignore_index=True)
            else:
                df = pd.DataFrame([new_row])

            # Save updated CSV
            df.to_csv(file_path, index=False)
            # # Check if file exists
            # if os.path.exists(file_path):
            #     # Read existing CSV file
            #     df = pd.read_csv(file_path)
            #     # Append new data at top
            #     df = pd.concat([pd.DataFrame([new_row]), df], ignore_index=True)
            # else:
            #     # Create new DataFrame if file doesn't exist
            #     df = pd.DataFrame([new_row])
            # Append new data at top
            # df = pd.read_excel(file_path)
            # df = pd.concat([pd.DataFrame([new_row]), df], ignore_index=True)
            # df.to_excel(file_path, index=False)

            time.sleep(5)
        except Exception as e:
            print("Error fetching data:", e)
            time.sleep(5)


# -------------------------
# Routes
# -------------------------
@app.route("/")
def index():
    """Main route - check token validity."""
    access_token_age = file_age_hours(ACCESS_TOKEN_FILE)
    if access_token_age < 6:
        return redirect(url_for("symbol_page"))

    # No valid token, show login link
    login_url = kite.login_url()
    return render_template("login.html", login_url=login_url)


@app.route("/callback")
def callback():
    """Handle redirect from Zerodha login."""
    global kite
    request_token = request.args.get("request_token")

    if not request_token:
        return "Missing request_token from Zerodha login."

    with open(REQUEST_TOKEN_FILE, "w") as f:
        f.write(request_token)

    data = kite.generate_session(request_token, api_secret=API_SECRET)
    access_token = data["access_token"]

    with open(ACCESS_TOKEN_FILE, "w") as f:
        f.write(access_token)

    kite.set_access_token(access_token)
    return redirect(url_for("symbol_page"))


@app.route("/symbol")
def symbol_page():
    """Page to enter trading symbol."""
    return render_template("symbol.html")


@app.route("/start", methods=["POST"])
def start():
    """Start background data fetching."""
    global fetching, fetch_thread, symbol
    symbol = request.form.get("symbol").strip()
    if not symbol:
        return "Symbol required!"

    if not fetching:
        fetching = True
        fetch_thread = threading.Thread(target=fetch_data_continuously, args=(symbol,))
        fetch_thread.start()

    return redirect(url_for("data_page"))


@app.route("/stop", methods=["POST"])
def stop():
    """Stop data fetching thread."""
    global fetching
    fetching = False
    return redirect(url_for("data_page"))


@app.route("/data")
def data_page():
    """Display latest data from Excel file."""
    # if symbol:
    #     file_path = os.path.join(DATA_DIR, f"{symbol.replace(':', '_')}.csv")
    #     if os.path.exists(file_path):
    #         df = pd.read_excel(file_path)
    #         data = df.to_dict(orient="records")
    #         return render_template("data.html", data=data, symbol=symbol)
    # return render_template("data.html", data=[], symbol=symbol)
    if symbol:
        file_path = os.path.join(DATA_DIR, f"{symbol.replace(':', '_')}.csv")
        if os.path.exists(file_path):
            try:
                df = pd.read_csv(file_path)
                # Ensure latest data is shown at the top (optional if already done)
                data = df.to_dict(orient="records")
            except Exception as e:
                print(f"Error reading CSV: {e}")
                data = []
            return render_template("data.html", data=data, symbol=symbol)

    # If no file found or symbol is missing
    return render_template("data.html", data=[], symbol=symbol)


if __name__ == "__main__":
    # app.run(port=8000, debug=True)
    app.run()
