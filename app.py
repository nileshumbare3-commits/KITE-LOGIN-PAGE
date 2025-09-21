from flask import Flask, request, redirect, session, render_template, jsonify
from kiteconnect import KiteConnect
import os
import pandas as pd
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Replace with your API key and secret
api_key = "YOUR_API_KEY"
api_secret = "YOUR_API_SECRET"

kite = KiteConnect(api_key=api_key)

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
        instrument_token = request.form.get("instrument_token")
        from_date_str = request.form.get("from_date")
        to_date_str = request.form.get("to_date")
        stop_loss = float(request.form.get("stop_loss", 1500))
        target = float(request.form.get("target", 4500))

        try:
            results = run_backtest(instrument_token, from_date_str, to_date_str, stop_loss, target)
            return render_template("backtest.html", results=results)
        except Exception as e:
            return render_template("backtest.html", error=str(e))

    return render_template("backtest.html", results=None)

# --- Instrument Caching and Search ---

@app.route("/api/update-instruments")
def update_instruments():
    if "access_token" not in session:
        return "Error: You must be logged in to update the instrument list.", 401

    try:
        kite.set_access_token(session["access_token"])
        instruments = kite.instruments()
        df = pd.DataFrame(instruments)
        df.to_csv("instance/instruments.csv", index=False)
        return f"Successfully updated and cached {len(df)} instruments."
    except Exception as e:
        return f"Error updating instruments: {e}", 500

@app.route("/api/search-instruments")
def search_instruments():
    query = request.args.get("q", "").upper()
    if not query:
        return jsonify([])

    try:
        df = pd.read_csv("instance/instruments.csv")
        # Search for NFO instruments containing the query
        mask = (df['tradingsymbol'].str.contains(query)) & (df['exchange'] == 'NFO')
        results = df[mask].head(10) # Limit results to 10
        return jsonify(results.to_dict(orient="records"))
    except FileNotFoundError:
        return jsonify({"error": "Instrument cache not found. Please log in and visit /api/update-instruments first."}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def run_backtest(instrument_token, from_date_str, to_date_str, stop_loss, target):
    """
    Runs the AVWAP breakout backtest strategy.
    NOTE: This is a simplified simulation. It does not use historical options data for P&L calculation
    due to the limitations of fetching historical instrument tokens. P&L is approximated.
    """
    kite.set_access_token(session["access_token"])

    from_date = datetime.strptime(from_date_str, "%Y-%m-%d")
    to_date = datetime.strptime(to_date_str, "%Y-%m-%d")

    historical_data = kite.historical_data(instrument_token, from_date, to_date + timedelta(days=1), "minute")

    if not historical_data:
        raise Exception("Could not fetch historical data. Please check the instrument token and date range.")

    df = pd.DataFrame(historical_data)
    df['date'] = pd.to_datetime(df['date'])

    all_trades = []

    for day in pd.date_range(start=from_date, end=to_date):
        day_df = df[df['date'].dt.date == day.date()]

        if day_df.empty:
            continue

        trade_day_df = day_df[day_df['date'].dt.time >= pd.to_datetime("09:30").time()].copy()

        if trade_day_df.empty:
            continue

        trade_day_df['cum_volume'] = trade_day_df['volume'].cumsum()
        trade_day_df['cum_volume_price'] = (trade_day_df['close'] * trade_day_df['volume']).cumsum()
        trade_day_df['avwap'] = trade_day_df['cum_volume_price'] / trade_day_df['cum_volume']

        trade_day_df['price_change'] = trade_day_df['close'].diff().fillna(0)
        trade_day_df['std_dev'] = trade_day_df['price_change'].expanding().std()

        trade_day_df['upper_band'] = trade_day_df['avwap'] + trade_day_df['std_dev']
        trade_day_df['lower_band'] = trade_day_df['avwap'] - trade_day_df['std_dev']

        entry_trade = None
        for i, row in trade_day_df.iterrows():
            if entry_trade is None:
                if row['close'] > row['upper_band']:
                    entry_trade = {"type": "SELL_PUT_SPREAD", "entry_price": row['close'], "entry_time": row['date']}
                    break
                elif row['close'] < row['lower_band']:
                    entry_trade = {"type": "SELL_CALL_SPREAD", "entry_price": row['close'], "entry_time": row['date']}
                    break

        if entry_trade:
            position_active = True
            for i, row in trade_day_df[trade_day_df['date'] > entry_trade['entry_time']].iterrows():
                if not position_active:
                    break

                lot_size = 50
                price_change = row['close'] - entry_trade['entry_price']

                if entry_trade['type'] == 'SELL_PUT_SPREAD':
                    pnl = price_change * 0.3 * lot_size
                else:
                    pnl = -price_change * 0.3 * lot_size

                if pnl <= -stop_loss or pnl >= target:
                    entry_trade['exit_price'] = row['close']
                    entry_trade['exit_time'] = row['date']
                    entry_trade['pnl'] = pnl
                    all_trades.append(entry_trade)
                    position_active = False

            if position_active:
                last_row = trade_day_df.iloc[-1]
                price_change = last_row['close'] - entry_trade['entry_price']
                if entry_trade['type'] == 'SELL_PUT_SPREAD':
                    pnl = price_change * 0.3 * lot_size
                else:
                    pnl = -price_change * 0.3 * lot_size

                entry_trade['exit_price'] = last_row['close']
                entry_trade['exit_time'] = last_row['date']
                entry_trade['pnl'] = pnl
                all_trades.append(entry_trade)

    total_pnl = sum(trade['pnl'] for trade in all_trades)

    return {"trades": all_trades, "total_pnl": total_pnl}

if __name__ == "__main__":
    app.run(debug=True)
