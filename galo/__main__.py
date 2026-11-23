"""Permite executar `python -m galo ...`."""

import sys

from .cli.main import main

sys.exit(main())
