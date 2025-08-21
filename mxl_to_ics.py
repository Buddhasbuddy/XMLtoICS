#!/usr/bin/env python3
"""Convert a D2L/Desire2Learn .mxl/.xml schedule export to an .ics file."""
from pathlib import Path
import sys
from mxl_to_ics_impl import mxl_to_ics  # Companion module saved alongside this script
def main():
    if len(sys.argv) < 3:
        print("Usage: python mxl_to_ics.py <input.xml> <output.ics>")
        sys.exit(1)
    mxl_to_ics(Path(sys.argv[1]), Path(sys.argv[2]))
if __name__ == "__main__":
    main()
