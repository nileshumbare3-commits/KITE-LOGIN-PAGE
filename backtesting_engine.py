import pandas as pd
import numpy as np

class BacktestingEngine:
    def __init__(self, strategy, historical_data):
        self.strategy = strategy
        self.df = pd.DataFrame(historical_data)
        self.trades = []
        self.results = {}

    def _calculate_indicators(self):
        """Calculate all indicators required by the strategy."""
        for condition in self.strategy['entry_conditions'] + self.strategy['exit_conditions']:
            indicator = condition['indicator']
            if indicator == 'SMA':
                period = int(condition['param1'])
                self.df[f'SMA_{period}'] = self.df['close'].rolling(window=period).mean()
            elif indicator == 'EMA':
                period = int(condition['param1'])
                self.df[f'EMA_{period}'] = self.df['close'].ewm(span=period, adjust=False).mean()
            elif indicator == 'RSI':
                period = int(condition['param1'])
                delta = self.df['close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
                rs = gain / loss
                self.df[f'RSI_{period}'] = 100 - (100 / (1 + rs))
            elif indicator == 'MACD':
                # This is a simplified MACD, a proper implementation is more complex
                ema_fast = self.df['close'].ewm(span=12, adjust=False).mean()
                ema_slow = self.df['close'].ewm(span=26, adjust=False).mean()
                self.df['MACD_12_26'] = ema_fast - ema_slow
            elif indicator == 'BB':
                period = int(condition['param1'])
                self.df[f'BB_mid_{period}'] = self.df['close'].rolling(window=period).mean()
                self.df[f'BB_std_{period}'] = self.df['close'].rolling(window=period).std()
                self.df[f'BB_upper_{period}'] = self.df[f'BB_mid_{period}'] + (self.df[f'BB_std_{period}'] * 2)
                self.df[f'BB_lower_{period}'] = self.df[f'BB_mid_{period}'] - (self.df[f'BB_std_{period}'] * 2)


    def _check_condition(self, row, prev_row, val1_str, operator, val2_str):
        """Checks if a single condition is met."""
        val1 = row[val1_str]
        val2 = float(val2_str) # Assuming val2 is a static value for now

        if operator == 'crosses_above':
            prev_val1 = prev_row[val1_str]
            return prev_val1 < val2 and val1 > val2
        if operator == 'crosses_below':
            prev_val1 = prev_row[val1_str]
            return prev_val1 > val2 and val1 < val2
        if operator == 'greater_than':
            return val1 > val2
        if operator == 'less_than':
            return val1 < val2
        return False

    def run(self):
        """Runs the backtest simulation."""
        self._calculate_indicators()
        in_position = False
        entry_price = 0

        stop_loss_pct = float(self.strategy.get('stop_loss', 0)) / 100
        take_profit_pct = float(self.strategy.get('take_profit', 0)) / 100

        for i, row in self.df.iterrows():
            if i == 0:
                continue

            prev_row = self.df.iloc[i-1]

            if not in_position:
                # Check entry conditions
                entry_signal = all(self._check_condition(row, prev_row, f"{c['indicator']}_{int(c['param1'])}", c['operator'], c['value']) for c in self.strategy['entry_conditions'])
                if entry_signal:
                    in_position = True
                    entry_price = row['close']
                    self.trades.append({
                        'entry_time': row['date'],
                        'entry_price': entry_price,
                        'exit_time': None,
                        'exit_price': None,
                        'pnl': 0
                    })
            else:
                # Check exit conditions (SL, TP, or signal)
                exit_signal = any(self._check_condition(row, prev_row, f"{c['indicator']}_{int(c['param1'])}", c['operator'], c['value']) for c in self.strategy['exit_conditions'])

                stop_loss_price = entry_price * (1 - stop_loss_pct)
                take_profit_price = entry_price * (1 + take_profit_pct)

                if row['low'] <= stop_loss_price or row['high'] >= take_profit_price or exit_signal:
                    exit_price = stop_loss_price if row['low'] <= stop_loss_price else (take_profit_price if row['high'] >= take_profit_price else row['close'])
                    in_position = False
                    trade = self.trades[-1]
                    trade['exit_time'] = row['date']
                    trade['exit_price'] = exit_price
                    trade['pnl'] = exit_price - entry_price

        return self._summarize_results()

    def _summarize_results(self):
        """Calculates performance metrics."""
        total_pnl = sum(t['pnl'] for t in self.trades)
        winning_trades = [t for t in self.trades if t['pnl'] > 0]
        losing_trades = [t for t in self.trades if t['pnl'] <= 0]

        self.results = {
            'total_pnl': total_pnl,
            'total_trades': len(self.trades),
            'win_rate': len(winning_trades) / len(self.trades) * 100 if self.trades else 0,
            'average_profit': np.mean([t['pnl'] for t in winning_trades]) if winning_trades else 0,
            'average_loss': np.mean([t['pnl'] for t in losing_trades]) if losing_trades else 0,
            'trades': self.trades
        }
        return self.results
