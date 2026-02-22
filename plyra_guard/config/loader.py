"""
Configuration Loader
~~~~~~~~~~~~~~~~~~~~

Loads and validates guard_config.yaml, merging with defaults.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import yaml

from plyra_guard.config.defaults import DEFAULT_CONFIG
from plyra_guard.config.schema import GuardConfig
from plyra_guard.exceptions import (
    ConfigFileNotFoundError,
    ConfigValidationError,
)

__all__ = ["load_config", "load_config_from_dict"]

logger = logging.getLogger(__name__)


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dicts, with override taking precedence."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: str) -> GuardConfig:
    """
    Load configuration from a YAML file.

    Merges user config with defaults and validates via Pydantic.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        Validated GuardConfig instance.

    Raises:
        ConfigFileNotFoundError: If the file doesn't exist.
        ConfigValidationError: If the config fails validation.
    """
    if not os.path.exists(path):
        raise ConfigFileNotFoundError(f"Configuration file not found: {path}")

    try:
        with open(path, encoding="utf-8") as f:
            user_config = yaml.safe_load(f) or {}
    except yaml.YAMLError as exc:
        raise ConfigValidationError(
            f"Invalid YAML in configuration file: {exc}"
        ) from exc

    return load_config_from_dict(user_config)


def load_config_from_dict(data: dict[str, Any]) -> GuardConfig:
    """
    Load configuration from a dictionary, merging with defaults.

    Args:
        data: Configuration dictionary.

    Returns:
        Validated GuardConfig instance.

    Raises:
        ConfigValidationError: If validation fails.
    """
    merged = _deep_merge(DEFAULT_CONFIG, data)

    try:
        return GuardConfig(**merged)
    except Exception as exc:
        raise ConfigValidationError(f"Configuration validation failed: {exc}") from exc
