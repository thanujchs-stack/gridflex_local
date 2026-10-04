"""Dataset metadata and manifest management for GridFlex Local.

Maintains data lineage, checksums, licensing, access logging, and explicit limitations
for all external and processed datasets in YAML format:
- data/metadata/dataset_manifest.yaml
- data/metadata/dataset_access_log.yaml
- data/metadata/dataset_summary.csv
"""

import os
import yaml
import pandas as pd
from datetime import datetime
from typing import Dict, Any, Optional, List


class MetadataManager:
    """Creates and updates the dataset manifest, access log, and summary table."""

    def __init__(self, metadata_path: str = "data/metadata/dataset_manifest.yaml"):
        self.metadata_path = metadata_path
        self.metadata_dir = os.path.dirname(self.metadata_path)
        os.makedirs(self.metadata_dir, exist_ok=True)
        self.access_log_path = os.path.join(self.metadata_dir, "dataset_access_log.yaml")
        self.summary_csv_path = os.path.join(self.metadata_dir, "dataset_summary.csv")

    def load_manifest(self) -> Dict[str, Any]:
        """Load the existing dataset manifest if present, else return empty structure."""
        if os.path.exists(self.metadata_path):
            with open(self.metadata_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {"datasets": {}}
        return {"datasets": {}}

    def save_manifest(self, manifest: Dict[str, Any]) -> None:
        """Save dictionary manifest to YAML file."""
        with open(self.metadata_path, "w", encoding="utf-8") as f:
            yaml.dump(manifest, f, default_flow_style=False, sort_keys=False)

    def save_access_log(self, access_records: List[Dict[str, Any]]) -> None:
        """Save dataset access log to YAML file."""
        log_payload = {
            "version": "1.0",
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "access_log": access_records,
        }
        with open(self.access_log_path, "w", encoding="utf-8") as f:
            yaml.dump(log_payload, f, default_flow_style=False, sort_keys=False)

    def save_summary_table(self, summary_rows: List[Dict[str, Any]], extra_dir: Optional[str] = None) -> None:
        """Save dataset summary table to CSV."""
        df = pd.DataFrame(summary_rows)
        df.to_csv(self.summary_csv_path, index=False)
        if extra_dir:
            os.makedirs(extra_dir, exist_ok=True)
            df.to_csv(os.path.join(extra_dir, "dataset_summary.csv"), index=False)

    def generate_default_manifest(
        self,
        suny_info: Optional[Dict[str, Any]] = None,
        ausgrid_info: Optional[Dict[str, Any]] = None,
        iiit_info: Optional[Dict[str, Any]] = None,
        grid_india_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate the complete, compliant dataset manifest for Phase 2.5."""
        suny_info = suny_info or {}
        ausgrid_info = ausgrid_info or {}
        iiit_info = iiit_info or {}
        grid_india_info = grid_india_info or {}

        today = datetime.now().strftime("%Y-%m-%d")

        manifest = {
            "version": "1.0",
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "conceptual_relationship": (
                "India solar resource (SUNY India) + real residential/PV behaviour (Ausgrid reference) "
                "+ authentic Indian household smart meter data (IIIT-Delhi) "
                "+ bulk grid context (Grid-India / NERLDC) "
                "+ engineering assumptions -> GridFlex simulated neighbourhood. "
                "The eventual GridFlex neighbourhood remains a simulated neighbourhood. "
                "We do NOT claim that our 100 neighbourhood households are real co-located Indian households."
            ),
            "datasets": {
                "suny_india": {
                    "name": "SUNY India Solar Resource Dataset (NSRDB)",
                    "category": "Indian Solar Resource",
                    "origin": "India (National Renewable Energy Grounding)",
                    "source": "National Renewable Energy Laboratory (NREL) / National Laboratory of the Rockies (NLR)",
                    "source_url": "https://developer.nlr.gov/docs/solar/nsrdb/suny-india-data-download/",
                    "purpose": "India-specific solar resource grounding (GHI, DNI, DHI, ambient temperature) for solar irradiance profile modeling.",
                    "geographic_scope": "New Delhi, India (Latitude: 28.65, Longitude: 77.25, Elevation: 0 m)",
                    "temporal_resolution": "60-minute (hourly), resampled to 15-minute",
                    "data_period": "2011-07-01 to 2012-06-30 (overlapping with Ausgrid) and 2014 full year",
                    "timezone": "UTC+05:30 (Indian Standard Time)",
                    "license": "Creative Commons Attribution 4.0 International (CC BY 4.0) / U.S. Government Open Data",
                    "download_date": suny_info.get("download_date", today),
                    "original_filename": "suny-india-download.csv",
                    "local_path": suny_info.get("local_path", "data/external/suny_india/suny_india_new_delhi_2014.csv"),
                    "file_size_bytes": suny_info.get("file_size", 0),
                    "sha256": suny_info.get("sha256", "UNKNOWN"),
                    "processing_steps": [
                        "Raw download from NREL/NLR NSRDB API v2",
                        "Skip 2-row metadata header to parse column timeseries",
                        "Parse Year/Month/Day/Hour/Minute into standard ISO timestamps",
                        "Physical range validation (GHI >= 0, Temp within physical limits)",
                        "15-minute cubic/linear interpolation during daylight, zero during nighttime",
                    ],
                    "known_limitations": (
                        "Satellite-derived Perez model data representing a specific location in New Delhi. "
                        "Does not reflect all Indian microclimates or local rooftop shading/soiling factors."
                    ),
                },
                "iiit_delhi_iawe": {
                    "name": "IIIT-Delhi Indian Dataset for Ambient Water and Energy (iAWE)",
                    "category": "Indian Household Load",
                    "origin": "India (Authentic Household Ground Truth)",
                    "source": "IIIT-Delhi (Energy Group: Nipun Batra, Manoj Gulati, Amarjeet Singh, Pushpendra Singh)",
                    "source_url": "https://github.com/nipunbatra/Home_Deployment",
                    "archive_doi": "10.5281/zenodo.13917372",
                    "purpose": "Ground truth Indian residential electricity consumption, voltage, and power factor measurements.",
                    "geographic_scope": "New Delhi, National Capital Territory of Delhi, India",
                    "temporal_resolution": "1-second raw smart meter readings, resampled to 15-minute average power",
                    "data_period": "2013-08-04 to 2013-08-05 (continuous smart meter run)",
                    "timezone": "UTC+05:30 (Indian Standard Time)",
                    "license": "Creative Commons Attribution 4.0 International (CC BY 4.0)",
                    "download_date": iiit_info.get("download_date", today),
                    "original_filename": "smart_meter.csv",
                    "local_path": iiit_info.get("local_path", "data/external/iiit_delhi/smart_meter.csv"),
                    "file_size_bytes": iiit_info.get("file_size", 0),
                    "sha256": iiit_info.get("sha256", "UNKNOWN"),
                    "processing_steps": [
                        "Raw retrieval from IIIT-Delhi Home Deployment repository",
                        "Convert Unix epoch timestamps to Indian Standard Time (IST)",
                        "Unit conversion: Active power (W) / 1000.0 = load (kW)",
                        "15-minute mean active power resampling",
                        "Physical non-negative load clamping",
                    ],
                    "known_limitations": (
                        "Collected from a single authentic Indian household in Delhi over a 73-day measurement campaign. "
                        "Provides real Indian household load characteristics, but insufficient household count for 100-home feeder diversity."
                    ),
                },
                "ausgrid": {
                    "name": "Ausgrid Solar Home Electricity Dataset (300 Homes)",
                    "category": "Non-Indian Benchmark (Residential Behaviour Reference)",
                    "origin": "Australia (Non-Indian)",
                    "source": "Ausgrid (Electricity distribution network service provider, NSW, Australia)",
                    "source_url": "https://data.gov.au/data/en/dataset/nsw-solar-home-electricty-data",
                    "archive_url": "https://pierreh.eu/downloads/Ausgrid_solar_home_data.zip",
                    "purpose": (
                        "Real residential electricity consumption (GC) and rooftop PV generation (GG) "
                        "behavioural reference data to simulate realistic consumer diversity across 100 households."
                    ),
                    "geographic_scope": "Sydney, Central Coast, and Hunter regions, New South Wales, Australia (NOT India)",
                    "temporal_resolution": "30-minute interval readings, resampled to 15-minute",
                    "data_period": "2011-07-01 to 2012-06-30 (1 full operational year / 366 days)",
                    "timezone": "UTC+10:00 (AEST - Australian Eastern Standard Time)",
                    "license": "Creative Commons Attribution 3.0 Australia (CC BY 3.0 AU)",
                    "download_date": ausgrid_info.get("download_date", today),
                    "original_filename": "Solar home 2011-2012.csv",
                    "local_path": ausgrid_info.get("local_path", "data/external/ausgrid/Solar home 2011-2012.csv"),
                    "file_size_bytes": ausgrid_info.get("file_size", 0),
                    "sha256": ausgrid_info.get("sha256", "UNKNOWN"),
                    "processing_steps": [
                        "Extracted from official CC BY 3.0 AU distribution archive",
                        "Skip notice header row",
                        "Reshape wide 48 half-hour columns (0:30 to 0:00) into long timeseries",
                        "Unit conversion: kWh / 0.5 h = average kW for each 30-min interval",
                        "Deterministic selection of 100 households (seed 42)",
                        "15-minute energy-conserving resampling (forward-fill average power)",
                        "Separate GC (load) and GG (PV) channels",
                    ],
                    "known_limitations": (
                        "CRITICAL: This is an Australian residential dataset, NOT Indian household data. "
                        "Southern hemisphere seasonal patterns (summer in Dec-Feb, winter in Jun-Aug). "
                        "Used solely as behavioral reference data to simulate realistic household load/PV diversity."
                    ),
                },
                "grid_india_nerldc": {
                    "name": "Grid-India / NERLDC Demand, Solar and Wind Generation Dataset",
                    "category": "Indian Bulk Grid Reference",
                    "origin": "India (Bulk Transmission Grid)",
                    "source": "North-Eastern Regional Load Despatch Centre (NERLDC), Grid-India, Ministry of Power, Government of India",
                    "source_url": "https://data.mendeley.com/datasets/y58jknpgs8/2",
                    "doi": "10.17632/y58jknpgs8.2",
                    "purpose": "Indian regional grid demand, bulk solar, and wind generation reference profile data.",
                    "geographic_scope": "National grid of India (5 Regional Grids: Northern, Western, Southern, Eastern, North-Eastern)",
                    "temporal_resolution": "1-hour interval",
                    "data_period": "September 2021 to June 2025 (covering historical operational data through Dec 2023)",
                    "timezone": "UTC+05:30 (Indian Standard Time)",
                    "license": "Creative Commons Attribution 4.0 International (CC BY 4.0)",
                    "access_status": grid_india_info.get("access_status", "ACCESS_LIMITATION_DOCUMENTED"),
                    "known_limitations": (
                        "Automated machine download is restricted by Elsevier/Mendeley Data OAuth 2.0 (HTTP 401). "
                        "Transmission bulk grid scale (MW/MWh), representing aggregate regional demand rather than LV distribution feeder households."
                    ),
                },
            },
        }

        self.save_manifest(manifest)
        return manifest
