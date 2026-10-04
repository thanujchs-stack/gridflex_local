"""Unit tests for GridFlex Local Phase 3 Forecasting Package.

Tests compliance with requirements:
- Chronological split
- No data leakage
- Feature generation
- Lag correctness
- Rolling-feature correctness
- Forecast horizon = 16 steps
- Timestamp alignment
- Uncertainty interval validity
- PV nighttime behaviour
- Metric calculation
- Flexibility forecast constraints
- Reproducibility
"""

import numpy as np
import pandas as pd
import pytest

from src.forecasting.features import generate_forecasting_features, get_feature_columns
from src.forecasting.split import chronological_train_val_test_split, verify_no_leakage
from src.forecasting.baselines import PersistenceForecaster, MovingAverageForecaster
from src.forecasting.models import MultiStepHistGradientBoostingForecaster
from src.forecasting.metrics import calculate_forecast_metrics, compute_mae, compute_rmse, compute_smape
from src.forecasting.flexibility_forecaster import forecast_available_flexibility
from src.utils.config import load_config


@pytest.fixture
def synthetic_timeseries():
    """Create a 5-day 15-minute synthetic time-series for deterministic testing."""
    dates = pd.date_range("2026-01-01 00:00", periods=5 * 96, freq="15min")
    hour = dates.hour + dates.minute / 60.0
    # Synthetic load with diurnal pattern
    load = 100.0 + 40.0 * np.sin((hour - 8) / 24.0 * 2 * np.pi) + np.random.RandomState(42).normal(0, 5, len(dates))
    load = np.maximum(load, 10.0)

    # Synthetic PV: daylight between 6:00 and 18:00
    daylight = (hour >= 6.0) & (hour <= 18.0)
    pv = np.where(daylight, 60.0 * np.sin((hour - 6.0) / 12.0 * np.pi), 0.0)

    return pd.DataFrame({
        "timestamp": dates,
        "total_load_kw": load,
        "total_pv_kw": pv,
        "ghi_wm2": pv * 15.0,
    })


def test_chronological_split(synthetic_timeseries):
    """Verify split partitions dataset chronologically without shuffle."""
    tr, val, te = chronological_train_val_test_split(
        synthetic_timeseries, train_ratio=0.70, val_ratio=0.15, test_ratio=0.15
    )

    assert len(tr) + len(val) + len(te) == len(synthetic_timeseries)
    assert tr["timestamp"].max() < val["timestamp"].min()
    assert val["timestamp"].max() < te["timestamp"].min()


def test_no_data_leakage(synthetic_timeseries):
    """Verify data leakage detection function identifies valid and contaminated splits."""
    tr, val, te = chronological_train_val_test_split(synthetic_timeseries)
    is_valid, msg = verify_no_leakage(tr, val, te)
    assert is_valid is True

    # Artificially create temporal overlap leak
    leaky_val = val.copy()
    leaky_val.iloc[0, leaky_val.columns.get_loc("timestamp")] = tr["timestamp"].max() - pd.Timedelta(minutes=15)
    is_valid_leaked, leak_msg = verify_no_leakage(tr, leaky_val, te)
    assert is_valid_leaked is False
    assert "leakage" in leak_msg.lower()


def test_feature_generation(synthetic_timeseries):
    """Verify feature generator creates required temporal, cyclic, lag, and rolling columns."""
    df_feat = generate_forecasting_features(
        synthetic_timeseries,
        target_col="total_load_kw",
        solar_col="total_pv_kw",
        irradiance_col="ghi_wm2",
    )

    expected_cols = [
        "hour", "minute", "block_96", "dayofweek", "is_weekend",
        "hour_sin", "hour_cos", "doy_sin", "doy_cos",
        "solar_hour_avail", "solar_elevation_proxy",
        "total_load_kw_lag_1", "total_load_kw_lag_2", "total_load_kw_lag_4",
        "total_load_kw_roll_mean_4", "total_load_kw_roll_std_4",
        "net_load_lag_1",
    ]
    for col in expected_cols:
        assert col in df_feat.columns, f"Missing feature column: {col}"


