import unittest
from unittest.mock import MagicMock, patch
from trading_terminal.strategy import MeanReversionStrategy, VWAPBandStrategy
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

    def test_vwap_band_strategy(self):
        from datetime import datetime, timedelta
        strategy = VWAPBandStrategy(instrument_token=456)
        now = datetime.now()

        # Simulate data to build VWAP and aggregate candles
        # Candle 1: 0-5 min (e.g., 10:00 to 10:04)
        base_time = now.replace(minute=(now.minute // 5) * 5, second=0, microsecond=0)
        for i in range(5):
            strategy.update_data({
                'instrument_token': 456, 'last_price': 100, 'volume': 10, 'high': 105, 'low': 95,
                'timestamp': base_time + timedelta(minutes=i)
            })

        # High VWAP = 105, Low VWAP = 95
        self.assertEqual(strategy.high_vwap, 105)
        self.assertEqual(strategy.low_vwap, 95)

        # At this point, 1 candle is in progress but not completed (unless we move to next interval)
        self.assertEqual(len(strategy.candles), 0)

        # Start Candle 2 (5-10 min) to complete Candle 1
        strategy.update_data({
            'instrument_token': 456, 'last_price': 110, 'volume': 10, 'high': 110, 'low': 110,
            'timestamp': base_time + timedelta(minutes=5)
        })
        self.assertEqual(len(strategy.candles), 1)
        self.assertEqual(strategy.candles[0]['close'], 100) # Close of first 5 min

        # Signal check: previous_close (100) is NOT above high_vwap (approx 105.8)
        self.assertNotEqual(strategy.generate_signal(), "BUY")

        # Now make previous close > high vwap
        # Update Candle 2 with high price
        strategy.update_data({
            'instrument_token': 456, 'last_price': 120, 'volume': 1, 'high': 120, 'low': 120,
            'timestamp': base_time + timedelta(minutes=6)
        })
        # Complete candle 2 by moving to 10 min mark
        strategy.update_data({
            'instrument_token': 456, 'last_price': 121, 'volume': 1, 'high': 121, 'low': 121,
            'timestamp': base_time + timedelta(minutes=10)
        })
        # Now candles has 2 entries. previous_close = candles[-1]['close'] = 120
        self.assertEqual(strategy.candles[-1]['close'], 120)
        self.assertEqual(strategy.generate_signal(), "BUY")
        self.assertEqual(strategy.get_tsl("BUY"), strategy.low_vwap)

        # Test SELL signal
        strategy = VWAPBandStrategy(instrument_token=456)
        # Complete candle 1 (10:00-10:05)
        strategy.update_data({'instrument_token': 456, 'last_price': 100, 'volume': 10, 'high': 105, 'low': 95, 'timestamp': base_time})
        strategy.update_data({'instrument_token': 456, 'last_price': 100, 'volume': 10, 'high': 105, 'low': 95, 'timestamp': base_time + timedelta(minutes=5)})
        # Now current_price < low_vwap (approx 95)
        strategy.update_data({'instrument_token': 456, 'last_price': 80, 'volume': 1, 'high': 80, 'low': 80, 'timestamp': base_time + timedelta(minutes=6)})
        self.assertEqual(strategy.generate_signal(), "SELL")

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
