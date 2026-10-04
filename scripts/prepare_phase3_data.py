#!/usr/bin/env python
"""GridFlex Local — Phase 2.5 Dataset Acquisition, Validation, and Preparation Pipeline.

Executes the end-to-end dataset pipeline:
- Validates / downloads approved sources: SUNY India (NREL NSRDB) & Ausgrid Solar Home Electricity Dataset
- Deterministic 100-household selection (random_seed: 42)
- Unit conversion (kWh -> average kW)
- Canonical 15-minute resampling (energy-conserving for power, continuous for solar irradiance)
- Physical validation & quality gating (PASS / WARNING / FAIL)
- Lineage manifest generation (data/metadata/dataset_manifest.yaml)
- Machine-readable quality reports (outputs/data_quality/)
- Data validation figures (outputs/data_quality/figures/)

Usage:
    python scripts/prepare_phase3_data.py
"""

import sys
import os
import logging
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.dataset_manager import DatasetManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("prepare_phase3_data")


def main():
    logger.info("Initializing DatasetManager (seed=42)...")
    manager = DatasetManager(
        data_dir=str(PROJECT_ROOT / "data"),
        output_dir=str(PROJECT_ROOT / "outputs" / "data_quality"),
        random_seed=42,
    )

    try:
        results = manager.run_pipeline()
        logger.info("Pipeline executed successfully.")
        logger.info("Selected Households: %d", results["households_selected"])
        logger.info("Processed Load Records: %d", results["load_rows"])
        logger.info("Processed PV Records: %d", results["pv_rows"])
        logger.info("Processed Solar Records: %d", results["solar_rows"])
        print("\n============================================================")
        print("GRIDFLEX LOCAL — PHASE 2.5 DATASET PREPARATION COMPLETE")
        print("Processed files generated in: data/processed/")
        print("Data quality reports in: outputs/data_quality/")
        print("Validation figures in: outputs/data_quality/figures/")
        print("Dataset manifest in: data/metadata/dataset_manifest.yaml")
        print("============================================================\n")
        return 0
    except Exception as e:
        logger.exception("Pipeline failed with error: %s", e)
        print(f"\n[FATAL ERROR] Dataset preparation pipeline failed: {e}\n", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
