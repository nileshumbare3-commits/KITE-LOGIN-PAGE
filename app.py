from flask import Flask, request, redirect, session, render_template, jsonify
from kiteconnect import KiteConnect
import os
import pandas as pd
from datetime import datetime, timedelta
import numpy as np
import importlib
import inspect
from strategies.base_strategy import BaseStrategy


app = Flask(__name__)
app.secret_key = os.urandom(24)

# Replace with your API key and secret
api_key = "YOUR_API_KEY"
api_secret = "YOUR_API_SECRET"

kite = KiteConnect(api_key=api_key)

# --- Strategy Loading ---
STRATEGIES = {}

def load_strategies():
    """Dynamically loads all strategy classes from the 'strategies' directory."""
    global STRATEGIES
    strategy_files = [f[:-3] for f in os.listdir('strategies') if f.endswith('.py') and f != '__init__.py' and f != 'base_strategy.py']
    for file_name in strategy_files:
        module = importlib.import_module(f'strategies.{file_name}')
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, BaseStrategy) and obj is not BaseStrategy:
                STRATEGIES[file_name] = {"name": obj.display_name, "class": obj}
load_strategies()


# --- Instrument Caching and Search (In-Memory) ---
instrument_cache = None

def update_instrument_cache():
    """Fetches and caches the instrument list in a global variable."""
    global instrument_cache
    try:
        kite.set_access_token(session["access_token"])
        instruments = kite.instruments()
        instrument_cache = pd.DataFrame(instruments)
    except Exception as e:
        print(f"Error caching instruments: {e}")
        instrument_cache = None

# --- Routes ---

@app.route("/")
def index():
    if "access_token" in session:
        return redirect("/home")
    return render_template("index.html")

@app.route("/login")
def login():
    return redirect(kite.login_url())

@app.route("/callback")
def callback():
    request_token = request.args.get("request_token")
    if not request_token:
        return "Error: request_token not found."
    try:
        data = kite.generate_session(request_token, api_secret=api_secret)
        session["access_token"] = data["access_token"]
        update_instrument_cache()
        return redirect("/home")
    except Exception as e:
        return f"Error: {e}"

@app.route("/home")
def home():
    if "access_token" not in session:
        return redirect("/")
    try:
        kite.set_access_token(session["access_token"])
        profile = kite.profile()
        return render_template("home.html", user=profile)
    except Exception as e:
        return f"Error: {e}"

@app.route("/logout")
def logout():
    session.pop("access_token", None)
    return redirect("/")

@app.route("/backtest", methods=["GET", "POST"])
def backtest():
    if "access_token" not in session:
        return redirect("/")
    if request.method == "POST":
        try:
            strategy_name = request.form.get("strategy")
            parameters = request.form.to_dict()
            results = run_backtest(strategy_name, parameters)
            return render_template("backtest.html", results=results, strategies=STRATEGIES, selected_strategy=strategy_name)
        except Exception as e:
            return render_template("backtest.html", error=str(e), strategies=STRATEGIES)
    return render_template("backtest.html", results=None, strategies=STRATEGIES)


@app.route("/scanner", methods=["GET", "POST"])
def scanner():
    if "access_token" not in session:
        return redirect("/")

    if request.method == "POST":
        try:
            proximity_percent = float(request.form.get("proximity_percent", 1.0))
            results = run_scanner(proximity_percent)
            return render_template("scanner.html", results=results)
        except Exception as e:
            return render_template("scanner.html", error=str(e))

    return render_template("scanner.html", results=None)


@app.route("/api/search-instruments")
def search_instruments():
    global instrument_cache
    query = request.args.get("q", "").upper()
    if instrument_cache is None:
        return jsonify({"error": "Instrument list not cached. Please log in again."}), 503
    if not query:
        return jsonify([])
    try:
        mask = (instrument_cache['tradingsymbol'].str.contains(query)) & (instrument_cache['exchange'] == 'NFO')
        results = instrument_cache[mask].head(10)
        return jsonify(results.to_dict(orient="records"))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- Scanner Logic ---
