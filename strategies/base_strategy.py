from abc import ABC, abstractmethod
import pandas as pd

class BaseStrategy(ABC):
    """
    Abstract base class for all backtesting strategies.
    """
    display_name = "Base Strategy"

    @abstractmethod
    def run(self, data: pd.DataFrame, parameters: dict) -> dict:
        """
        Run the backtest for the strategy.

        :param data: A pandas DataFrame containing the historical data.
        :param parameters: A dictionary of parameters for the strategy.
        :return: A dictionary containing the backtest results.
        """
        pass
