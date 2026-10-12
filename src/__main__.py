"""`python -m nxo_export ...` (same as the `nxo-export` command)."""

from .cli import main

if __name__ == "__main__":
    main(prog_name="nxo-export")
