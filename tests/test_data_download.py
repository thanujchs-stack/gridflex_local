"""Unit tests for dataset acquisition, detection, and manifest metadata."""

import os
import pytest
import yaml
from src.data.downloader import DataDownloader
from src.data.metadata import MetadataManager


def test_dataset_detection():
    """Verify external dataset files are properly detected and exist locally."""
    downloader = DataDownloader()
    assert downloader.check_suny_exists(), "SUNY India dataset should exist locally in data/external/suny_india/"
    assert downloader.check_ausgrid_exists(), "Ausgrid dataset should exist locally in data/external/ausgrid/"


def test_sha256_checksum_reproducibility():
    """Verify SHA-256 calculation is reproducible on downloaded files."""
    downloader = DataDownloader()
    suny_path = downloader.get_suny_local_path()
    h1 = downloader.compute_sha256(suny_path)
    h2 = downloader.compute_sha256(suny_path)
    assert h1 == h2
    assert len(h1) == 64


def test_metadata_manifest_structure():
    """Verify dataset manifest conforms to all data lineage requirements."""
    manifest_path = "data/metadata/dataset_manifest.yaml"
    assert os.path.exists(manifest_path), "dataset_manifest.yaml must exist"

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = yaml.safe_load(f)

    assert "datasets" in manifest
    assert "suny_india" in manifest["datasets"]
    assert "ausgrid" in manifest["datasets"]

    suny = manifest["datasets"]["suny_india"]
    assert "name" in suny
    assert "source" in suny
    assert "source_url" in suny
    assert "geographic_scope" in suny
    assert "license" in suny
    assert "sha256" in suny
    assert "known_limitations" in suny

    ausgrid = manifest["datasets"]["ausgrid"]
    assert "name" in ausgrid
    assert "source" in ausgrid
    assert "license" in ausgrid
    assert "sha256" in ausgrid
    assert "known_limitations" in ausgrid
    assert "Australian residential" in ausgrid["known_limitations"]
