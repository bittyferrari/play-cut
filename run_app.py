"""PyInstaller 的進入點（打包成 exe 時用）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from playcut.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
