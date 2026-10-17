"""Run mutmut and fail when the mutation score is below the required threshold.

    python scripts/mutation.py                    # every mutant (release candidates)
    python scripts/mutation.py --changed origin/dev  # the modules a pull request changes

A pull request mutates only the domain and application modules it changes; the release
candidate's CI run mutates everything (ADR 0029). The threshold is the same for both.
A run that stops before it checked every mutant (seen once in CI: every mutant "not
checked") is resumed once; mutmut keeps what it already checked.
"""

import argparse
import fnmatch
import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

THRESHOLD = 0.90
LOG = Path("mutmut.log")
MUTANTS = Path("mutants")
MUTATED = ("src/rhinvoice/domain/", "src/rhinvoice/application/")
ATTEMPTS = 2

# mutmut's exit codes (mutmut.stats): 1 and 3 kill a mutant, 36 and the SIGXCPU codes are
# timeouts (counted as killed, as before), 34 skips it, None is not checked yet.
KILLED = {1, 3, 24, -24, 36, 152, 255}
SKIPPED = 34


def changed_modules(base: str) -> list[str]:
    """Mutant name patterns for the mutated modules changed since ``base``."""
    diff = subprocess.run(  # noqa: S603 - fixed git command, the ref comes from the Makefile
        ["git", "diff", "--name-only", f"{base}...HEAD", "--", "."],  # noqa: S607 - git on PATH
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    settings = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    excluded: list[str] = settings["tool"]["mutmut"]["do_not_mutate"]
    patterns: list[str] = []
    for name in diff:
        path = name.removeprefix("backend/")
        if not (path.endswith(".py") and path.startswith(MUTATED) and Path(path).is_file()):
            continue
        if any(fnmatch.fnmatch(path, pattern) for pattern in excluded):
            continue
        module = path.removeprefix("src/").removesuffix(".py").removesuffix("/__init__")
        patterns.append(module.replace("/", ".") + ".x*")
    return patterns


def results(patterns: list[str]) -> dict[str, int | None]:
    """Exit code per mutant, only the selected ones when patterns are given."""
    codes: dict[str, int | None] = {}
    for meta in MUTANTS.rglob("*.py.meta"):
        exit_codes: dict[str, int | None] = json.loads(meta.read_text(encoding="utf-8"))[
            "exit_code_by_key"
        ]
        codes.update(exit_codes)
    if patterns:
        codes = {
            key: code
            for key, code in codes.items()
            if any(fnmatch.fnmatch(key, pattern) for pattern in patterns)
        }
    return codes


def run(patterns: list[str]) -> None:
    with LOG.open("a", encoding="utf-8") as log:
        # mutmut exits non-zero when mutants survive; the score below is the gate.
        subprocess.run(  # noqa: S603 - fixed command, the names are module patterns
            ["mutmut", "run", *patterns],  # noqa: S607 - mutmut of this environment
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--changed", metavar="BASE", help="only modules changed since BASE")
    args = parser.parse_args()
    patterns: list[str] = []
    if args.changed:
        patterns = changed_modules(args.changed)
        if not patterns:
            sys.stdout.write("no domain or application module changed: nothing to mutate\n")
            return 0
        sys.stdout.write("mutating " + " ".join(patterns) + "\n")

    shutil.rmtree(MUTANTS, ignore_errors=True)
    LOG.unlink(missing_ok=True)
    run(patterns)
    codes = results(patterns)
    for _ in range(ATTEMPTS - 1):
        if None not in codes.values():
            break
        sys.stdout.write("mutmut stopped before it checked every mutant; resuming\n")
        run(patterns)
        codes = results(patterns)

    unchecked = sum(code is None for code in codes.values())
    if unchecked:
        sys.stdout.write("".join(LOG.read_text(encoding="utf-8").splitlines(keepends=True)[-40:]))
        sys.stderr.write(f"{unchecked} mutants were not checked\n")
        return 1
    tested = sum(code != SKIPPED for code in codes.values())
    killed = sum(code in KILLED for code in codes.values())
    if not tested:
        sys.stdout.write("the changed modules hold no mutants\n")
        return 0
    score = killed / tested
    sys.stdout.write(f"mutation score: {score:.1%} ({killed}/{tested} killed)\n")
    if score < THRESHOLD:
        sys.stderr.write(f"mutation score below {THRESHOLD:.0%}; see: uv run mutmut results\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
