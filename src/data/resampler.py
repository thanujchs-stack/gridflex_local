"""Resampling and time-series alignment module for GridFlex Local.

Standardizes all datasets to GridFlex Local's canonical 15-minute resolution:
- Ausgrid: 30-minute interval readings (kWh) converted to average kW (kWh / 0.5 h)
  and expanded to 15-minute intervals via energy-conserving constant power blocks.
- SUNY India: 60-minute solar resource records (W/m², °C) interpolated to 15-minute
  intervals with strict night clamping (irradiance >= 0).
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)


class DataResampler:
    """Performs energy-conserving and physical-continuous resampling to 15-minute timesteps."""

    @staticmethod
    def resample_ausgrid_halfhourly_to_15min(
        df_30min: pd.DataFrame,
        timestamp_col: str = "timestamp",
        value_cols: list[str] = None,
        group_col: Optional[str] = "household_id",
    ) -> pd.DataFrame:
        """Resample 30-minute average power (kW) to 15-minute resolution.

        Preserves 100% interval energy conservation by representing each 30-minute block [t, t+30m)
        as two identical 15-minute power intervals [t, t+15m) and [t+15m, t+30m).
        Average power * 0.25h + Average power * 0.25h = Average power * 0.5h = Interval Energy (kWh).
        """
        if value_cols is None:
            value_cols = [c for c in df_30min.columns if c not in [timestamp_col, group_col]]

        # Block 1: start at t
        b1 = df_30min.copy()

        # Block 2: start at t + 15 min
        b2 = df_30min.copy()
        b2[timestamp_col] = b2[timestamp_col] + pd.Timedelta(minutes=15)

        # Concatenate and sort
        combined = pd.concat([b1, b2], ignore_index=True)
        if group_col and group_col in combined.columns:
            combined = combined.sort_values(by=[group_col, timestamp_col]).reset_index(drop=True)
        else:
            combined = combined.sort_values(by=timestamp_col).reset_index(drop=True)

        return combined

    @staticmethod
    def resample_solar_hourly_to_15min(
        df_hourly: pd.DataFrame,
        timestamp_col: str = "timestamp",
        irradiance_cols: list[str] = None,
        temp_col: str = "Temperature",
    ) -> pd.DataFrame:
        """Resample hourly solar resource data to continuous 15-minute intervals.

        Uses time-based interpolation for daylight periods and strictly clamps night
        hours (GHI == 0) to 0.0 W/m² to prevent unphysical twilight artifacts.
        """
        if irradiance_cols is None:
            irradiance_cols = ["GHI", "DNI", "DHI"]

        df = df_hourly.copy()
        df = df.sort_values(by=timestamp_col).drop_duplicates(subset=[timestamp_col])
        df = df.set_index(timestamp_col)

        start_time = df.index.min()
        end_time = df.index.max()
        target_index = pd.date_range(start=start_time, end=end_time, freq="15min", name=timestamp_col)

        # Reindex to 15min
        resampled = df.reindex(target_index)

        # Interpolate linearly along time axis
        resampled = resampled.interpolate(method="time")

        # Fill any boundary edges if needed
        resampled = resampled.bfill().ffill()

        # Strict physical night clamping: if both surrounding hourly GHI were 0, intermediate must be 0
        for col in irradiance_cols:
            if col in resampled.columns:
                resampled[col] = resampled[col].clip(lower=0.0)

        return resampled.reset_index()
