from flask import Flask, request, redirect, session, render_template, jsonify
from kiteconnect import KiteConnect
from breeze_connect import BreezeConnect
import os
import pandas as pd
from datetime import datetime, timedelta
import numpy as np
from trading_terminal.market_data import MarketDataHandler
from trading_terminal.breeze_handler import BreezeHandler
from trading_terminal.strategy import MeanReversionStrategy
from trading_terminal.ems import EMS
from trading_terminal.risk_manager import RiskManager
from trading_terminal.logger import Heartbeat

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Use environment variables for API keys and secrets for security
api_key = os.getenv("KITE_API_KEY", "YOUR_API_KEY")
api_secret = os.getenv("KITE_API_SECRET", "YOUR_API_SECRET")

# Breeze Credentials
breeze_api_key = os.getenv("BREEZE_API_KEY", "YOUR_BREEZE_API_KEY")
breeze_api_secret = os.getenv("BREEZE_API_SECRET", "YOUR_BREEZE_API_SECRET")

kite = KiteConnect(api_key=api_key)
breeze = BreezeConnect(api_key=breeze_api_key)

# --- Instrument Caching and Search (In-Memory) ---
instrument_cache = None
terminal_instance = None
terminal_logs = []

def add_terminal_log(message):
    global terminal_logs
    timestamp = datetime.now().strftime("%H:%M:%S")
    terminal_logs.append(f"[{timestamp}] {message}")
    if len(terminal_logs) > 100:
        terminal_logs.pop(0)

class TerminalManager:
    def __init__(self, broker, api_key, access_token, instrument_token, trading_symbol, exchange, api_secret=None, breeze_instance=None):
        self.broker = broker
        self.trading_symbol = trading_symbol
        self.exchange = exchange
        # Kite uses numeric instrument_token, Breeze uses stock_code (string symbol)
        self.instrument_token = int(instrument_token) if broker == "kite" else trading_symbol

        if broker == "kite":
            self.market_data = MarketDataHandler(api_key, access_token)
            self.ems = EMS(api_key, access_token)
        else:
            self.market_data = BreezeHandler(api_key, api_secret, access_token, breeze_instance=breeze_instance)
            self.ems = self.market_data # For simplicity, BreezeHandler handles orders too

        self.strategy = MeanReversionStrategy(self.instrument_token)
        self.risk_manager = RiskManager()
        self.heartbeat = Heartbeat(interval=60)
        self.running = False

    def start(self):
        self.market_data.set_on_tick_callback(self.handle_ticks)
        self.market_data.connect()

        # For Breeze, we subscribe using the symbol
        subscription_token = self.trading_symbol if self.broker == "breeze" else self.instrument_token
        self.market_data.subscribe([subscription_token])
        self.heartbeat.start()
        self.running = True
        add_terminal_log(f"Terminal started for {self.trading_symbol}")

    def handle_ticks(self, ticks):
        if not self.running:
            return
        for tick in ticks:
            self.strategy.update_data(tick)
            signal = self.strategy.generate_signal()
            if signal:
                add_terminal_log(f"Signal generated: {signal}")
                if self.broker == "kite":
                    order_params = {
                        "variety": "regular",
                        "exchange": self.exchange,
                        "tradingsymbol": self.trading_symbol,
                        "transaction_type": "BUY" if signal == "BUY" else "SELL",
                        "quantity": 1,
                        "product": "CNC",
                        "order_type": "MARKET"
                    }
                else:
                    # Breeze order format
                    order_params = {
                        "stock_code": self.trading_symbol,
                        "exchange_code": self.exchange,
                        "product": "cash",
                        "action": "buy" if signal == "BUY" else "sell",
                        "order_type": "market",
                        "quantity": 1,
                        "price": 0,
                        "validity": "day"
                    }

                if self.risk_manager.check_risk(order_params):
                    order_id = self.ems.place_order(**order_params)
                    if order_id:
                        add_terminal_log(f"Order placed: {order_id}")
                        self.risk_manager.increment_trade_count()
                else:
                    add_terminal_log("Risk check failed!")

    def stop(self):
        self.running = False
        self.market_data.stop()
        self.heartbeat.stop()
        add_terminal_log("Terminal stopped.")

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

@app.route("/login-breeze")
def login_breeze():
    # ICICI Direct Breeze login URL
    login_url = f"https://api.icicidirect.com/apiuser/login?api_key={breeze_api_key}"
    return redirect(login_url)

@app.route("/callback")
def callback():
    request_token = request.args.get("request_token")
    if not request_token:
        return "Error: request_token not found."
    try:
        data = kite.generate_session(request_token, api_secret=api_secret)
        session["access_token"] = data["access_token"]
        session["broker"] = "kite"
        update_instrument_cache()
        return redirect("/home")
    except Exception as e:
        return f"Error: {e}"

@app.route("/callback-breeze")
def callback_breeze():
    apisession = request.args.get("apisession")
    if not apisession:
        return "Error: apisession not found."
    try:
        # For Breeze, the apisession is used to generate the full session
        breeze.generate_session(api_secret=breeze_api_secret, session_token=apisession)
        session["access_token"] = apisession # Store it as access_token for simplicity
        session["broker"] = "breeze"
        # Breeze doesn't have a direct instrument fetch like Kite in the same way,
        # but we can mock or handle it differently
        return redirect("/home")
    except Exception as e:
        return f"Error: {e}"

@app.route("/home")
def home():
    if "access_token" not in session:
        return redirect("/")

    broker = session.get("broker", "kite")
    try:
        if broker == "kite":
            kite.set_access_token(session["access_token"])
            profile = kite.profile()
            user_data = {"user_name": profile.get("user_name"), "email": profile.get("email"), "broker": "Kite"}
        else:
            # Breeze doesn't have a simple profile() call in the same way,
            # maybe get_customer_details()
            user_data = {"user_name": "ICICI User", "email": "N/A", "broker": "ICICI Direct (Breeze)"}

        return render_template("home.html", user=user_data)
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


@app.route("/terminal")
def terminal_ui():
    if "access_token" not in session:
        return redirect("/")
    return render_template("terminal.html")

@app.route("/api/terminal/start", methods=["POST"])
def start_terminal():
    global terminal_instance
    if "access_token" not in session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    data = request.json
    instrument_token = data.get("instrument_token")
    trading_symbol = data.get("trading_symbol")
    exchange = data.get("exchange")

    if not all([trading_symbol, exchange]):
        return jsonify({"status": "error", "message": "Missing parameters"}), 400

    if terminal_instance and terminal_instance.running:
        return jsonify({"status": "error", "message": "Terminal already running"}), 400

    try:
        broker = session.get("broker", "kite")
        if broker == "kite":
            if not instrument_token:
                 return jsonify({"status": "error", "message": "Instrument Token is required for Kite"}), 400
            terminal_instance = TerminalManager(broker, api_key, session["access_token"], instrument_token, trading_symbol, exchange)
        else:
            terminal_instance = TerminalManager(broker, breeze_api_key, session["access_token"], instrument_token, trading_symbol, exchange, api_secret=breeze_api_secret, breeze_instance=breeze)

        terminal_instance.start()
        return jsonify({"status": "success", "message": "Terminal started"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/terminal/stop", methods=["POST"])
def stop_terminal():
    global terminal_instance
    if terminal_instance:
        terminal_instance.stop()
        terminal_instance = None
        return jsonify({"status": "success", "message": "Terminal stopped"})
    return jsonify({"status": "error", "message": "Terminal not running"}), 400

@app.route("/api/terminal/logs")
def get_logs():
    return jsonify(terminal_logs)

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