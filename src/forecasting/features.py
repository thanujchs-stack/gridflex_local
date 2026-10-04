"""Feature engineering for time-series forecasting in GridFlex Local.

Enforces STRICT chronological safety:
- All lag features use indices >= 1 (t-1, t-2, etc.).
- All rolling statistics operate strictly on prior observations (shift(1).rolling(...)).
- Cyclic time encodings (sin/cos) preserve diurnal and annual continuity.
"""

from typing import List, Optional
import numpy as np
import pandas as pd


def generate_forecasting_features(
    df: pd.DataFrame,
    target_col: str,
    solar_col: Optional[str] = None,
    irradiance_col: Optional[str] = None,
    include_grid_features: bool = True,
    load_col: Optional[str] = None,
    pv_col: Optional[str] = None,
) -> pd.DataFrame:
    """Generate chronological feature matrix for multi-step forecasting.

    Args:
        df: Input DataFrame containing 'timestamp' and numeric timeseries.
        target_col: Name of column being forecast (e.g. 'total_load_kw' or 'total_pv_kw').
        solar_col: Optional column for solar PV generation.
        irradiance_col: Optional column for GHI (W/m²).
        include_grid_features: If True, computes net load and joint interactions.
        load_col: Optional column for gross load (if target is net_load).
        pv_col: Optional column for gross PV (if target is net_load).

    Returns:
        DataFrame with added feature columns.
    """
    out = df.copy()
    if not np.issubdtype(out["timestamp"].dtype, np.datetime64):
        out["timestamp"] = pd.to_datetime(out["timestamp"])

    ts = out["timestamp"]

    # 1. Temporal & Calendar Features
    hour_float = ts.dt.hour + ts.dt.minute / 60.0
    out["hour"] = ts.dt.hour
    out["minute"] = ts.dt.minute
    out["block_96"] = (ts.dt.hour * 4 + ts.dt.minute // 15).astype(int)
    out["dayofweek"] = ts.dt.dayofweek
    out["is_weekend"] = (ts.dt.dayofweek >= 5).astype(int)
    out["month"] = ts.dt.month
    out["dayofyear"] = ts.dt.dayofyear

    # Cyclic encodings
    out["hour_sin"] = np.sin(2 * np.pi * hour_float / 24.0)
    out["hour_cos"] = np.cos(2 * np.pi * hour_float / 24.0)
    out["doy_sin"] = np.sin(2 * np.pi * out["dayofyear"] / 365.25)
    out["doy_cos"] = np.cos(2 * np.pi * out["dayofyear"] / 365.25)

    # 2. Solar Availability & Proxy Features
    # Solar daylight window approx 06:00 to 18:15
    daylight_mask = (hour_float >= 6.0) & (hour_float <= 18.25)
    out["solar_hour_avail"] = daylight_mask.astype(int)
    # Smooth half-sine elevation proxy
    solar_angle = np.clip((hour_float - 6.0) / 12.25 * np.pi, 0.0, np.pi)
    out["solar_elevation_proxy"] = np.where(daylight_mask, np.sin(solar_angle), 0.0)

    # 3. Target Lag Features (STRICTLY >= 1, NO CURRENT OR FUTURE TARGETS)
    target_series = out[target_col]
    lags = [1, 2, 4, 8, 16, 96, 192]
    for lag in lags:
        out[f"{target_col}_lag_{lag}"] = target_series.shift(lag)

    # 4. Target Rolling Statistics (STRICTLY ON PAST DATA: shift(1))
    past_series = target_series.shift(1)
    out[f"{target_col}_roll_mean_4"] = past_series.rolling(window=4, min_periods=1).mean()
    out[f"{target_col}_roll_std_4"] = past_series.rolling(window=4, min_periods=1).std().fillna(0.0)
    out[f"{target_col}_roll_min_4"] = past_series.rolling(window=4, min_periods=1).min()
    out[f"{target_col}_roll_max_4"] = past_series.rolling(window=4, min_periods=1).max()

    out[f"{target_col}_roll_mean_16"] = past_series.rolling(window=16, min_periods=1).mean()
    out[f"{target_col}_roll_std_16"] = past_series.rolling(window=16, min_periods=1).std().fillna(0.0)

    out[f"{target_col}_roll_mean_96"] = past_series.rolling(window=96, min_periods=1).mean()

    # 5. Solar Resource Lags (if available)
    if solar_col and solar_col in out.columns and solar_col != target_col:
        pv_past = out[solar_col].shift(1)
        out[f"{solar_col}_lag_1"] = out[solar_col].shift(1)
        out[f"{solar_col}_lag_4"] = out[solar_col].shift(4)
        out[f"{solar_col}_roll_mean_4"] = pv_past.rolling(window=4, min_periods=1).mean()

    if irradiance_col and irradiance_col in out.columns:
        out[f"{irradiance_col}_lag_1"] = out[irradiance_col].shift(1)
        out[f"{irradiance_col}_lag_4"] = out[irradiance_col].shift(4)

    # 6. Grid / Net Load Features
    if include_grid_features:
        l_col = load_col or ("total_load_kw" if "total_load_kw" in out.columns else None)
        p_col = pv_col or ("total_pv_kw" if "total_pv_kw" in out.columns else None)
        if l_col and p_col:
            # Past net load strictly shifted
            past_net = (out[l_col] - out[p_col]).shift(1)
            out["net_load_lag_1"] = past_net
            out["net_load_roll_mean_4"] = past_net.rolling(window=4, min_periods=1).mean()

    return out


def get_feature_columns(
    df: pd.DataFrame,
    target_col: str,
    exclude_cols: Optional[List[str]] = None
) -> List[str]:
    """Retrieve list of purely predictor feature column names (excluding timestamps and targets)."""
    exclude = set(exclude_cols or [])
    exclude.update(["timestamp", target_col])
    # Also exclude future targets or unshifted contemporaneous loads/pvs if present
    features = [c for c in df.columns if c not in exclude and not c.startswith("future_target_")]
    return sorted(features)
