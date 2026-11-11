"""Every corpus resume (fresher and experienced, many layouts) must be understood and reproduced exactly."""

from __future__ import annotations

import sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import tempfile
import unittest
from pathlib import Path

from tests.corpus.builders import CORPUS, build_corpus
from tests.corpus.evaluate import evaluate


class CorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.paths = build_corpus(Path(tempfile.mkdtemp(prefix="rw-corpus-")))

    def test_corpus_is_broad(self) -> None:
        self.assertGreaterEqual(len(CORPUS), 40)
        self.assertEqual({s.level for s in CORPUS}, {"fresher", "experienced"})
        for dimension in ("header", "heading", "bullet", "dates", "skills", "layout"):
            self.assertGreaterEqual(len({getattr(s, dimension) for s in CORPUS}), 3, dimension)

    def test_every_format_is_analysed_generated_and_sanitised_correctly(self) -> None:
        failures = {}
        for spec in CORPUS:
            issues = evaluate(spec, self.paths[spec.id])
            if issues:
                failures[spec.id] = issues
        self.assertEqual(failures, {}, "\n" + "\n".join(f"{k}: {v}" for k, v in failures.items()))


if __name__ == "__main__":
    unittest.main()
