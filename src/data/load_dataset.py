"""Standardized forecasting dataset interface for GridFlex Local.

Provides an abstracted data loader for future Phase 3 forecasting pipelines:
- DATASET_MODE: "REAL_PUBLIC" (prepared Ausgrid + SUNY India 15-minute data)
- DATASET_MODE: "SYNTHETIC_PHASE1" (Phase 1 synthetic baseline profiles)

Exposes a uniform contract:
- Timestamps
- Neighbourhood load (kW)
- Neighbourhood PV (kW)
- Solar resource data (W/m², °C)
- Metadata & limitations
"""

import os
import logging
from typing import Dict, Any, Optional
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def load_forecasting_dataset(
    mode: str = "REAL_PUBLIC",
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    include_household_level: bool = False,
    data_dir: str = "data/processed",
) -> Dict[str, Any]:
    """Load forecasting-ready dataset in an abstracted, source-agnostic format.

    Args:
        mode: "REAL_PUBLIC" or "SYNTHETIC_PHASE1"
        start_time: Optional ISO timestamp string filter (inclusive)
        end_time: Optional ISO timestamp string filter (inclusive)
        include_household_level: If True, includes individual household load and PV series.
        data_dir: Directory containing processed data files.

    Returns:
        Dictionary containing standardized timeseries, arrays, and metadata.
    """
    mode_upper = mode.upper()
    if mode_upper not in ["REAL_PUBLIC", "SYNTHETIC_PHASE1"]:
        raise ValueError(f"Unsupported dataset mode '{mode}'. Choose 'REAL_PUBLIC' or 'SYNTHETIC_PHASE1'.")

    if mode_upper == "REAL_PUBLIC":
        return _load_real_public_dataset(start_time, end_time, include_household_level, data_dir)
    else:
        return _load_synthetic_phase1_dataset(start_time, end_time)


def _load_real_public_dataset(
    start_time: Optional[str],
    end_time: Optional[str],
    include_household_level: bool,
    data_dir: str,
) -> Dict[str, Any]:
    """Load from processed real/public data directory."""
    nb_load_path = os.path.join(data_dir, "neighbourhood_load_15min.csv")
    nb_pv_path = os.path.join(data_dir, "neighbourhood_pv_15min.csv")
    solar_path = os.path.join(data_dir, "suny_india_solar_15min.csv")

    for p in [nb_load_path, nb_pv_path, solar_path]:
        if not os.path.exists(p):
            raise FileNotFoundError(f"Processed dataset file not found: {p}. Run scripts/prepare_phase3_data.py first.")

    df_load = pd.read_csv(nb_load_path)
    df_load["timestamp"] = pd.to_datetime(df_load["timestamp"])

    df_pv = pd.read_csv(nb_pv_path)
    df_pv["timestamp"] = pd.to_datetime(df_pv["timestamp"])

    df_solar = pd.read_csv(solar_path)
    df_solar["timestamp"] = pd.to_datetime(df_solar["timestamp"])

    # Merge on timestamp
    merged = pd.merge(df_load[["timestamp", "total_load_kw"]], df_pv[["timestamp", "total_pv_kw"]], on="timestamp", how="inner")
    merged = pd.merge(merged, df_solar, on="timestamp", how="left")

    if start_time:
        merged = merged[merged["timestamp"] >= pd.to_datetime(start_time)]
    if end_time:
        merged = merged[merged["timestamp"] <= pd.to_datetime(end_time)]

    merged = merged.sort_values("timestamp").reset_index(drop=True)

    result: Dict[str, Any] = {
        "mode": "REAL_PUBLIC",
        "resolution_minutes": 15,
        "timestamps": merged["timestamp"],
        "neighbourhood_load_kw": merged["total_load_kw"],
        "neighbourhood_pv_kw": merged["total_pv_kw"],
        "solar_irradiance": merged[["ghi_wm2", "dni_wm2", "dhi_wm2", "temp_c"]],
        "metadata": {
            "load_source": "Ausgrid Solar Home Electricity Dataset (Residential Behaviour Reference)",
            "solar_source": "SUNY India (NREL NSRDB Satellite-derived Perez Model)",
            "geographic_scope": "Simulated Neighbourhood (grounded in New Delhi solar resource + Ausgrid diversity)",
            "units": {
                "load_kw": "Average active power (kW) over 15-minute interval",
                "pv_kw": "Average active generation (kW) over 15-minute interval",
                "ghi_wm2": "Global Horizontal Irradiance (W/m²)",
                "dni_wm2": "Direct Normal Irradiance (W/m²)",
                "dhi_wm2": "Diffuse Horizontal Irradiance (W/m²)",
                "temp_c": "Ambient Temperature (°C)",
            },
            "limitations": (
                "Real residential load behaviour is sourced from Australia and is NOT Indian household data. "
                "The neighbourhood is a simulation grounding Indian solar conditions with real household diversity."
            ),
        },
    }

    if include_household_level:
        hh_load_path = os.path.join(data_dir, "ausgrid_load_15min.csv")
        hh_pv_path = os.path.join(data_dir, "ausgrid_pv_15min.csv")
        if os.path.exists(hh_load_path) and os.path.exists(hh_pv_path):
            df_hh_l = pd.read_csv(hh_load_path)
            df_hh_l["timestamp"] = pd.to_datetime(df_hh_l["timestamp"])
            df_hh_p = pd.read_csv(hh_pv_path)
            df_hh_p["timestamp"] = pd.to_datetime(df_hh_p["timestamp"])

            if start_time:
                df_hh_l = df_hh_l[df_hh_l["timestamp"] >= pd.to_datetime(start_time)]
                df_hh_p = df_hh_p[df_hh_p["timestamp"] >= pd.to_datetime(start_time)]
            if end_time:
                df_hh_l = df_hh_l[df_hh_l["timestamp"] <= pd.to_datetime(end_time)]
                df_hh_p = df_hh_p[df_hh_p["timestamp"] <= pd.to_datetime(end_time)]

            result["household_load_df"] = df_hh_l.reset_index(drop=True)
            result["household_pv_df"] = df_hh_p.reset_index(drop=True)

    return result


