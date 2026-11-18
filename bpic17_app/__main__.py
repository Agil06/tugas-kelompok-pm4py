"""Entrypoint for `python -m bpic17_app`."""

from __future__ import annotations

import argparse
import os
import sys

from bpic17_app.gui import launch_app


def main() -> int:
    parser = argparse.ArgumentParser(
        description="BPIC17 Desktop Event Log Analyzer (PM4Py + PySide6)"
    )
    parser.add_argument(
        "--xes",
        type=str,
        default=None,
        help="Optional path to a .xes file to load automatically on startup.",
    )
    args = parser.parse_args()

    xes_path = args.xes
    if xes_path is None:
        default_bpic = os.path.join("ignore_TUGAS-PM4PY", "BPI Challenge 2017.xes")
        if os.path.isfile(default_bpic):
            xes_path = default_bpic

    return launch_app(initial_xes=xes_path)


if __name__ == "__main__":
    sys.exit(main())
