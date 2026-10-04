"""Configuration loader utility for GridFlex Local."""

import os
from pathlib import Path
from typing import Any, Dict, Optional
import yaml


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load neighbourhood configuration YAML.

    Args:
        config_path: Optional path to YAML config file. If None, defaults to config/neighbourhood_config.yaml.

    Returns:
        Dictionary representation of config.
    """
    if config_path is None:
        # Default relative to repository root
        base_dir = Path(__file__).resolve().parent.parent.parent
        config_path = str(base_dir / "config" / "neighbourhood_config.yaml")

    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
