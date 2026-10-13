"""Read parsed TCEQ detail pages from the raw shards."""
import base64
import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_detail import parse  # noqa: E402

RAW = Path(__file__).resolve().parent.parent / "data" / "raw" / "details"


def iter_details(wanted=None):
    """Yield (incident, parsed page) for every saved page, or only for incidents in `wanted`."""
    for shard in sorted(RAW.glob("shard_*.jsonl.gz")):
        with gzip.open(shard, "rt", encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                if wanted is not None and rec["incident"] not in wanted:
                    continue
                yield rec["incident"], parse(base64.b64decode(rec["body_b64"]))
