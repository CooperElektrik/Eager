"""Tests for eager CLI screenplay check and parser."""

import tempfile
from pathlib import Path

from eager.cli import build_parser, main

SAMPLE_SCRIPT = """
## The Clearing --- courtyard

# Ambient comment
Alice: Welcome to the ancient ruins!
? Examine the glowing runes (runes)
? Turn back towards town (exit)

## Ancient Runes --- runes
The runes shimmer with blue light.
> courtyard

## Town Exit --- exit
You head back to town.
"""


def test_cli_version() -> None:
    parser = build_parser()
    assert parser is not None


def test_cli_check() -> None:
    with tempfile.NamedTemporaryFile(
        mode="w+", suffix=".es", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(SAMPLE_SCRIPT)
        tmp_path = tmp.name

    try:
        exit_code = main(["check", tmp_path])
        assert exit_code == 0
    finally:
        Path(tmp_path).unlink(missing_ok=True)
