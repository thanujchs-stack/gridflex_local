"""GridFlex Local — Data Acquisition, Validation, and Preparation Module (Phase 2.5).

This module manages the acquisition, validation, cleaning, resampling, and
standardized loading of real/public datasets for GridFlex Local:
- SUNY India (NREL NSRDB): Indian solar resource grounding.
- Ausgrid Solar Home Electricity Dataset: Residential load and PV behavioural reference data.
"""

from src.data.dataset_manager import DatasetManager
from src.data.downloader import DataDownloader
from src.data.validator import DataValidator
from src.data.cleaner import DataCleaner
from src.data.resampler import DataResampler
from src.data.metadata import MetadataManager
from src.data.load_dataset import load_forecasting_dataset

__all__ = [
    "DatasetManager",
    "DataDownloader",
    "DataValidator",
    "DataCleaner",
    "DataResampler",
    "MetadataManager",
    "load_forecasting_dataset",
]
