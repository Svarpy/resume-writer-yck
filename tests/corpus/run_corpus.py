"""Print a report for the whole corpus: ``python -m tests.corpus.run_corpus``."""

from __future__ import annotations

import tempfile
from pathlib import Path

from tests.corpus.builders import CORPUS, build_corpus
from tests.corpus.evaluate import evaluate


def main() -> int:
    paths = build_corpus(Path(tempfile.mkdtemp(prefix="rw-corpus-")))
    failed = 0
    for spec in CORPUS:
        issues = evaluate(spec, paths[spec.id])
        failed += bool(issues)
        label = f"{spec.id} [{spec.level}, header={spec.header}, heading={spec.heading}, bullet={spec.bullet}, dates={spec.dates}, skills={spec.skills}]"
        print(("FAIL " if issues else "ok   ") + label)
        for issue in issues:
            print("       -", issue)
    print(f"\n{len(CORPUS) - failed}/{len(CORPUS)} formats handled")
    return failed


if __name__ == "__main__":
    raise SystemExit(main())
