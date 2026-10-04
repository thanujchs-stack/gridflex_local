"""Standardized Forecast Evaluation Metrics for GridFlex Local.

Computes MAE, RMSE, and sMAPE across models, targets, and forecast horizons,
with dedicated segregation for solar daylight vs all periods.
"""

from typing import Dict, List, Optional
import numpy as np
import pandas as pd


def compute_mae(actual: np.ndarray, forecast: np.ndarray) -> float:
    """Mean Absolute Error."""
    return float(np.mean(np.abs(actual - forecast)))


def compute_rmse(actual: np.ndarray, forecast: np.ndarray) -> float:
    """Root Mean Squared Error."""
    return float(np.sqrt(np.mean((actual - forecast) ** 2)))


def compute_smape(actual: np.ndarray, forecast: np.ndarray, eps: float = 1e-6) -> float:
    """Symmetric Mean Absolute Percentage Error (percentage, 0 to 200%)."""
    denom = np.abs(actual) + np.abs(forecast) + eps
    return float(np.mean(2.0 * np.abs(actual - forecast) / denom) * 100.0)


def calculate_forecast_metrics(
    forecast_df: pd.DataFrame,
    target_name: Optional[str] = None,
    is_solar: bool = False,
) -> pd.DataFrame:
    """Calculate summary and horizon-specific metrics from a standardized forecast DataFrame.

    Args:
        forecast_df: DataFrame with 'actual', 'forecast', 'model', 'target', 'horizon_minutes', 'timestamp'.
        target_name: Optional override for target name.
        is_solar: If True, evaluates daylight-only subset in addition to all periods.

    Returns:
        DataFrame containing metrics table ready for CSV export.
    """
    valid_df = forecast_df.dropna(subset=["actual", "forecast"]).copy()
    if valid_df.empty:
        return pd.DataFrame()

    target = target_name or str(valid_df["target"].iloc[0])
    records = []

    models = valid_df["model"].unique()

    for model in models:
        m_df = valid_df[valid_df["model"] == model]

        scopes = ["all"]
        if is_solar:
            scopes.append("daylight")

        for scope in scopes:
            if scope == "daylight":
                # Daylight filter: actual > 0.05 kW or solar hour between 6:00 and 18:15
                ts = pd.to_datetime(m_df["timestamp"])
                hour_float = ts.dt.hour + ts.dt.minute / 60.0
                daylight_mask = (m_df["actual"] > 0.05) | ((hour_float >= 6.0) & (hour_float <= 18.25))
                sub_df = m_df[daylight_mask]
            else:
                sub_df = m_df

            if len(sub_df) == 0:
                continue

            y_act = sub_df["actual"].values
            y_pred = sub_df["forecast"].values

            # Overall metrics across all horizons
            records.append({
                "target": target,
                "model": model,
                "horizon_minutes": "all (15-240m)",
                "period_scope": scope,
                "MAE": round(compute_mae(y_act, y_pred), 4),
                "RMSE": round(compute_rmse(y_act, y_pred), 4),
                "sMAPE": round(compute_smape(y_act, y_pred), 2),
                "sample_count": len(y_act),
            })

            # Key individual horizons: 15m (t+1), 60m (t+4), 120m (t+8), 240m (t+16)
            for h in [15, 60, 120, 240]:
                h_df = sub_df[sub_df["horizon_minutes"] == h]
                if len(h_df) > 0:
                    y_h_act = h_df["actual"].values
                    y_h_pred = h_df["forecast"].values
                    records.append({
                        "target": target,
                        "model": model,
                        "horizon_minutes": str(h),
                        "period_scope": scope,
                        "MAE": round(compute_mae(y_h_act, y_h_pred), 4),
                        "RMSE": round(compute_rmse(y_h_act, y_h_pred), 4),
                        "sMAPE": round(compute_smape(y_h_act, y_h_pred), 2),
                        "sample_count": len(y_h_act),
                    })

    return pd.DataFrame(records)
