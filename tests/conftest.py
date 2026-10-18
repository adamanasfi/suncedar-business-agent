import os
import sys
import tempfile
from pathlib import Path

# Unit tests must never touch the real data/ folder: point the app at a throwaway directory
# BEFORE app.py is imported (it reads BUSINESS_BOT_DATA_DIR at import time).
os.environ["BUSINESS_BOT_DATA_DIR"] = tempfile.mkdtemp(prefix="suncedar_unit_")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
