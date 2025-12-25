from flask import Flask, render_template, request, redirect, url_for, session
import os
from kiteconnect import KiteConnect
import json
import pandas as pd
from datetime import datetime
from backtesting_engine import BacktestingEngine
import traceback

app = Flask(__name__)
app.secret_key = os.urandom(24)

# In-memory store for strategies for simplicity
strategies = {}
strategy_id_counter = 1

# Replace with your API key and secret - In a real app, use environment variables
api_key = os.environ.get("KITE_API_KEY", "jaibrxwjfdmr86ao")
api_secret = os.environ.get("KITE_API_SECRET", "se1mzachqkdv963oqgbu7ij0y6002di1")

kite = KiteConnect(api_key=api_key)

instrument_df = None

def get_instrument_token(instrument_name):
    """Looks up the instrument token for a given instrument name."""
    global instrument_df
    if instrument_df is None:
        instrument_df = pd.DataFrame(kite.instruments())

    instrument = instrument_df[instrument_df.tradingsymbol == instrument_name]
    if not instrument.empty:
        return instrument.instrument_token.iloc[0]
    return None

@app.route('/')
def index():
    """Renders the landing page."""
    return render_template('index.html')

@app.route('/login')
def login():
    """Redirects the user to the Kite login page."""
    return redirect(kite.login_url())

@app.route('/callback')
def callback():
    """Handles the callback from Kite after successful login."""
    request_token = request.args.get('request_token')
    if not request_token:
        return "Error: request_token not found.", 400
    try:
        data = kite.generate_session(request_token, api_secret=api_secret)
        session['access_token'] = data['access_token']
        # Fetch and cache instruments or user profile if needed
        return redirect(url_for('dashboard'))
    except Exception as e:
        return f"Authentication failed: {e}", 400

@app.route('/dashboard')
def dashboard():
    """Displays the main dashboard after login."""
    if 'access_token' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html', strategies=strategies)

@app.route('/strategy-builder')
def strategy_builder():
    """Displays the strategy builder page."""
    if 'access_token' not in session:
        return redirect(url_for('login'))
    return render_template('strategy-builder.html')

@app.route('/backtest')
def backtest():
    """Displays the backtesting page."""
    if 'access_token' not in session:
        return redirect(url_for('login'))
    # This will be enhanced to show backtest results
    return render_template('backtest.html')

@app.route('/logout')
def logout():
    """Logs the user out."""
    session.pop('access_token', None)
    return redirect(url_for('index'))

@app.route('/save-strategy', methods=['POST'])
def save_strategy():
    """Saves the strategy configuration from the builder."""
    if 'access_token' not in session:
        return redirect(url_for('login'))

    global strategy_id_counter
    strategy_name = request.form.get('strategy_name')
    instrument = request.form.get('instrument')
    stop_loss = request.form.get('stop_loss')
    take_profit = request.form.get('take_profit')

    entry_conditions = []
    exit_conditions = []

    # This parsing logic is a bit complex due to the dynamic form
    # In a real app, you might use a library or a more robust naming convention
    for key, value in request.form.items():
        if key.startswith('entry_indicator_'):
            index = key.split('_')[-1]
            condition = {
                'indicator': value,
                'param1': request.form.get(f'entry_indicator_param1_{index}'),
                'operator': request.form.get(f'entry_operator_{index}'),
                'value': request.form.get(f'entry_value_{index}')
            }
            entry_conditions.append(condition)
        elif key.startswith('exit_indicator_'):
            index = key.split('_')[-1]
            condition = {
                'indicator': value,
                'param1': request.form.get(f'exit_indicator_param1_{index}'),
                'operator': request.form.get(f'exit_operator_{index}'),
                'value': request.form.get(f'exit_value_{index}')
            }
            exit_conditions.append(condition)

    strategy = {
        'id': strategy_id_counter,
        'name': strategy_name,
        'instrument': instrument,
        'entry_conditions': entry_conditions,
        'exit_conditions': exit_conditions,
        'stop_loss': stop_loss,
        'take_profit': take_profit
    }

    strategies[strategy_id_counter] = strategy
    strategy_id_counter += 1

    # For debugging: print the captured strategy
    print(json.dumps(strategy, indent=4))

    return redirect(url_for('dashboard'))

@app.route('/edit-strategy/<int:strategy_id>', methods=['GET', 'POST'])
def edit_strategy(strategy_id):
    """Handles editing a strategy."""
    if 'access_token' not in session:
        return redirect(url_for('login'))

    strategy = strategies.get(strategy_id)
    if not strategy:
        return "Strategy not found", 404

    if request.method == 'POST':
        # Update logic
        strategy['name'] = request.form.get('strategy_name')
        strategy['instrument'] = request.form.get('instrument')
        strategy['stop_loss'] = request.form.get('stop_loss')
        strategy['take_profit'] = request.form.get('take_profit')

        entry_conditions = []
        exit_conditions = []

        for key, value in request.form.items():
            if key.startswith('entry_indicator_'):
                index = key.split('_')[-1]
                condition = {
                    'indicator': value,
                    'param1': request.form.get(f'entry_indicator_param1_{index}'),
                    'operator': request.form.get(f'entry_operator_{index}'),
                    'value': request.form.get(f'entry_value_{index}')
                }
                entry_conditions.append(condition)
            elif key.startswith('exit_indicator_'):
                index = key.split('_')[-1]
                condition = {
                    'indicator': value,
                    'param1': request.form.get(f'exit_indicator_param1_{index}'),
                    'operator': request.form.get(f'exit_operator_{index}'),
                    'value': request.form.get(f'exit_value_{index}')
                }
                exit_conditions.append(condition)

        strategy['entry_conditions'] = entry_conditions
        strategy['exit_conditions'] = exit_conditions

        return redirect(url_for('dashboard'))

    return render_template('strategy-builder.html', strategy=strategy)

@app.route('/run-backtest/<int:strategy_id>')
def run_backtest(strategy_id):
    """Displays the page to set backtest parameters."""
    if 'access_token' not in session:
        return redirect(url_for('login'))

    strategy = strategies.get(strategy_id)
    if not strategy:
        return "Strategy not found", 404

    return render_template('run-backtest.html', strategy=strategy)

@app.route('/execute-backtest/<int:strategy_id>', methods=['POST'])
def execute_backtest(strategy_id):
    """Executes the backtest with the given parameters."""
    if 'access_token' not in session:
        return redirect(url_for('login'))

    strategy = strategies.get(strategy_id)
    if not strategy:
        return "Strategy not found", 404

    try:
        from_date_str = request.form.get('from_date')
        to_date_str = request.form.get('to_date')
        from_date = datetime.strptime(from_date_str, '%Y-%m-%d')
        to_date = datetime.strptime(to_date_str, '%Y-%m-%d')

        kite.set_access_token(session['access_token'])

        instrument_token = get_instrument_token(strategy['instrument'])
        if not instrument_token:
            return "Instrument not found", 404

        historical_data = kite.historical_data(instrument_token, from_date, to_date, "5minute")

        engine = BacktestingEngine(strategy, historical_data)
        results = engine.run()

        return render_template('backtest.html', results=results, strategy=strategy)
    except Exception as e:
        return f"<pre>{traceback.format_exc()}</pre>", 500

@app.route('/delete-strategy/<int:strategy_id>')
def delete_strategy(strategy_id):
    """Deletes a strategy."""
    if 'access_token' not in session:
        return redirect(url_for('login'))

    if strategy_id in strategies:
        del strategies[strategy_id]

    return redirect(url_for('dashboard'))


if __name__ == '__main__':
    app.run(debug=True, port=5000)
