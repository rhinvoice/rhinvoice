"""Fail when the mutmut mutation score is below the required threshold.

Reads ``mutants/mutmut-cicd-stats.json`` written by ``mutmut export-cicd-stats``.
"""

import json
import sys
from pathlib import Path

THRESHOLD = 0.90
STATS_FILE = Path("mutants/mutmut-cicd-stats.json")


def main() -> int:
    stats = json.loads(STATS_FILE.read_text(encoding="utf-8"))
    total = int(stats["total"]) - int(stats["skipped"])
    killed = int(stats["killed"]) + int(stats["timeout"])
    score = killed / total if total else 1.0
    sys.stdout.write(f"mutation score: {score:.1%} ({killed}/{total} killed)\n")
    if score < THRESHOLD:
        sys.stderr.write(f"mutation score below {THRESHOLD:.0%}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
