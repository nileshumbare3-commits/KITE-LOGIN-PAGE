from kiteconnect import KiteTicker, KiteConnect
import logging

logger = logging.getLogger(__name__)

class MarketDataHandler:
    def __init__(self, api_key, access_token):
        self.api_key = api_key
        self.access_token = access_token
        self.kws = KiteTicker(api_key, access_token)
        self.kite = KiteConnect(api_key=api_key)
        self.kite.set_access_token(access_token)
        self.on_tick_callback = None

    def set_on_tick_callback(self, callback):
        self.on_tick_callback = callback

    def connect(self):
        self.kws.on_ticks = self._on_ticks
        self.kws.on_connect = self._on_connect
        self.kws.on_close = self._on_close
        self.kws.on_error = self._on_error
        self.kws.on_reconnect = self._on_reconnect
        self.kws.on_noreconnect = self._on_noreconnect
        self.kws.connect(threaded=True)

    def stop(self):
        if self.kws.is_connected():
            self.kws.close()
        logger.info("MarketDataHandler stopped.")

    def _on_ticks(self, ws, ticks):
        if self.on_tick_callback:
            self.on_tick_callback(ticks)

    def _on_connect(self, ws, response):
        logger.info("Successfully connected to WebSocket.")

    def _on_close(self, ws, code, reason):
        logger.warning(f"WebSocket closed: {code} - {reason}")

    def _on_error(self, ws, code, reason):
        logger.error(f"WebSocket error: {code} - {reason}")

    def _on_reconnect(self, ws, attempts_count):
        logger.info(f"Reconnecting... Attempt {attempts_count}")

    def _on_noreconnect(self, ws):
        logger.error("Failed to reconnect after multiple attempts.")

    def subscribe(self, instrument_tokens):
        self.kws.subscribe(instrument_tokens)
        self.kws.set_mode(self.kws.MODE_FULL, instrument_tokens)

    def get_historical_data(self, instrument_token, from_date, to_date, interval):
        try:
            return self.kite.historical_data(instrument_token, from_date, to_date, interval)
        except Exception as e:
            logger.error(f"Error fetching historical data: {e}")
            return None

    def get_ltp(self, instruments):
        try:
            return self.kite.ltp(instruments)
        except Exception as e:
            logger.error(f"Error fetching LTP: {e}")
            return None
