import unittest
from unittest.mock import MagicMock, patch
from trading_terminal.strategy import MeanReversionStrategy
from trading_terminal.risk_manager import RiskManager
from trading_terminal.market_data import MarketDataHandler
from trading_terminal.ems import EMS

class TestTradingTerminalLogic(unittest.TestCase):
    def test_mean_reversion_signal(self):
        strategy = MeanReversionStrategy(instrument_token=123)
        # Simulate some data points
        # If price is far above mean, it should signal SELL
        for i in range(20):
            strategy.update_data({'instrument_token': 123, 'last_price': 100})

        # Add a high price to trigger SELL
        strategy.update_data({'instrument_token': 123, 'last_price': 150})
        self.assertEqual(strategy.generate_signal(), "SELL")

        # Reset and test BUY
        strategy = MeanReversionStrategy(instrument_token=123)
        for i in range(20):
            strategy.update_data({'instrument_token': 123, 'last_price': 100})
        strategy.update_data({'instrument_token': 123, 'last_price': 50})
        self.assertEqual(strategy.generate_signal(), "BUY")

    def test_risk_manager(self):
        rm = RiskManager(max_trades_per_day=2, max_position_size=100)

        # Test valid order
        self.assertTrue(rm.check_risk({'quantity': 50}))

        # Test max position size
        self.assertFalse(rm.check_risk({'quantity': 150}))

        # Test max trades
        rm.increment_trade_count()
        rm.increment_trade_count()
        self.assertFalse(rm.check_risk({'quantity': 50}))

    @patch('trading_terminal.ems.KiteConnect')
    def test_ems_place_order(self, mock_kite):
        ems = EMS(api_key="key", access_token="token")
        ems.kite.place_order.return_value = "ORDER123"

        order_id = ems.place_order(
            variety="regular", exchange="NSE", tradingsymbol="INFY",
            transaction_type="BUY", quantity=1, product="CNC", order_type="MARKET"
        )
        self.assertEqual(order_id, "ORDER123")

if __name__ == "__main__":
    unittest.main()
