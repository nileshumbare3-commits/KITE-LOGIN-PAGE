from flask import session
from datetime import datetime
import pandas as pd

instrument_df = None

def get_instrument_token(kite, instrument_name):
    """Looks up the instrument token for a given instrument name."""
    global instrument_df
    if instrument_df is None:
        instrument_df = pd.DataFrame(kite.instruments())

    instrument = instrument_df[instrument_df.tradingsymbol == instrument_name]
    if not instrument.empty:
        return instrument.instrument_token.iloc[0]
    return None

def get_historical_data(kite, breeze, instrument_name, from_date, to_date, interval):
    """
    Fetches historical data from the active API.
    """
    if 'access_token' in session:
        # Use Kite Connect
        instrument_token = get_instrument_token(kite, instrument_name)
        if not instrument_token:
            raise Exception("Instrument not found")
        return kite.historical_data(instrument_token, from_date, to_date, interval)
    elif 'breeze_session' in session:
        # Use Breeze Connect
        # Note: The Breeze API has a different way of specifying instruments and date formats.
        # This is a simplified example and would need to be adapted to the specific requirements of the Breeze API.
        return breeze.get_historical_data(
            interval=interval,
            from_date=from_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            to_date=to_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            stock_code=instrument_name,
            exchange_code="NSE",
            product_type="cash"
        )
    else:
        raise Exception("User not logged in")
