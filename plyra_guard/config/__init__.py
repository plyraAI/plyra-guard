"""ActionGuard configuration — loading, validation, and defaults."""

from plyra_guard.config.defaults import DEFAULT_CONFIG
from plyra_guard.config.loader import load_config, load_config_from_dict
from plyra_guard.config.schema import GuardConfig

__all__ = [
    "load_config",
    "load_config_from_dict",
    "GuardConfig",
    "DEFAULT_CONFIG",
]
