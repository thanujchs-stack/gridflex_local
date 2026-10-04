"""Direct Multi-Step Tree-Based Forecaster using HistGradientBoostingRegressor.

Provides fast, reproducible, lightweight gradient boosted regression for
load, PV, and net load with calibrated empirical prediction intervals.
"""

from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor


def _is_nighttime(timestamp: pd.Timestamp) -> bool:
    """Check if given timestamp is during solar nighttime."""
    hour_float = timestamp.hour + timestamp.minute / 60.0
    return bool(hour_float < 6.0 or hour_float > 18.25)


class MultiStepHistGradientBoostingForecaster:
    """Direct multi-step forecaster training an ensemble of 16 horizon-specific models."""

    def __init__(
        self,
        target_name: str = "load",
        horizon_steps: int = 16,
        step_minutes: int = 15,
        is_solar: bool = False,
        random_state: int = 42,
        max_iter: int = 100,
        max_depth: int = 6,
        min_samples_leaf: int = 20,
    ):
        self.target_name = target_name
        self.horizon_steps = horizon_steps
        self.step_minutes = step_minutes
        self.is_solar = is_solar
        self.random_state = random_state
        self.max_iter = max_iter
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf

        self.models_: Dict[int, HistGradientBoostingRegressor] = {}
        self.residual_stds_: Dict[int, float] = {}
        self.feature_cols_: List[str] = []

    def fit(
        self,
        train_df: pd.DataFrame,
        val_df: pd.DataFrame,
        target_col: str,
        feature_cols: List[str],
    ) -> "MultiStepHistGradientBoostingForecaster":
        """Train separate direct models for each horizon step and calibrate prediction intervals on validation set."""
        self.feature_cols_ = list(feature_cols)

        X_train = train_df[self.feature_cols_].values
        X_val = val_df[self.feature_cols_].values

        for step in range(1, self.horizon_steps + 1):
            # Target is shifted forward by `step`
            y_train = train_df[target_col].shift(-step).values
            y_val = val_df[target_col].shift(-step).values

            # Drop boundary NaNs from target shifting
            valid_train = ~np.isnan(y_train)
            valid_val = ~np.isnan(y_val)

            model = HistGradientBoostingRegressor(
                loss="squared_error",
                max_iter=self.max_iter,
                max_depth=self.max_depth,
                min_samples_leaf=self.min_samples_leaf,
                random_state=self.random_state + step,
            )
            model.fit(X_train[valid_train], y_train[valid_train])
            self.models_[step] = model

            # Calibrate empirical uncertainty on validation set
            val_preds = model.predict(X_val[valid_val])
            val_resids = y_val[valid_val] - val_preds
            std_resid = float(np.std(val_resids)) if len(val_resids) > 0 else 1.0
            self.residual_stds_[step] = max(0.01, std_resid)

        return self

    def predict_origin(
        self,
        feature_row: pd.Series,
        forecast_origin: pd.Timestamp,
        actual_forward_series: Optional[pd.Series] = None,
    ) -> pd.DataFrame:
        """Generate 16-step forward forecast from a single forecast origin timestamp.

        Returns DataFrame matching required standard format.
        """
        X = feature_row[self.feature_cols_].values.reshape(1, -1)
        rows = []

        for step in range(1, self.horizon_steps + 1):
            horizon_mins = step * self.step_minutes
            t_target = forecast_origin + pd.Timedelta(minutes=horizon_mins)

            model = self.models_[step]
            pred = float(model.predict(X)[0])

            # Apply domain constraints
            if self.is_solar:
                if _is_nighttime(t_target):
                    pred = 0.0
                else:
                    pred = max(0.0, pred)
            elif "load" in self.target_name.lower():
                pred = max(0.0, pred)

            # Prediction interval (90% interval: +/- 1.645 sigma)
            sigma = self.residual_stds_.get(step, 1.0)
            lb = pred - 1.645 * sigma
            ub = pred + 1.645 * sigma

            if self.is_solar:
                if _is_nighttime(t_target):
                    lb = 0.0
                    ub = 0.0
                else:
                    lb = max(0.0, lb)
                    ub = max(0.0, ub)
            elif "load" in self.target_name.lower():
                lb = max(0.0, lb)

            act_val = np.nan
            if actual_forward_series is not None and (step - 1) < len(actual_forward_series):
                act_val = float(actual_forward_series.iloc[step - 1])

            rows.append({
                "timestamp": t_target,
                "forecast_origin": forecast_origin,
                "horizon_minutes": horizon_mins,
                "actual": act_val,
                "forecast": pred,
                "lower_bound": lb,
                "upper_bound": ub,
                "model": "HistGradientBoosting",
                "target": self.target_name,
            })

        return pd.DataFrame(rows)

    def forecast_series(
        self,
        test_df: pd.DataFrame,
        target_col: str,
        stride: int = 16,
    ) -> pd.DataFrame:
        """Generate forecasts across test dataset with specified stride between forecast origins.

        Args:
            test_df: Feature-engineered test split.
            target_col: Target column name.
            stride: Timestep interval between consecutive forecast origins (e.g. 16 steps = every 4 hours).

        Returns:
            Concatenated DataFrame of all 16-step forecast trajectories.
        """
        all_forecasts = []
        max_origin_idx = len(test_df) - self.horizon_steps

        for idx in range(0, max_origin_idx, stride):
            origin_row = test_df.iloc[idx]
            origin_ts = pd.to_datetime(origin_row["timestamp"])
            actual_fwd = test_df.iloc[idx + 1:idx + 1 + self.horizon_steps][target_col]

            fc_df = self.predict_origin(
                feature_row=origin_row,
                forecast_origin=origin_ts,
                actual_forward_series=actual_fwd,
            )
            all_forecasts.append(fc_df)

        if not all_forecasts:
            return pd.DataFrame()

        return pd.concat(all_forecasts, ignore_index=True)
