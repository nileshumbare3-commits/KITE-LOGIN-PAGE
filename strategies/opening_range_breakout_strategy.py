import pandas as pd
from datetime import datetime, timedelta
from .base_strategy import BaseStrategy

class OpeningRangeBreakoutStrategy(BaseStrategy):
    """
    The original opening range breakout strategy.
    """
    display_name = "Opening Range Breakout"

    def run(self, data: pd.DataFrame, parameters: dict) -> dict:
        stop_loss = float(parameters.get("stop_loss", 1500))
        target = float(parameters.get("target", 4500))
        use_tsl = parameters.get("use_tsl") == "true"
        tsl_mode = parameters.get("tsl_mode")
        tsl_fixed_amount = float(parameters.get("tsl_fixed_amount", 0))
        tsl_ema_period = int(parameters.get("tsl_ema_period", 9))
        allow_reentry = parameters.get("allow_reentry") == "true"
        from_date_str = parameters.get("from_date")
        to_date_str = parameters.get("to_date")

        from_date = datetime.strptime(from_date_str, "%Y-%m-%d")
        to_date = datetime.strptime(to_date_str, "%Y-%m-%d")

        df = data
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
            lot_size = 50 # Default lot size

            for i, row in trade_day_df.iterrows():
                if in_position:
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

        if not all_trades:
            return {"trades": [], "total_pnl": 0, "summary": {}}

        total_pnl = sum(trade['pnl'] for trade in all_trades)
        winning_trades = [t for t in all_trades if t['pnl'] > 0]
        losing_trades = [t for t in all_trades if t['pnl'] <= 0]
        summary = {"win_percentage": (len(winning_trades) / len(all_trades) * 100) if all_trades else 0, "avg_profit_win": sum(t['pnl'] for t in winning_trades) / len(winning_trades) if winning_trades else 0, "avg_loss_lose": sum(t['pnl'] for t in losing_trades) / len(losing_trades) if losing_trades else 0}
        return {"trades": all_trades, "total_pnl": total_pnl, "summary": summary}
