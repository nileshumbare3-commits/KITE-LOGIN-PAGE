import logging
import time
import os
from trading_terminal.market_data import MarketDataHandler
from trading_terminal.strategy import MeanReversionStrategy
from trading_terminal.ems import EMS
from trading_terminal.risk_manager import RiskManager
from trading_terminal.logger import Heartbeat

# Configuration - Use environment variables for security
API_KEY = os.getenv("KITE_API_KEY", "YOUR_API_KEY")
ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN", "YOUR_ACCESS_TOKEN")
INSTRUMENT_TOKEN = int(os.getenv("KITE_INSTRUMENT_TOKEN", 12345))
TRADING_SYMBOL = "INFY"
EXCHANGE = "NSE"

# Setup Logging
logger = logging.getLogger("TradingTerminal")

class TradingTerminal:
    def __init__(self, api_key, access_token, instrument_token, trading_symbol, exchange):
        self.market_data = MarketDataHandler(api_key, access_token)
        self.strategy = MeanReversionStrategy(instrument_token)
        self.ems = EMS(api_key, access_token)
        self.risk_manager = RiskManager()
        self.heartbeat = Heartbeat(interval=60) # Set to 1 minute for demonstration

        self.trading_symbol = trading_symbol
        self.exchange = exchange
        self.instrument_token = instrument_token

    def start(self):
        logger.info("Starting Trading Terminal...")
        self.heartbeat.start()

        # Set callback for real-time ticks
        self.market_data.set_on_tick_callback(self.handle_ticks)

        # Connect to WebSocket
        self.market_data.connect()

        # Subscribe to instrument
        self.market_data.subscribe([self.instrument_token])

        logger.info(f"Subscribed to {self.trading_symbol} ({self.instrument_token})")

    def handle_ticks(self, ticks):
        for tick in ticks:
            # Update strategy data
            self.strategy.update_data(tick)

            # Generate signal
            signal = self.strategy.generate_signal()

            if signal:
                logger.info(f"Signal generated: {signal} for {self.trading_symbol}")

                # Check Risk
                order_params = {
                    "variety": "regular",
                    "exchange": self.exchange,
                    "tradingsymbol": self.trading_symbol,
                    "transaction_type": "BUY" if signal == "BUY" else "SELL",
                    "quantity": 1,
                    "product": "CNC",
                    "order_type": "MARKET"
                }

                if self.risk_manager.check_risk(order_params):
                    # Place Order
                    order_id = self.ems.place_order(**order_params)
                    if order_id:
                        logger.info(f"Order {order_id} placed successfully.")
                        self.risk_manager.increment_trade_count()
                else:
                    logger.warning("Order blocked by Risk Manager.")

    def stop(self):
        logger.info("Stopping Trading Terminal...")
        self.market_data.stop()
        self.heartbeat.stop()

if __name__ == "__main__":
    # In a real scenario, ACCESS_TOKEN would be retrieved from a session or database
    terminal = TradingTerminal(API_KEY, ACCESS_TOKEN, INSTRUMENT_TOKEN, TRADING_SYMBOL, EXCHANGE)
    terminal.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        terminal.stop()
