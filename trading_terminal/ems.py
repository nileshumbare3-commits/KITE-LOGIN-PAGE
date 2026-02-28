import logging
from kiteconnect import KiteConnect

logger = logging.getLogger(__name__)

class EMS:
    def __init__(self, api_key, access_token):
        self.kite = KiteConnect(api_key=api_key)
        self.kite.set_access_token(access_token)

    def place_order(self, variety, exchange, tradingsymbol, transaction_type, quantity, product, order_type, price=None, trigger_price=None, stoploss=None, squareoff=None, trailing_stoploss=None, validity=None, tag=None):
        try:
            order_id = self.kite.place_order(
                variety=variety,
                exchange=exchange,
                tradingsymbol=tradingsymbol,
                transaction_type=transaction_type,
                quantity=quantity,
                product=product,
                order_type=order_type,
                price=price,
                trigger_price=trigger_price,
                stoploss=stoploss,
                squareoff=squareoff,
                trailing_stoploss=trailing_stoploss,
                validity=validity,
                tag=tag
            )
            logger.info(f"Order placed successfully: {order_id}")
            return order_id
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return None

    def get_order_history(self, order_id):
        try:
            return self.kite.order_history(order_id)
        except Exception as e:
            logger.error(f"Error fetching order history for {order_id}: {e}")
            return None

    def cancel_order(self, variety, order_id, parent_order_id=None):
        try:
            return self.kite.cancel_order(variety, order_id, parent_order_id)
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return None

    def modify_order(self, variety, order_id, parent_order_id=None, quantity=None, price=None, order_type=None, trigger_price=None, validity=None):
        try:
            return self.kite.modify_order(variety, order_id, parent_order_id, quantity, price, order_type, trigger_price, validity)
        except Exception as e:
            logger.error(f"Error modifying order {order_id}: {e}")
            return None
