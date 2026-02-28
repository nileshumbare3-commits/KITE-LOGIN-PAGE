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
