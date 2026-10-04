"""Chronological train/validation/test splitting and data leakage verification.

Strictly prohibits random shuffling or temporal contamination across splits.
"""

from typing import Tuple, Dict, Any, Optional
import numpy as np
import pandas as pd


def chronological_train_val_test_split(
    df: pd.DataFrame,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    timestamp_col: str = "timestamp",
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Perform strict chronological split on time-series dataset.

    Args:
        df: Ordered time-series DataFrame.
        train_ratio: Proportion of earliest data allocated to training.
        val_ratio: Proportion of middle data allocated to validation.
        test_ratio: Proportion of latest data allocated to testing.
        timestamp_col: Name of datetime timestamp column.

    Returns:
        (train_df, val_df, test_df)
    """
    total_ratio = train_ratio + val_ratio + test_ratio
    if not np.isclose(total_ratio, 1.0, atol=1e-4):
        raise ValueError(f"Split ratios must sum to 1.0, got {total_ratio:.4f}")

    # Ensure strictly sorted by timestamp
    sorted_df = df.sort_values(timestamp_col).reset_index(drop=True)
    n = len(sorted_df)

    n_train = int(n * train_ratio)
    n_val = int(n * val_ratio)

    train_df = sorted_df.iloc[:n_train].copy().reset_index(drop=True)
    val_df = sorted_df.iloc[n_train:n_train + n_val].copy().reset_index(drop=True)
    test_df = sorted_df.iloc[n_train + n_val:].copy().reset_index(drop=True)

    is_valid, msg = verify_no_leakage(train_df, val_df, test_df, timestamp_col=timestamp_col)
    if not is_valid:
        raise ValueError(f"Chronological split failed data leakage verification: {msg}")

    return train_df, val_df, test_df


def verify_no_leakage(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
    timestamp_col: str = "timestamp",
) -> Tuple[bool, str]:
    """Verify that train, validation, and test splits have zero chronological overlap.

    Returns:
        (is_valid, message)
    """
    if train_df.empty or val_df.empty or test_df.empty:
        return False, "One or more splits are empty."

    t_train_max = pd.to_datetime(train_df[timestamp_col].max())
    t_val_min = pd.to_datetime(val_df[timestamp_col].min())
    t_val_max = pd.to_datetime(val_df[timestamp_col].max())
    t_test_min = pd.to_datetime(test_df[timestamp_col].min())

    if t_train_max >= t_val_min:
        return False, f"Temporal leakage: train_max ({t_train_max}) >= val_min ({t_val_min})"

    if t_val_max >= t_test_min:
        return False, f"Temporal leakage: val_max ({t_val_max}) >= test_min ({t_test_min})"

    # Monotonicity check
    for name, split in [("Train", train_df), ("Val", val_df), ("Test", test_df)]:
        diffs = pd.to_datetime(split[timestamp_col]).diff().dropna()
        if (diffs <= pd.Timedelta(0)).any():
            return False, f"{name} split is not strictly monotonically increasing in time."

    return True, "Chronological integrity verified: zero temporal leakage."
