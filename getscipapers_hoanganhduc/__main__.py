#!/usr/bin/env python3

"""Module entry point for ``python -m getscipapers_hoanganhduc``.

This thin wrapper simply delegates to :func:`getscipapers_hoanganhduc.main`
while ensuring the environment is prepared for command-line execution.
"""

import os
import sys
from . import main

if not __package__:
    # Make CLI runnable from source tree with
    #    python src/package
    package_source_path = os.path.dirname(os.path.dirname(__file__))
    sys.path.insert(0, package_source_path)

if __name__ == "__main__":
    main()