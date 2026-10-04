"""Benchmark Forecasting Baselines for GridFlex Local.

Implements standard benchmark predictors required for determining ML value-add:
1. Persistence Forecaster: y_hat(t+k) = y(t)
2. Moving Average Forecaster: y_hat(t+k) = mean(y(t-W+1 ... t))
"""

from typing import List, Optional, Dict, Any
import numpy as np
import pandas as pd


def _is_nighttime(timestamp: pd.Timestamp) -> bool:
    """Check if given timestamp is during solar nighttime (before 06:00 or after 18:15)."""
    hour_float = timestamp.hour + timestamp.minute / 60.0
    return bool(hour_float < 6.0 or hour_float > 18.25)


class PersistenceForecaster:
    """Multi-step persistence forecaster (naive baseline).

    Assumes future value equals the last observed value at the forecast origin:
        y_hat(t+k) = y(t)
    For PV targets, nighttime intervals are physically clipped to 0.0.
    """

    def __init__(self, target_name: str = "load", is_solar: bool = False):
        self.target_name = target_name
        self.is_solar = is_solar
        self.residual_std_: float = 0.0

    def fit(self, train_series: pd.Series, horizon_steps: int = 16) -> "PersistenceForecaster":
        """Compute training residual standard deviation for simple empirical uncertainty intervals."""
        # Baseline 1-step residual proxy
        diffs = train_series.diff().dropna()
        self.residual_std_ = float(diffs.std()) if len(diffs) > 0 else 1.0
        return self

    def forecast(
        self,
        history_df: pd.DataFrame,
        origin_idx: int,
        target_col: str,
        horizon_steps: int = 16,
        step_minutes: int = 15,
        actual_series: Optional[pd.Series] = None,
    ) -> pd.DataFrame:
        """Generate multi-step forward forecast from a specific origin index.

        Returns DataFrame formatted with:
            timestamp, forecast_origin, horizon_minutes, actual, forecast, lower_bound, upper_bound, model, target
        """
        origin_row = history_df.iloc[origin_idx]
        t_origin = pd.to_datetime(origin_row["timestamp"])
        y_last = float(origin_row[target_col])

        rows = []
        for step in range(1, horizon_steps + 1):
            horizon_mins = step * step_minutes
            t_target = t_origin + pd.Timedelta(minutes=horizon_mins)

            y_pred = y_last
            if self.is_solar and _is_nighttime(t_target):
                y_pred = 0.0

            # Step-scaled uncertainty expansion: std * sqrt(step)
            margin = 1.645 * self.residual_std_ * np.sqrt(step / 4.0)
            lb = max(0.0, y_pred - margin)
            ub = max(0.0, y_pred + margin)

            if self.is_solar and _is_nighttime(t_target):
                lb = 0.0
                ub = 0.0

            y_act = np.nan
            if actual_series is not None and (origin_idx + step) < len(actual_series):
                y_act = float(actual_series.iloc[origin_idx + step])

            rows.append({
                "timestamp": t_target,
                "forecast_origin": t_origin,
                "horizon_minutes": horizon_mins,
                "actual": y_act,
                "forecast": y_pred,
                "lower_bound": lb,
                "upper_bound": ub,
                "model": "Persistence",
                "target": self.target_name,
            })

        return pd.DataFrame(rows)


class MovingAverageForecaster:
    """Historical moving average multi-step forecaster.

    Forecasts mean of the previous window W observations:
        y_hat(t+k) = mean(y(t-W+1 ... t))
    """

    def __init__(self, target_name: str = "load", window: int = 4, is_solar: bool = False):
        self.target_name = target_name
        self.window = window
        self.is_solar = is_solar
        self.residual_std_: float = 0.0

    def fit(self, train_series: pd.Series) -> "MovingAverageForecaster":
        """Compute training residual standard deviation for uncertainty intervals."""
        rolling_mean = train_series.rolling(self.window).mean()
        residuals = (train_series - rolling_mean).dropna()
        self.residual_std_ = float(residuals.std()) if len(residuals) > 0 else 1.0
        return self

    def forecast(
        self,
        history_df: pd.DataFrame,
        origin_idx: int,
        target_col: str,
        horizon_steps: int = 16,
        step_minutes: int = 15,
        actual_series: Optional[pd.Series] = None,
    ) -> pd.DataFrame:
        """Generate multi-step forward forecast from a specific origin index."""
        origin_row = history_df.iloc[origin_idx]
        t_origin = pd.to_datetime(origin_row["timestamp"])

        start_w = max(0, origin_idx - self.window + 1)
        w_vals = history_df.iloc[start_w:origin_idx + 1][target_col].values
        ma_val = float(np.mean(w_vals)) if len(w_vals) > 0 else float(origin_row[target_col])

        rows = []
        for step in range(1, horizon_steps + 1):
            horizon_mins = step * step_minutes
            t_target = t_origin + pd.Timedelta(minutes=horizon_mins)

            y_pred = ma_val
            if self.is_solar and _is_nighttime(t_target):
                y_pred = 0.0

            margin = 1.645 * self.residual_std_ * np.sqrt(step / 4.0)
            lb = max(0.0, y_pred - margin)
            ub = max(0.0, y_pred + margin)

            if self.is_solar and _is_nighttime(t_target):
                lb = 0.0
                ub = 0.0

            y_act = np.nan
            if actual_series is not None and (origin_idx + step) < len(actual_series):
                y_act = float(actual_series.iloc[origin_idx + step])

            rows.append({
                "timestamp": t_target,
                "forecast_origin": t_origin,
                "horizon_minutes": horizon_mins,
                "actual": y_act,
                "forecast": y_pred,
                "lower_bound": lb,
                "upper_bound": ub,
                "model": "MovingAverage",
                "target": self.target_name,
            })

        return pd.DataFrame(rows)
