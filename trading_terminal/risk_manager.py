import logging

logger = logging.getLogger(__name__)

class RiskManager:
    def __init__(self, max_total_loss=10000, max_position_size=1000, max_trades_per_day=5):
        self.max_total_loss = max_total_loss
        self.max_position_size = max_position_size
        self.max_trades_per_day = max_trades_per_day
        self.current_total_loss = 0
        self.trades_today = 0

    def check_risk(self, order_params):
        """
        Checks if the proposed order exceeds any risk limits.
        """
        # Rule 1: Max Trades Per Day
        if self.trades_today >= self.max_trades_per_day:
            logger.warning(f"Risk Check Failed: Max trades ({self.max_trades_per_day}) reached.")
            return False

        # Rule 2: Max Position Size
        quantity = order_params.get('quantity', 0)
        if quantity > self.max_position_size:
            logger.warning(f"Risk Check Failed: Position size {quantity} exceeds max {self.max_position_size}.")
            return False

        # Rule 3: Max Total Loss (Circuit Breaker)
        if self.current_total_loss >= self.max_total_loss:
            logger.warning(f"Risk Check Failed: Total loss limit reached.")
            return False

        return True

    def update_pnl(self, pnl):
        self.current_total_loss += pnl

    def increment_trade_count(self):
        self.trades_today += 1
