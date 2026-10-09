"""Executable module entrypoint for python -m eager_runtime."""

import sys

from eager_runtime.cli import main

if __name__ == "__main__":
    sys.exit(main())
