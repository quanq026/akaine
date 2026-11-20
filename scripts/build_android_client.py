"""Compatibility entry point. Run the package from the repository root."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from akaine_build.android import main


if __name__ == '__main__':
    main()
