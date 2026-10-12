#!/usr/bin/env python3
"""Export a Writerside instance to PDF / DOCX.

    python app.py -p /path/to/Writerside -i nsk -f pdf -t dark     # combined dark PDF
    python app.py -p /path/to/Writerside -i nsk -f pdf -f docx -m both
    python app.py instances -p /path/to/Writerside                 # list the instances (trees)
    python app.py --help

Run it with the project's virtual environment active (source .venv/bin/activate).
"""

import sys

try:
    from nxo_export.cli import main
except ImportError:
    sys.exit("nxo_export is not installed in this Python. Run: source .venv/bin/activate "
             "(first time: python3 -m venv .venv && source .venv/bin/activate && pip install -e '.[dev]')")

if __name__ == "__main__":
    main(prog_name="app.py")
