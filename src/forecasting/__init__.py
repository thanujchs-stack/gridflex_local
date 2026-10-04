"""GridFlex Local - Phase 3 Forecasting Package.

Provides monitoring, time-series forecasting, and flexibility projection
for neighbourhood load, solar PV generation, and net load.
"""

from src.forecasting.features import generate_forecasting_features
from src.forecasting.split import chronological_train_val_test_split, verify_no_leakage
from src.forecasting.baselines import PersistenceForecaster, MovingAverageForecaster
from src.forecasting.models import MultiStepHistGradientBoostingForecaster
from src.forecasting.metrics import calculate_forecast_metrics
from src.forecasting.flexibility_forecaster import forecast_available_flexibility

__all__ = [
    "generate_forecasting_features",
    "chronological_train_val_test_split",
    "verify_no_leakage",
    "PersistenceForecaster",
    "MovingAverageForecaster",
    "MultiStepHistGradientBoostingForecaster",
    "calculate_forecast_metrics",
    "forecast_available_flexibility",
]