def test_lag_correctness(synthetic_timeseries):
    """Verify lag features strictly equal past values shifted in time."""
    df_feat = generate_forecasting_features(synthetic_timeseries, target_col="total_load_kw")

    # lag_1 at index 10 should equal actual target at index 9
    assert df_feat["total_load_kw_lag_1"].iloc[10] == synthetic_timeseries["total_load_kw"].iloc[9]
    # lag_4 at index 20 should equal actual target at index 16
    assert df_feat["total_load_kw_lag_4"].iloc[20] == synthetic_timeseries["total_load_kw"].iloc[16]


def test_rolling_feature_correctness(synthetic_timeseries):
    """Verify rolling statistics at time t use strictly observations prior to t."""
    df_feat = generate_forecasting_features(synthetic_timeseries, target_col="total_load_kw")

    # At row 10, roll_mean_4 must be mean of rows 6, 7, 8, 9 (NOT row 10)
    expected_mean_at_10 = synthetic_timeseries["total_load_kw"].iloc[6:10].mean()
    actual_mean_at_10 = df_feat["total_load_kw_roll_mean_4"].iloc[10]
    assert np.isclose(expected_mean_at_10, actual_mean_at_10, atol=1e-5)

    # Modifying value at row 10 should NOT change rolling feature at row 10
    synth_modified = synthetic_timeseries.copy()
    synth_modified.loc[10, "total_load_kw"] += 9999.0
    df_feat_mod = generate_forecasting_features(synth_modified, target_col="total_load_kw")
    assert np.isclose(df_feat_mod["total_load_kw_roll_mean_4"].iloc[10], expected_mean_at_10, atol=1e-5)


def test_forecast_horizon_16_steps(synthetic_timeseries):
    """Verify forecasting models produce exactly 16 future steps."""
    forecaster = PersistenceForecaster(target_name="load")
    forecaster.fit(synthetic_timeseries["total_load_kw"])

    fc = forecaster.forecast(
        history_df=synthetic_timeseries,
        origin_idx=50,
        target_col="total_load_kw",
        horizon_steps=16,
        step_minutes=15,
    )
    assert len(fc) == 16
    assert fc["horizon_minutes"].tolist() == [15 * i for i in range(1, 17)]


def test_timestamp_alignment(synthetic_timeseries):
    """Verify forecast timestamps align exactly with 15-minute grid spacing."""
    forecaster = MovingAverageForecaster(target_name="load", window=4)
    forecaster.fit(synthetic_timeseries["total_load_kw"])

    origin_ts = synthetic_timeseries["timestamp"].iloc[100]
    fc = forecaster.forecast(
        history_df=synthetic_timeseries,
        origin_idx=100,
        target_col="total_load_kw",
        horizon_steps=16,
        step_minutes=15,
    )

    for i, t in enumerate(fc["timestamp"]):
        expected_t = origin_ts + pd.Timedelta(minutes=(i + 1) * 15)
        assert t == expected_t


def test_uncertainty_interval_validity(synthetic_timeseries):
    """Verify lower_bound <= forecast <= upper_bound for non-negative loads."""
    df_feat = generate_forecasting_features(synthetic_timeseries, target_col="total_load_kw")
    tr, val, te = chronological_train_val_test_split(df_feat)
    feat_cols = get_feature_columns(df_feat, target_col="total_load_kw")

    ml = MultiStepHistGradientBoostingForecaster(target_name="load", horizon_steps=16, max_iter=20)
    ml.fit(tr, val, "total_load_kw", feat_cols)

    origin_row = te.iloc[10]
    fc = ml.predict_origin(origin_row, pd.to_datetime(origin_row["timestamp"]))

    assert (fc["lower_bound"] <= fc["forecast"] + 1e-4).all()
    assert (fc["forecast"] <= fc["upper_bound"] + 1e-4).all()
    assert (fc["lower_bound"] >= 0.0).all()  # non-negative load bound


