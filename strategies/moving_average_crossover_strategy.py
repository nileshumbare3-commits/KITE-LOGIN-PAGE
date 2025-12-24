import pandas as pd
import numpy as np
from .base_strategy import BaseStrategy

class MovingAverageCrossoverStrategy(BaseStrategy):
    """
    A simple moving average crossover strategy.
    """
    display_name = "Moving Average Crossover"

    def run(self, data: pd.DataFrame, parameters: dict) -> dict:
        """
        Run the backtest for the moving average crossover strategy.

        :param data: A pandas DataFrame containing the historical data.
                     It must have 'date', 'open', 'high', 'low', 'close', 'volume' columns.
        :param parameters: A dictionary of parameters for the strategy.
                           - short_window (int): The period for the short moving average.
                           - long_window (int): The period for the long moving average.
                           - stop_loss (float): The stop loss in points.
                           - target (float): The target profit in points.
        :return: A dictionary containing the backtest results.
        """
        short_window = int(parameters.get('short_window', 50))
        long_window = int(parameters.get('long_window', 200))
        stop_loss = float(parameters.get('stop_loss', 100))
        target = float(parameters.get('target', 200))

        if 'close' not in data.columns:
            raise ValueError("Dataframe must contain 'close' column.")

        # Calculate moving averages
        data['short_mavg'] = data['close'].rolling(window=short_window, min_periods=1, center=False).mean()
        data['long_mavg'] = data['close'].rolling(window=long_window, min_periods=1, center=False).mean()

        # Generate signals
        data['signal'] = 0.0
        data['signal'][short_window:] = np.where(data['short_mavg'][short_window:] > data['long_mavg'][short_window:], 1.0, 0.0)
        data['position'] = data['signal'].diff()

        all_trades = []
        in_position = False
        current_trade = {}

        for i, row in data.iterrows():
            if not in_position and row['position'] == 1: # Buy signal
                in_position = True
                current_trade = {
                    "type": "BUY",
                    "entry_price": row['close'],
                    "entry_time": row['date'],
                }
                entry_price = row['close']

            elif in_position and (row['position'] == -1): # Sell signal
                current_trade.update({
                    'exit_price': row['close'],
                    'exit_time': row['date'],
                })
                pnl = (current_trade['exit_price'] - current_trade['entry_price'])
                current_trade['pnl'] = pnl
                current_trade['max_profit'] = max(0, pnl)
                current_trade['max_loss'] = min(0, pnl)
                all_trades.append(current_trade)
                in_position = False
                current_trade = {}

            # Handle stop-loss and target
            if in_position:
                price_change = row['close'] - entry_price
                exit_condition_met = False

                if price_change >= target:
                    exit_condition_met = True
                elif price_change <= -stop_loss:
                    exit_condition_met = True

                if exit_condition_met:
                    current_trade.update({
                        'exit_price': row['close'],
                        'exit_time': row['date'],
                    })
                    pnl = (current_trade['exit_price'] - current_trade['entry_price'])
                    current_trade['pnl'] = pnl
                    current_trade['max_profit'] = max(0, pnl)
                    current_trade['max_loss'] = min(0, pnl)
                    all_trades.append(current_trade)
                    in_position = False
                    current_trade = {}


        if in_position:
            last_row = data.iloc[-1]
            current_trade.update({
                'exit_price': last_row['close'],
                'exit_time': last_row['date'],
            })
            pnl = (current_trade['exit_price'] - current_trade['entry_price'])
            current_trade['pnl'] = pnl
            current_trade['max_profit'] = max(0, pnl)
            current_trade['max_loss'] = min(0, pnl)
            all_trades.append(current_trade)


        if not all_trades:
            return {"trades": [], "total_pnl": 0, "summary": {}}

        total_pnl = sum(trade['pnl'] for trade in all_trades)
        winning_trades = [t for t in all_trades if t['pnl'] > 0]
        losing_trades = [t for t in all_trades if t['pnl'] <= 0]

        summary = {
            "win_percentage": (len(winning_trades) / len(all_trades) * 100) if all_trades else 0,
            "avg_profit_win": sum(t['pnl'] for t in winning_trades) / len(winning_trades) if winning_trades else 0,
            "avg_loss_lose": sum(t['pnl'] for t in losing_trades) / len(losing_trades) if losing_trades else 0,
            "strike_traded": "N/A"
        }

        return {"trades": all_trades, "total_pnl": total_pnl, "summary": summary}
