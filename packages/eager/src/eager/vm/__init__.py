"""Headless story virtual machine and localization tooling for Eager."""

from eager.vm.i18n import (
    compute_beat_id,
    extract_catalog,
    get_beat_occurrence,
    merge_catalog,
    strip_explicit_id,
    validate_catalog,
)
from eager.vm.runtime import EagerRuntimeError, StoryRuntimeError, StoryVM

__all__ = [
    "EagerRuntimeError",
    "StoryRuntimeError",
    "StoryVM",
    "compute_beat_id",
    "extract_catalog",
    "get_beat_occurrence",
    "merge_catalog",
    "strip_explicit_id",
    "validate_catalog",
]
