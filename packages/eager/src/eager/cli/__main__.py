"""Allow ``python -m eager.cli`` invocation."""

import sys

from eager.cli import main

if __name__ == "__main__":
    sys.exit(main())
