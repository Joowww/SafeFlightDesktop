import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Never touch the real user configuration while testing.
os.environ.setdefault("SAFEFLIGHT_CONFIG_DIR", str(ROOT / "build" / "test-config"))
os.environ.setdefault("SAFEFLIGHT_LOG_DIR", str(ROOT / "build" / "test-logs"))

VECTORS_PATH = ROOT / "shared" / "protocols" / "mavlink-test-vectors.json"
