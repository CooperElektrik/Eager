"""Entry point for python -m eager_script_lsp."""

import sys

from eager_script_lsp.cli import main

__all__: list[str] = []

if __name__ == "__main__":
    sys.exit(main())