def test_pv_nighttime_behaviour(synthetic_timeseries):
    """Verify PV forecasts are strictly zeroed during nighttime periods."""
    forecaster = PersistenceForecaster(target_name="pv", is_solar=True)
    forecaster.fit(synthetic_timeseries["total_pv_kw"])

    # Forecast starting at 22:00 (nighttime)
    night_idx = synthetic_timeseries[synthetic_timeseries["timestamp"].dt.hour == 22].index[0]
    fc = forecaster.forecast(
        history_df=synthetic_timeseries,
        origin_idx=night_idx,
        target_col="total_pv_kw",
        horizon_steps=16,
    )

    # Next 4 hours (22:15 to 02:00) must all be 0.0
    assert (fc["forecast"] == 0.0).all()
    assert (fc["lower_bound"] == 0.0).all()
    assert (fc["upper_bound"] == 0.0).all()


def test_metric_calculation():
    """Verify MAE, RMSE, and sMAPE formula calculations."""
    act = np.array([100.0, 150.0, 200.0])
    pred = np.array([110.0, 140.0, 200.0])

    assert np.isclose(compute_mae(act, pred), 6.666667, atol=1e-4)
    assert np.isclose(compute_rmse(act, pred), 8.164965, atol=1e-4)
    # sMAPE: 200 * |10| / 210 + 200 * |10| / 290 + 0 = 9.5238 + 6.8965 = 16.42 / 3 = ~5.47%
    assert compute_smape(act, pred) > 0.0


def test_flexibility_forecast_constraints():
    """Verify forward available flexibility respects technical limits, SOC floor, and participation."""
    cfg = load_config()
    dates = pd.date_range("2026-01-15 12:00", periods=16, freq="15min")
    pv_kw = np.full(16, 50.0)

    # SOC at 0.50 (well above 0.30 reserve floor)
    flex_df = forecast_available_flexibility(
        forecast_timestamps=list(dates),
        pv_forecast_kw=pv_kw,
        config=cfg,
        bess_current_soc=0.50,
    )

    assert len(flex_df) == 16
    # Technical flexibility must be >= Available flexibility
    assert (flex_df["total_up_technical_kw"] >= flex_df["total_up_available_kw"]).all()
    assert (flex_df["total_down_technical_kw"] >= flex_df["total_down_available_kw"]).all()
    # PV downward available must equal forecast * participation (50 * 0.70 = 35 kW)
    assert np.isclose(flex_df["pv_down_kw"].iloc[0], 35.0, atol=1e-2)

    # Test SOC at floor (0.30) -> zero discharge up-flexibility available
    flex_floor = forecast_available_flexibility(
        forecast_timestamps=list(dates),
        pv_forecast_kw=pv_kw,
        config=cfg,
        bess_current_soc=0.30,
    )
    assert np.isclose(flex_floor["bess_up_kw"].iloc[0], 0.0, atol=1e-2)


def test_forecasting_reproducibility(synthetic_timeseries):
    """Verify that models initialized with random_state=42 generate byte-identical predictions."""
    df_feat = generate_forecasting_features(synthetic_timeseries, target_col="total_load_kw")
    tr, val, te = chronological_train_val_test_split(df_feat)
    feat_cols = get_feature_columns(df_feat, target_col="total_load_kw")

    m1 = MultiStepHistGradientBoostingForecaster(random_state=42, max_iter=20)
    m1.fit(tr, val, "total_load_kw", feat_cols)
    p1 = m1.predict_origin(te.iloc[5], te.iloc[5]["timestamp"])

    m2 = MultiStepHistGradientBoostingForecaster(random_state=42, max_iter=20)
    m2.fit(tr, val, "total_load_kw", feat_cols)
    p2 = m2.predict_origin(te.iloc[5], te.iloc[5]["timestamp"])

    np.testing.assert_allclose(p1["forecast"].values, p2["forecast"].values, rtol=1e-7)
