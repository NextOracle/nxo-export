"""`python -m nxo_ws_export ...` (same as the `nxo-ws-export` command)."""

from .cli import main

if __name__ == "__main__":
    main(prog_name="nxo-ws-export")
