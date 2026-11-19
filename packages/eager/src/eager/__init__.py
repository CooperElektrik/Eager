"""Eager — unified visual novel and interactive narrative engine."""

from __future__ import annotations

import logging

__version__ = "0.9.0"

logging.getLogger("eager").addHandler(logging.NullHandler())

__all__ = ["__version__"]
