import os
import sys

os.environ.setdefault("PYTHONUTF8", "1")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
