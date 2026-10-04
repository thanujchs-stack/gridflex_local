"""Validation utilities for GridFlex Local Phase 1.

Enforces physical and simulation invariants:
- Time-series sanity (sorted, unique, complete, no NaN/inf)
- Non-negativity of physical loads and PV generation
- Asset capacity bounds (PV <= rated capacity, EV <= charger limit)
- Battery state of charge (SOC) limits
- Power balance conservation across the distribution feeder
"""

from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


def validate_timestamps(df: pd.DataFrame, expected_step_minutes: int = 15) -> None:
    """Validate that timestamp column exists, is strictly increasing, and has no missing intervals."""
    if "timestamp" not in df.columns:
        raise ValueError("DataFrame must contain a 'timestamp' column.")

    ts = pd.to_datetime(df["timestamp"])

    if ts.isna().any():
        raise ValueError("Timestamp column contains NaN / NaT values.")

    if not ts.is_monotonic_increasing:
        raise ValueError("Timestamps are not strictly monotonically increasing.")

    if ts.duplicated().any():
        dups = ts[ts.duplicated()].tolist()
        raise ValueError(f"Duplicate timestamps detected: {dups[:5]}")

    if len(ts) > 1:
        diffs = ts.diff().dropna()
        expected_delta = pd.Timedelta(minutes=expected_step_minutes)
        abnormal = diffs[diffs != expected_delta]
        if not abnormal.empty:
            raise ValueError(
                f"Missing or irregular timestep detected. Expected step: {expected_delta}, "
                f"found irregular diffs: {abnormal.iloc[0]} at index {abnormal.index[0]}"
            )


def validate_no_nan_or_inf(df: pd.DataFrame, name: str = "DataFrame") -> None:
    """Check that all numeric columns have neither NaN nor infinite values."""
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    if df[numeric_cols].isna().any().any():
        cols_with_nan = df[numeric_cols].columns[df[numeric_cols].isna().any()].tolist()
        raise ValueError(f"{name} contains NaN values in columns: {cols_with_nan}")

    arr = df[numeric_cols].to_numpy()
    if np.isinf(arr).any():
        cols_with_inf = df[numeric_cols].columns[np.isinf(df[numeric_cols]).any()].tolist()
        raise ValueError(f"{name} contains infinite values in columns: {cols_with_inf}")


def validate_load_profiles(df: pd.DataFrame, load_cols: Optional[List[str]] = None) -> None:
    """Ensure loads are strictly non-negative (no negative demand)."""
    validate_timestamps(df)
    validate_no_nan_or_inf(df, "Load Profiles")

    if load_cols is None:
        load_cols = [c for c in df.columns if c != "timestamp"]

    for col in load_cols:
        negatives = df[df[col] < -1e-6]
        if not negatives.empty:
            min_val = df[col].min()
            first_idx = negatives.index[0]
            raise ValueError(
                f"Load column '{col}' has negative values (min: {min_val:.4f} kW) at timestamp {df.loc[first_idx, 'timestamp']}"
            )


def validate_solar_profiles(df: pd.DataFrame, capacities: Optional[Dict[str, float]] = None) -> None:
    """Ensure PV generation is non-negative and does not exceed rated capacity."""
    validate_timestamps(df)
    validate_no_nan_or_inf(df, "Solar Profiles")

    pv_cols = [c for c in df.columns if c != "timestamp"]
    for col in pv_cols:
        negatives = df[df[col] < -1e-6]
        if not negatives.empty:
            min_val = df[col].min()
            raise ValueError(f"Solar PV column '{col}' has negative generation: {min_val:.4f} kW")

        if capacities and col in capacities:
            cap = capacities[col]
            over_cap = df[df[col] > cap * 1.001]
            if not over_cap.empty:
                max_val = df[col].max()
                raise ValueError(
                    f"Solar PV column '{col}' exceeds rated capacity {cap:.2f} kW (observed: {max_val:.2f} kW)"
                )


def validate_ev_profiles(df: pd.DataFrame, max_chargers: Optional[Dict[str, float]] = None) -> None:
    """Ensure EV charging is non-negative and within charger ratings."""
    validate_timestamps(df)
    validate_no_nan_or_inf(df, "EV Profiles")

    ev_cols = [c for c in df.columns if c != "timestamp"]
    for col in ev_cols:
        negatives = df[df[col] < -1e-6]
        if not negatives.empty:
            raise ValueError(f"EV charging column '{col}' has negative values: {df[col].min():.4f} kW")

        if max_chargers and col in max_chargers:
            rating = max_chargers[col]
            over_rate = df[df[col] > rating * 1.001]
            if not over_rate.empty:
                raise ValueError(
                    f"EV charging column '{col}' exceeds charger limit {rating:.2f} kW (observed: {df[col].max():.2f} kW)"
                )


def validate_battery_soc(
    soc_series: pd.Series,
    min_soc: float,
    max_soc: float,
    tolerance: float = 1e-4
) -> None:
    """Verify that battery State of Charge stays within operational bounds [min_soc, max_soc]."""
    if (soc_series < (min_soc - tolerance)).any():
        min_observed = soc_series.min()
        raise ValueError(
            f"Battery SOC violated minimum boundary: min_observed={min_observed:.4f}, min_limit={min_soc:.4f}"
        )

    if (soc_series > (max_soc + tolerance)).any():
        max_observed = soc_series.max()
        raise ValueError(
            f"Battery SOC violated maximum boundary: max_observed={max_observed:.4f}, max_limit={max_soc:.4f}"
        )


def validate_power_balance(
    p_grid_import: pd.Series,
    p_pv_generation: pd.Series,
    p_bess_discharge: pd.Series,
    p_total_load: pd.Series,
    p_bess_charge: pd.Series,
    p_losses: pd.Series,
    tolerance_kw: float = 1.0
) -> Tuple[float, float, int, pd.Series]:
    """Validate power conservation across the LV feeder at each timestep.

    Power Conservation:
        Total Inflow (Generation + Import) = Total Outflow (Demand + Losses + Storage)
        P_grid_net + P_pv = P_load + P_loss + P_bess_net
        where:
        Inflow  = p_grid_import + p_pv_generation + p_bess_discharge
        Outflow = p_total_load + p_bess_charge + p_losses + p_grid_export (if split)

    Returns:
        (max_abs_error_kw, mean_abs_error_kw, failed_timesteps_count, error_series)
    """
    total_supply = p_grid_import + p_pv_generation + p_bess_discharge
    total_demand_and_losses = p_total_load + p_bess_charge + p_losses

    power_mismatch = (total_supply - total_demand_and_losses).abs()
    max_err = float(power_mismatch.max())
    mean_err = float(power_mismatch.mean())
    failures = int((power_mismatch > tolerance_kw).sum())

    return max_err, mean_err, failures, power_mismatch
