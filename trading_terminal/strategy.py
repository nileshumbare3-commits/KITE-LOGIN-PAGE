import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

class BaseStrategy:
    def __init__(self, instrument_token):
        self.instrument_token = instrument_token
        self.data = []

    def update_data(self, tick):
        if tick['instrument_token'] == self.instrument_token:
            self.data.append(tick)
            if len(self.data) > 100:
                self.data.pop(0)

    def generate_signal(self):
        raise NotImplementedError("Strategies must implement generate_signal()")

class MeanReversionStrategy(BaseStrategy):
    def __init__(self, instrument_token, window=20, std_dev=2):
        super().__init__(instrument_token)
        self.window = window
        self.std_dev = std_dev

    def generate_signal(self):
        if len(self.data) < self.window:
            return None

        prices = pd.Series([d['last_price'] for d in self.data])
        rolling_mean = prices.rolling(window=self.window).mean()
        rolling_std = prices.rolling(window=self.window).std()

        upper_band = rolling_mean + (self.std_dev * rolling_std)
        lower_band = rolling_mean - (self.std_dev * rolling_std)

        current_price = prices.iloc[-1]

        if current_price > upper_band.iloc[-1]:
            return "SELL"
        elif current_price < lower_band.iloc[-1]:
            return "BUY"
        else:
            return None

class MomentumStrategy(BaseStrategy):
    def __init__(self, instrument_token, short_window=5, long_window=20):
        super().__init__(instrument_token)
        self.short_window = short_window
        self.long_window = long_window

    def generate_signal(self):
        if len(self.data) < self.long_window:
            return None

        prices = pd.Series([d['last_price'] for d in self.data])
        short_sma = prices.rolling(window=self.short_window).mean()
        long_sma = prices.rolling(window=self.long_window).mean()

        if short_sma.iloc[-1] > long_sma.iloc[-1] and short_sma.iloc[-2] <= long_sma.iloc[-2]:
            return "BUY"
        elif short_sma.iloc[-1] < long_sma.iloc[-1] and short_sma.iloc[-2] >= long_sma.iloc[-2]:
            return "SELL"
        else:
            return None

class VWAPBandStrategy(BaseStrategy):
    def __init__(self, instrument_token):
        super().__init__(instrument_token)
        self.cum_volume = 0
        self.cum_high_vol = 0
        self.cum_low_vol = 0
        self.high_vwap = 0
        self.low_vwap = 0
        self.candles = [] # List of completed 5-min candles
        self.current_candle = None

    def update_data(self, tick):
        if tick['instrument_token'] == self.instrument_token:
            last_price = tick['last_price']
            # In Breeze 'vtt' is total volume traded today, in Kite 'volume' is often the same.
            # We need the volume of this tick.
            volume = tick.get('volume', 1)
            high = tick.get('high', last_price)
            low = tick.get('low', last_price)
            timestamp = tick.get('timestamp') # Expecting datetime object

            # Update Session VWAP (running total)
            self.cum_volume += volume
            self.cum_high_vol += (high * volume)
            self.cum_low_vol += (low * volume)

            if self.cum_volume > 0:
                self.high_vwap = self.cum_high_vol / self.cum_volume
                self.low_vwap = self.cum_low_vol / self.cum_volume

            # Candle Aggregation (5-min)
            if timestamp:
                # Round down to 5-min interval
                candle_time = timestamp.replace(minute=(timestamp.minute // 5) * 5, second=0, microsecond=0)

                if not self.current_candle or self.current_candle['time'] != candle_time:
                    if self.current_candle:
                        self.candles.append(self.current_candle)
                        if len(self.candles) > 100: self.candles.pop(0)

                    self.current_candle = {
                        'time': candle_time,
                        'open': last_price,
                        'high': high,
                        'low': low,
                        'close': last_price,
                        'volume': volume
                    }
                else:
                    # Update current candle
                    self.current_candle['high'] = max(self.current_candle['high'], high)
                    self.current_candle['low'] = min(self.current_candle['low'], low)
                    self.current_candle['close'] = last_price
                    self.current_candle['volume'] += volume

            # Maintain raw tick data for immediate response if needed
            self.data.append(tick)
            if len(self.data) > 100: self.data.pop(0)

    def generate_signal(self):
        if len(self.candles) < 1:
            return None

        # Request: "if PREVIOUS CLOSE PRICE IS ABOVE HIGH OF SESSION VWAP INITIATE BUY TRADE"
        # and "SELL INTIATED IF CLOSE IS BELOW LOW OF SESSION VWAP"
        # PREVIOUS CLOSE refers to the last completed candle's close.
        previous_close = self.candles[-1]['close']

        # 'CLOSE' in "SELL INTIATED IF CLOSE IS BELOW LOW" might mean current price
        current_price = self.data[-1]['last_price'] if self.data else previous_close

        if previous_close > self.high_vwap:
            return "BUY"
        elif current_price < self.low_vwap:
            return "SELL"
        else:
            return None

    def get_tsl(self, signal):
        if signal == "BUY":
            return self.low_vwap
        elif signal == "SELL":
            return self.high_vwap
        return None