def _load_synthetic_phase1_dataset(
    start_time: Optional[str],
    end_time: Optional[str],
) -> Dict[str, Any]:
    """Load from Phase 1 synthetic baseline profiles."""
    p1_csv = "outputs/csv/phase1_timeseries.csv"
    if os.path.exists(p1_csv):
        df_p1 = pd.read_csv(p1_csv)
        df_p1["timestamp"] = pd.to_datetime(df_p1["timestamp"])
        df = pd.DataFrame({
            "timestamp": df_p1["timestamp"],
            "total_load_kw": df_p1["total_load_kw"],
            "total_pv_kw": df_p1["pv_generation_kw"],
        })
    else:
        from src.utils.config import load_config
        from src.profiles.load_profiles import generate_time_index, generate_residential_profiles
        from src.profiles.solar_profiles import generate_solar_profiles
        cfg = load_config()
        t_idx = generate_time_index()
        res_df, _ = generate_residential_profiles(cfg, t_idx)
        hh_ids = list(res_df.columns)
        pv_df, _ = generate_solar_profiles(cfg, t_idx, hh_ids)
        df = pd.DataFrame({
            "timestamp": pd.to_datetime(t_idx),
            "total_load_kw": res_df.sum(axis=1).values,
            "total_pv_kw": pv_df.sum(axis=1).values,
        })

    if start_time:
        df = df[df["timestamp"] >= pd.to_datetime(start_time)]
    if end_time:
        df = df[df["timestamp"] <= pd.to_datetime(end_time)]
    df = df.reset_index(drop=True)

    # Mock synthetic solar irradiance proxy (GHI roughly ~ 1000 * (PV / peak_PV))
    peak_pv = max(df["total_pv_kw"].max(), 1.0)
    synthetic_ghi = (df["total_pv_kw"].values / peak_pv) * 950.0

    solar_df = pd.DataFrame({
        "ghi_wm2": synthetic_ghi,
        "dni_wm2": synthetic_ghi * 0.8,
        "dhi_wm2": synthetic_ghi * 0.2,
        "temp_c": np.full(len(df), 32.0),
    }, index=df.index)

    return {
        "mode": "SYNTHETIC_PHASE1",
        "resolution_minutes": 15,
        "timestamps": df["timestamp"],
        "neighbourhood_load_kw": df["total_load_kw"],
        "neighbourhood_pv_kw": df["total_pv_kw"],
        "solar_irradiance": solar_df,
        "metadata": {
            "load_source": "Phase 1 Synthetic Residential Profiles (100 Households)",
            "solar_source": "Phase 1 Synthetic Half-sine PV Profiles (60 Systems)",
            "geographic_scope": "GridFlex Local Digital Feeder (Synthesized)",
            "units": {
                "load_kw": "Average active power (kW) over 15-minute interval",
                "pv_kw": "Average active generation (kW) over 15-minute interval",
                "ghi_wm2": "Synthesized Global Horizontal Irradiance proxy (W/m²)",
            },
            "limitations": "Synthetic statistical model generated for LV network testing.",
        },
    }
