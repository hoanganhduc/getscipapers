import os
import sys
from . import main

#!/usr/bin/env python3
"""
Main entry point for the getscipapers_hoanganhduc package.
"""

if not __package__:
    # Make CLI runnable from source tree with
    #    python src/package
    package_source_path = os.path.dirname(os.path.dirname(__file__))
    sys.path.insert(0, package_source_path)

if __name__ == "__main__":
    main()