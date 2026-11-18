"""Permite ejecutar ``python -m dcf <TICKER>``."""

import sys

from dcf.cli import main

sys.exit(main())