def run_scanner(proximity_percent=1.0):
    """
    FINAL DEBUG VERSION: Scans F&O stocks with extensive logging.
    """
    print("\n--- NEW SCANNER RUN ---")
    print(f"Proximity: {proximity_percent}%")

    global instrument_cache
    if instrument_cache is None:
        raise Exception("Instrument cache is not available. Please log in again.")

    kite.set_access_token(session["access_token"])

    nfo_options = instrument_cache[instrument_cache['segment'] == 'NFO-OPT'].copy()
    excluded_symbols = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY']
    nfo_options = nfo_options[~nfo_options['name'].isin(excluded_symbols)]

    nfo_options['expiry'] = pd.to_datetime(nfo_options['expiry'])
    future_expiries = nfo_options[nfo_options['expiry'] > datetime.now()].sort_values('expiry')
    if future_expiries.empty:
        return []
    nearest_expiry = future_expiries['expiry'].min()

    target_options = nfo_options[nfo_options['expiry'] == nearest_expiry]

    underlying_symbols = target_options['name'].unique()
    equity_instruments = instrument_cache[
        (instrument_cache['name'].isin(underlying_symbols)) &
        (instrument_cache['exchange'] == 'NSE') &
        (instrument_cache['instrument_type'] == 'EQ')
    ]
    equity_tokens = {inst['name']: f"{inst['exchange']}:{inst['tradingsymbol']}" for _, inst in equity_instruments.iterrows()}

    if not equity_tokens:
        return []

    ltp_data = {}
    token_list = list(equity_tokens.values())
    batch_size = 200
    for i in range(0, len(token_list), batch_size):
        batch = token_list[i:i + batch_size]
        ltp_data.update(kite.ltp(batch))
        print(f"Fetched LTP for batch {i//batch_size + 1}...")

    found_stocks = []
    proximity_decimal = proximity_percent / 100.0

    print("\n--- Processing Stocks ---")
    for symbol, group in target_options.groupby('name'):
        equity_token_str = equity_tokens.get(symbol)
        if not equity_token_str: continue

        ltp_info = ltp_data.get(equity_token_str)
        if not ltp_info or 'last_price' not in ltp_info: continue
        ltp = ltp_info['last_price']

        calls = group[group['instrument_type'] == 'CE']
        puts = group[group['instrument_type'] == 'PE']

        if calls.empty or puts.empty: continue

        high_oi_call = calls.loc[calls['open_interest'].idxmax()]
        high_oi_put = puts.loc[puts['open_interest'].idxmax()]

        call_strike = high_oi_call['strike']
        put_strike = high_oi_put['strike']

        # Final detailed check
        call_diff = abs(ltp - call_strike) / call_strike
        put_diff = abs(ltp - put_strike) / put_strike

        print(f" - {symbol}: LTP={ltp:.2f}, CallStrike={call_strike}, Diff={call_diff:.4f} | PutStrike={put_strike}, Diff={put_diff:.4f}")

        reason = ""
        if call_diff <= proximity_decimal:
            reason = f"LTP is within {proximity_percent}% of the highest OI Call strike ({call_strike})"
        elif put_diff <= proximity_decimal:
            reason = f"LTP is within {proximity_percent}% of the highest OI Put strike ({put_strike})"

        if reason:
            print(f"   *** FOUND MATCH: {symbol} ***")
            found_stocks.append({
                "symbol": symbol,
                "ltp": ltp,
                "high_oi_call_strike": call_strike,
                "high_oi_put_strike": put_strike,
                "reason": reason
            })
    print("--- SCANNER RUN COMPLETE ---")
    return found_stocks


# --- Backtesting Logic ---
def run_backtest(strategy_name: str, parameters: dict):
    """
    Runs a backtest for a given strategy.
    """
    if strategy_name not in STRATEGIES:
        raise ValueError(f"Strategy '{strategy_name}' not found.")

    strategy_class = STRATEGIES[strategy_name]["class"]
    strategy_instance = strategy_class()

    instrument_token = parameters.get("instrument_token")
    from_date_str = parameters.get("from_date")
    to_date_str = parameters.get("to_date")
    timeframe = parameters.get("timeframe", "5minute")

    from_date = datetime.strptime(from_date_str, "%Y-%m-%d")
    to_date = datetime.strptime(to_date_str, "%Y-%m-%d")

    kite.set_access_token(session["access_token"])
    historical_data = kite.historical_data(instrument_token, from_date, to_date + timedelta(days=1), timeframe)

    if not historical_data:
        raise Exception("Could not fetch historical data. Please check token/dates.")

    df = pd.DataFrame(historical_data)

    results = strategy_instance.run(df, parameters)
    return results


if __name__ == "__main__":
    app.run(debug=True)
