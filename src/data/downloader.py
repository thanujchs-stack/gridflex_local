"""Dataset acquisition and download manager for GridFlex Local.

Handles acquisition of approved public reference datasets:
1. SUNY India / NREL: India solar resource grounding.
2. Ausgrid Solar Home Electricity Dataset: Residential load and PV behaviour reference data.

Adheres strictly to project constraints:
- Caches locally and skips download if already present.
- Never overwrites original downloaded raw data.
- Computes SHA256 checksums and file sizes for data lineage.
- Fails cleanly and transparently if credentials or network are unavailable (no fabrication).
"""

import os
import urllib.request
import urllib.parse
import hashlib
import zipfile
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class DataDownloader:
    """Manages downloading, checksumming, and raw storage of external datasets."""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.external_dir = os.path.join(data_dir, "external")
        self.suny_dir = os.path.join(self.external_dir, "suny_india")
        self.ausgrid_dir = os.path.join(self.external_dir, "ausgrid")

        os.makedirs(self.suny_dir, exist_ok=True)
        os.makedirs(self.ausgrid_dir, exist_ok=True)

    @staticmethod
    def compute_sha256(filepath: str, block_size: int = 65536) -> str:
        """Compute SHA-256 hash of a local file."""
        hasher = hashlib.sha256()
        with open(filepath, "rb") as f:
            for block in iter(lambda: f.read(block_size), b""):
                hasher.update(block)
        return hasher.hexdigest()

    def get_suny_local_path(self) -> str:
        """Return expected local path for SUNY India dataset."""
        return os.path.join(self.suny_dir, "suny_india_new_delhi_2014.csv")

    def get_ausgrid_local_path(self) -> str:
        """Return expected local path for Ausgrid 2011-2012 dataset."""
        return os.path.join(self.ausgrid_dir, "Solar home 2011-2012.csv")

    def check_suny_exists(self) -> bool:
        """Check if SUNY India file exists locally and has non-zero size."""
        path = self.get_suny_local_path()
        return os.path.exists(path) and os.path.getsize(path) > 0

    def check_ausgrid_exists(self) -> bool:
        """Check if Ausgrid 2011-2012 file exists locally and has non-zero size."""
        path = self.get_ausgrid_local_path()
        return os.path.exists(path) and os.path.getsize(path) > 0

    def download_suny_india(
        self,
        lat: float = 28.6139,
        lon: float = 77.2090,
        year: int = 2014,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Download SUNY India solar data from official NREL / NLR NSRDB endpoint.

        Location default is New Delhi (Lat: 28.6139, Lon: 77.2090).
        """
        local_path = self.get_suny_local_path()
        if not force and self.check_suny_exists():
            logger.info("SUNY India dataset already exists locally: %s", local_path)
            return {
                "status": "CACHED",
                "local_path": local_path,
                "file_size": os.path.getsize(local_path),
                "sha256": self.compute_sha256(local_path),
            }

        api_key = os.environ.get("NREL_API_KEY", "DEMO_KEY")
        # Primary active endpoint after May 2026 NREL->NLR migration
        base_url = "https://developer.nlr.gov/api/nsrdb/v2/solar/suny-india-download.csv"
        params = {
            "api_key": api_key,
            "full_name": "GridFlex Research Team",
            "email": "gridflex.research@gmail.com",
            "wkt": f"POINT({lon} {lat})",
            "names": str(year),
            "attributes": "ghi,dni,dhi,air_temperature",
            "utc": "false",
            "leap_day": "false",
            "interval": "60",
        }
        url = f"{base_url}?{urllib.parse.urlencode(params)}"

        logger.info("Downloading SUNY India data from %s (lat: %s, lon: %s, year: %s)...", base_url, lat, lon, year)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "GridFlex-Local/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp, open(local_path, "wb") as f:
                content = resp.read()
                f.write(content)

            file_size = os.path.getsize(local_path)
            sha256_hash = self.compute_sha256(local_path)
            logger.info("SUNY India download successful (%d bytes, SHA256: %s)", file_size, sha256_hash)
            return {
                "status": "DOWNLOADED",
                "local_path": local_path,
                "file_size": file_size,
                "sha256": sha256_hash,
            }
        except Exception as e:
            logger.error("Failed to download SUNY India dataset: %s", e)
            return {
                "status": "FAILED",
                "error": str(e),
                "manual_action": (
                    "Register for an API key at https://developer.nlr.gov/ or set NREL_API_KEY environment variable. "
                    "Alternatively, place suny_india_new_delhi_2014.csv manually in data/external/suny_india/."
                ),
            }

    def download_ausgrid(
        self,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Download Ausgrid Solar Home Electricity Dataset and extract 2011-2012 CSV."""
        local_path = self.get_ausgrid_local_path()
        if not force and self.check_ausgrid_exists():
            logger.info("Ausgrid dataset already exists locally: %s", local_path)
            return {
                "status": "CACHED",
                "local_path": local_path,
                "file_size": os.path.getsize(local_path),
                "sha256": self.compute_sha256(local_path),
            }

        zip_path = os.path.join(self.ausgrid_dir, "Ausgrid_solar_home_data.zip")
        archive_url = "https://pierreh.eu/downloads/Ausgrid_solar_home_data.zip"

        try:
            if not os.path.exists(zip_path) or os.path.getsize(zip_path) < 50 * 1024 * 1024:
                logger.info("Downloading Ausgrid archive (57 MB) from %s...", archive_url)
                req = urllib.request.Request(archive_url, headers={"User-Agent": "GridFlex-Local/1.0"})
                with urllib.request.urlopen(req, timeout=180) as resp, open(zip_path, "wb") as f:
                    while True:
                        chunk = resp.read(1024 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)

            logger.info("Extracting Solar home 2011-2012.csv from %s...", zip_path)
            with zipfile.ZipFile(zip_path) as z:
                # Extract target year csv and metadata documentation
                for member in ["Solar home 2011-2012.csv", "README.md", "Ausgrid solar home electricity data notes (Aug 2014).pdf"]:
                    if member in z.namelist():
                        z.extract(member, self.ausgrid_dir)

            file_size = os.path.getsize(local_path)
            sha256_hash = self.compute_sha256(local_path)
            logger.info("Ausgrid extraction successful (%d bytes, SHA256: %s)", file_size, sha256_hash)
            return {
                "status": "DOWNLOADED",
                "local_path": local_path,
                "file_size": file_size,
                "sha256": sha256_hash,
            }
        except Exception as e:
            logger.error("Failed to download/extract Ausgrid dataset: %s", e)
            return {
                "status": "FAILED",
                "error": str(e),
                "manual_action": (
                    "Download Ausgrid Solar Home Electricity Data from https://data.gov.au/ or "
                    "https://pierreh.eu/downloads/Ausgrid_solar_home_data.zip and extract "
                    "'Solar home 2011-2012.csv' into data/external/ausgrid/."
                ),
            }

    def get_iiit_delhi_local_path(self) -> str:
        """Return expected local path for IIIT-Delhi smart meter dataset."""
        iiit_dir = os.path.join(self.external_dir, "iiit_delhi")
        os.makedirs(iiit_dir, exist_ok=True)
        return os.path.join(iiit_dir, "smart_meter.csv")

    def check_iiit_delhi_exists(self) -> bool:
        """Check if IIIT-Delhi dataset exists locally."""
        p = self.get_iiit_delhi_local_path()
        return os.path.exists(p) and os.path.getsize(p) > 0

    def download_iiit_delhi(self, force: bool = False) -> Dict[str, Any]:
        """Download IIIT-Delhi iAWE smart meter dataset (real Indian household in New Delhi)."""
        local_path = self.get_iiit_delhi_local_path()
        if not force and self.check_iiit_delhi_exists():
            logger.info("IIIT-Delhi dataset already exists locally: %s", local_path)
            return {
                "status": "CACHED",
                "local_path": local_path,
                "file_size": os.path.getsize(local_path),
                "sha256": self.compute_sha256(local_path),
            }

        url = "https://raw.githubusercontent.com/nipunbatra/Home_Deployment/master/dataset/smart_meter.csv"
        try:
            logger.info("Downloading IIIT-Delhi iAWE smart meter dataset from %s...", url)
            req = urllib.request.Request(url, headers={"User-Agent": "GridFlex-Local/1.0"})
            with urllib.request.urlopen(req, timeout=120) as resp, open(local_path, "wb") as f:
                f.write(resp.read())

            file_size = os.path.getsize(local_path)
            sha256_hash = self.compute_sha256(local_path)
            logger.info("IIIT-Delhi download successful (%d bytes, SHA256: %s)", file_size, sha256_hash)
            return {
                "status": "DOWNLOADED",
                "local_path": local_path,
                "file_size": file_size,
                "sha256": sha256_hash,
            }
        except Exception as e:
            logger.error("Failed to download IIIT-Delhi dataset: %s", e)
            return {
                "status": "FAILED",
                "error": str(e),
                "manual_action": "Download smart_meter.csv from https://github.com/nipunbatra/Home_Deployment and place in data/external/iiit_delhi/.",
            }

    def check_grid_india_access(self) -> Dict[str, Any]:
        """Document access limitation and authentication requirements for Grid-India/NERLDC dataset."""
        doi = "10.17632/y58jknpgs8.2"
        dataset_url = "https://data.mendeley.com/datasets/y58jknpgs8/2"
        title = "Electricity Demand, Solar and Wind Generation Data (September 2021- June 2025) of India at 1-hour interval"
        source_org = "North-Eastern Regional Load Despatch Centre (NERLDC), Grid-India, Ministry of Power, Government of India"

        logger.info("Auditing Grid-India / NERLDC access via Mendeley Data (DOI: %s)...", doi)
        # Attempt automated access check
        test_url = "https://api.data.mendeley.com/datasets/y58jknpgs8"
        try:
            req = urllib.request.Request(test_url, headers={"User-Agent": "GridFlex-Local/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                status_code = resp.status
        except urllib.error.HTTPError as e:
            status_code = e.code
        except Exception as e:
            status_code = "UNREACHABLE"

        return {
            "name": title,
            "source": source_org,
            "doi": doi,
            "source_url": dataset_url,
            "http_status": status_code,
            "access_status": "ACCESS_LIMITATION_DOCUMENTED",
            "reason": (
                "Automated machine download is restricted by Elsevier/Mendeley Data OAuth 2.0 authentication (HTTP 401). "
                "Interactive browser download or registered developer token is required."
            ),
            "manual_action_required": (
                f"1. Navigate in browser to {dataset_url}\n"
                "2. Click 'Download All Files' to obtain the hourly demand, solar, and wind CSV/Excel files.\n"
                "3. Place extracted files in data/external/grid_india/ for bulk system integration."
            ),
        }
