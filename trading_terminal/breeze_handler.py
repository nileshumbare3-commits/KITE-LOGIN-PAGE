from breeze_connect import BreezeConnect
import logging
from datetime import datetime
import base64
import json

logger = logging.getLogger(__name__)

class BreezeHandler:
    def __init__(self, api_key, api_secret, session_token, breeze_instance=None):
        self.breeze = breeze_instance if breeze_instance else BreezeConnect(api_key=api_key)
        self.api_key = api_key
        self.api_secret = api_secret
        self.session_token = session_token
        self.on_tick_callback = None
        self.is_connected = False

    def connect(self):
        try:
            # Only generate session if not already done in the breeze_instance
            if not self.is_connected:
                try:
                    self.breeze.generate_session(api_secret=self.api_secret, session_token=self.session_token)
                    logger.info("Breeze session generated successfully.")
                except Exception as e:
                    logger.warning(f"Session generation failed (might already be active): {e}")

                # Start WebSocket
                self.breeze.ws_connect()
                self.breeze.on_ticks = self._on_ticks
                self.is_connected = True

        except Exception as e:
            logger.error(f"Error connecting to Breeze: {e}")

    def _on_ticks(self, tick):
        if self.on_tick_callback:
            # Normalize Breeze tick to match the format used by the strategy
            # Use 'symbol' consistently for Breeze identification

            # Convert string timestamp to datetime object
            raw_ts = tick.get('datetime')
            ts = None
            if raw_ts:
                try:
                    # Breeze typically returns 'YYYY-MM-DD HH:MM:SS'
                    ts = datetime.strptime(raw_ts, '%Y-%m-%d %H:%M:%S')
                except:
                    ts = datetime.now() # Fallback

            normalized_tick = {
                'instrument_token': tick.get('stock_code'),
                'last_price': float(tick.get('last', 0)) if tick.get('last') else 0.0,
                'volume': int(tick.get('vtt', 1)) if tick.get('vtt') else 1, # 'vtt' is often total volume traded
                'high': float(tick.get('high', 0)) if tick.get('high') else 0.0,
                'low': float(tick.get('low', 0)) if tick.get('low') else 0.0,
                'timestamp': ts
            }
            self.on_tick_callback([normalized_tick])

    def subscribe(self, symbols):
        """
        Subscribes to market data for the given symbols.
        Expected format: list of symbols (e.g., ["ICIBAN", "INFY"])
        Note: Simplified for demonstration; real Breeze API needs exchange_code too.
        """
        for symbol in symbols:
            try:
                self.breeze.subscribe_feeds(stock_code=symbol, exchange_code="NSE", product_type="cash")
                logger.info(f"Breeze subscribed to {symbol}")
            except Exception as e:
                logger.error(f"Breeze subscription error for {symbol}: {e}")

    def stop(self):
        # Breeze doesn't have a direct ws_close in some versions, but let's try
        try:
            self.breeze.ws_disconnect()
        except:
            pass
        logger.info("BreezeHandler stopped.")

    def place_order(self, stock_code, exchange_code, product, action, order_type, quantity, price, validity, stoploss=None):
        try:
            return self.breeze.place_order(
                stock_code=stock_code,
                exchange_code=exchange_code,
                product=product,
                action=action,
                order_type=order_type,
                quantity=quantity,
                price=price,
                validity=validity,
                stoploss=stoploss
            )
        except Exception as e:
            logger.error(f"Breeze place_order error: {e}")
            return None
