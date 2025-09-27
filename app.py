from flask import Flask, request, redirect, session, render_template, jsonify
from kiteconnect import KiteConnect
import os
import pandas as pd
from datetime import datetime, timedelta
import numpy as np

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Replace with your API key and secret
api_key = "YOUR_API_KEY"
api_secret = "YOUR_API_SECRET"

kite = KiteConnect(api_key=api_key)

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
            instrument_token = request.form.get("instrument_token")
            from_date_str = request.form.get("from_date")
            to_date_str = request.form.get("to_date")
            stop_loss = float(request.form.get("stop_loss", 1500))
            target = float(request.form.get("target", 4500))
            use_tsl = request.form.get("use_tsl") == "true"
            tsl_mode = request.form.get("tsl_mode")
            tsl_fixed_amount = float(request.form.get("tsl_fixed_amount", 0))
            tsl_ema_period = int(request.form.get("tsl_ema_period", 9))
            timeframe = request.form.get("timeframe", "5minute")
            allow_reentry = request.form.get("allow_reentry") == "true"

            results = run_backtest(
                instrument_token, from_date_str, to_date_str, stop_loss, target,
                use_tsl, tsl_mode, tsl_fixed_amount, tsl_ema_period, timeframe, allow_reentry
            )
            return render_template("backtest.html", results=results)
        except Exception as e:
            return render_template("backtest.html", error=str(e))
    return render_template("backtest.html", results=None)

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
def run_backtest(instrument_token, from_date_str, to_date_str, stop_loss, target,
                 use_tsl, tsl_mode, tsl_fixed_amount, tsl_ema_period, timeframe, allow_reentry):
    kite.set_access_token(session["access_token"])
    from_date = datetime.strptime(from_date_str, "%Y-%m-%d")
    to_date = datetime.strptime(to_date_str, "%Y-%m-%d")
    historical_data = kite.historical_data(instrument_token, from_date, to_date + timedelta(days=1), timeframe)
    if not historical_data:
        raise Exception("Could not fetch historical data. Please check token/dates.")
    df = pd.DataFrame(historical_data)
    df['date'] = pd.to_datetime(df['date'])
    all_trades = []

    for day in pd.date_range(start=from_date, end=to_date):
        day_df = df[df['date'].dt.date == day.date()]
        if day_df.empty: continue

        trade_day_df = day_df[day_df['date'].dt.time >= pd.to_datetime("09:30").time()].copy()
        if trade_day_df.empty: continue

        first_candle = trade_day_df.iloc[0]
        opening_range_high = first_candle['high']
        opening_range_low = first_candle['low']

        trade_day_df.loc[:, 'cum_volume'] = trade_day_df['volume'].cumsum()
        trade_day_df.loc[:, 'cum_volume_high'] = (trade_day_df['high'] * trade_day_df['volume']).cumsum()
        trade_day_df.loc[:, 'upper_band'] = trade_day_df['cum_volume_high'] / trade_day_df['cum_volume']
        trade_day_df.loc[:, 'cum_volume_low'] = (trade_day_df['low'] * trade_day_df['volume']).cumsum()
        trade_day_df.loc[:, 'lower_band'] = trade_day_df['cum_volume_low'] / trade_day_df['cum_volume']

        if use_tsl and tsl_mode == 'ema':
            trade_day_df.loc[:, 'tsl_ema'] = trade_day_df['close'].ewm(span=tsl_ema_period, adjust=False).mean()

        in_position = False
        current_trade = {}
        high_water_mark, low_water_mark = 0, 0

        for i, row in trade_day_df.iterrows():
            if in_position:
                lot_size = 50
                price_change = row['close'] - current_trade['entry_price']
                pnl = price_change * 0.3 * lot_size if current_trade['type'] == 'SELL_PUT_SPREAD' else -price_change * 0.3 * lot_size
                current_trade['max_profit'] = max(current_trade.get('max_profit', pnl), pnl)
                current_trade['max_loss'] = min(current_trade.get('max_loss', pnl), pnl)

                exit_condition_met = False
                if pnl >= target: exit_condition_met = True
                elif use_tsl:
                    if current_trade['type'] == 'SELL_PUT_SPREAD':
                        if tsl_mode == 'fixed':
                            high_water_mark = max(high_water_mark, row['close'])
                            tsl_price = high_water_mark - tsl_fixed_amount
                        elif tsl_mode == 'ema':
                            tsl_price = row['tsl_ema']
                        else: # Band mode
                            tsl_price = row['lower_band']
                        if row['close'] < tsl_price: exit_condition_met = True
                    else: # Bearish trade
                        if tsl_mode == 'fixed':
                            low_water_mark = min(low_water_mark, row['close'])
                            tsl_price = low_water_mark + tsl_fixed_amount
                        elif tsl_mode == 'ema':
                            tsl_price = row['tsl_ema']
                        else: # Band mode
                            tsl_price = row['upper_band']
                        if row['close'] > tsl_price: exit_condition_met = True
                elif pnl <= -stop_loss: exit_condition_met = True

                if exit_condition_met:
                    current_trade.update({'exit_price': row['close'], 'exit_time': row['date'], 'pnl': pnl})
                    all_trades.append(current_trade)
                    in_position = False
                    current_trade = {}
                    if not allow_reentry:
                        break

            if not in_position:
                def get_strike(price): return round(price / 50) * 50
                if row['close'] > row['upper_band'] and row['open'] < row['upper_band'] and row['close'] > opening_range_high:
                    in_position, strike = True, get_strike(row['close'])
                    current_trade = {"type": "SELL_PUT_SPREAD", "entry_price": row['close'], "entry_time": row['date'], "strike_traded": f"{strike} PE"}
                    high_water_mark = row['close']
                elif row['close'] < row['lower_band'] and row['open'] > row['lower_band'] and row['close'] < opening_range_low:
                    in_position, strike = True, get_strike(row['close'])
                    current_trade = {"type": "SELL_CALL_SPREAD", "entry_price": row['close'], "entry_time": row['date'], "strike_traded": f"{strike} CE"}
                    low_water_mark = row['close']

        if in_position:
            last_row = trade_day_df.iloc[-1]
            price_change = last_row['close'] - current_trade['entry_price']
            pnl = price_change * 0.3 * lot_size if current_trade['type'] == 'SELL_PUT_SPREAD' else -price_change * 0.3 * lot_size
            current_trade.update({'exit_price': last_row['close'], 'exit_time': last_row['date'], 'pnl': pnl, 'max_profit': max(current_trade.get('max_profit', pnl), pnl), 'max_loss': min(current_trade.get('max_loss', pnl), pnl)})
            all_trades.append(current_trade)

    total_pnl = sum(trade['pnl'] for trade in all_trades)
    winning_trades = [t for t in all_trades if t['pnl'] > 0]
    losing_trades = [t for t in all_trades if t['pnl'] <= 0]
    summary = {"win_percentage": (len(winning_trades) / len(all_trades) * 100) if all_trades else 0, "avg_profit_win": sum(t['pnl'] for t in winning_trades) / len(winning_trades) if winning_trades else 0, "avg_loss_lose": sum(t['pnl'] for t in losing_trades) / len(losing_trades) if losing_trades else 0}
    return {"trades": all_trades, "total_pnl": total_pnl, "summary": summary}

if __name__ == "__main__":
    app.run(debug=True)