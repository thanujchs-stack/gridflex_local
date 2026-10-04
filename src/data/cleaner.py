"""Data cleaning module for GridFlex Local.

Handles controlled cleaning, missing data quantification, duplicate removal,
and physical validity corrections without discarding realistic demand spikes.
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)


class DataCleaner:
    """Cleans time-series data while preserving physical fidelity and auditing actions."""

    def __init__(self, max_interpolation_gap: int = 2):
        """Args:

        max_interpolation_gap: Maximum consecutive missing steps to
        interpolate. Gaps larger than this remain unfilled or are handled per
        policy.
        """
        self.max_interpolation_gap = max_interpolation_gap

    def clean_timeseries(
        self,
        df: pd.DataFrame,
        value_cols: list[str],
        timestamp_col: str = "timestamp",
        group_col: Optional[str] = None,
        clamp_min_zero: bool = True,
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """Clean timeseries dataframe.

        1. Deduplicate by timestamp (and group_col if present).
        2. Ensure chronological order.
        3. Clamp physically invalid negative values to 0.0 (if clamp_min_zero=True).
        4. Track missing values before/after controlled interpolation.
        """
        cleaned = df.copy()

        # Step 1: Sort timestamps
        if group_col:
            cleaned = cleaned.sort_values(by=[group_col, timestamp_col]).reset_index(drop=True)
            dup_mask = cleaned.duplicated(subset=[group_col, timestamp_col], keep="first")
        else:
            cleaned = cleaned.sort_values(by=timestamp_col).reset_index(drop=True)
            dup_mask = cleaned.duplicated(subset=[timestamp_col], keep="first")

        duplicate_count = int(dup_mask.sum())
        if duplicate_count > 0:
            logger.info("Dropping %d duplicate timestamp records", duplicate_count)
            cleaned = cleaned[~dup_mask].reset_index(drop=True)

        stats: Dict[str, Any] = {
            "initial_rows": len(df),
            "duplicates_dropped": duplicate_count,
            "negative_clamped": {},
            "missing_before": {},
            "number_of_filled_values": 0,
            "number_of_remaining_missing_values": 0,
            "longest_missing_gap": {},
        }

        for col in value_cols:
            if col not in cleaned.columns:
                continue

            # Check negative values
            neg_mask = cleaned[col] < 0.0
            neg_count = int(neg_mask.sum())
            stats["negative_clamped"][col] = neg_count
            if clamp_min_zero and neg_count > 0:
                logger.info("Clamping %d physically invalid negative values to 0.0 in col '%s'", neg_count, col)
                cleaned.loc[neg_mask, col] = 0.0

            # Missing value audit
            missing_before = int(cleaned[col].isna().sum())
            stats["missing_before"][col] = missing_before

            # Calculate longest consecutive missing interval
            is_na = cleaned[col].isna().astype(int)
            if missing_before > 0:
                blocks = (is_na != is_na.shift()).cumsum()
                max_gap = int(is_na.groupby(blocks).sum().max())
            else:
                max_gap = 0
            stats["longest_missing_gap"][col] = max_gap

            # Controlled interpolation: interpolate only short gaps <= max_interpolation_gap
            if missing_before > 0 and self.max_interpolation_gap > 0:
                if group_col:
                    cleaned[col] = cleaned.groupby(group_col)[col].transform(
                        lambda s: s.interpolate(method="linear", limit=self.max_interpolation_gap, limit_direction="both")
                    )
                else:
                    cleaned[col] = cleaned[col].interpolate(
                        method="linear",
                        limit=self.max_interpolation_gap,
                        limit_direction="both",
                    )

            missing_after = int(cleaned[col].isna().sum())
            filled_count = missing_before - missing_after
            stats["number_of_filled_values"] += filled_count
            stats["number_of_remaining_missing_values"] += missing_after

        stats["final_rows"] = len(cleaned)
        return cleaned, stats
