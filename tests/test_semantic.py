"""
tests/test_semantic.py — Tests for the FlowScript semantic analyzer
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from parser   import parse
from semantic import SemanticAnalyzer, SemanticError, analyze


class TestSemantic:

    def _analyze(self, src: str):
        ast = parse(src)
        SemanticAnalyzer(ast).analyze()

    def _expect_error(self, src: str, fragment: str):
        with pytest.raises(SemanticError) as exc:
            self._analyze(src)
        assert fragment.lower() in str(exc.value).lower()

    # ── Valid programs ─────────────────────────────────────────

    def test_valid_simple(self):
        self._analyze('''
        SOURCE s AS CSV { path = "a.csv" }
        PIPELINE p { FETCH FROM s }
        OUTPUT o TO CSV { from = "p" path = "out.csv" }
        ''')

    def test_valid_multiple_sources(self):
        self._analyze('''
        SOURCE s1 AS CSV  { path = "a.csv" }
        SOURCE s2 AS JSON { path = "b.json" }
        PIPELINE p {
            FETCH FROM s1, s2
            JOIN s2 ON s1.id = s2.id
        }
        OUTPUT o TO STDOUT { from = "p" }
        ''')

    def test_valid_no_output(self):
        # No output is allowed at semantic level
        self._analyze('''
        SOURCE s AS CSV { path = "a.csv" }
        PIPELINE p { FETCH FROM s }
        ''')

    # ── Duplicate names ────────────────────────────────────────

    def test_duplicate_source_name(self):
        self._expect_error('''
        SOURCE s AS CSV { path = "a.csv" }
        SOURCE s AS JSON { path = "b.json" }
        ''', "duplicate source")

    def test_duplicate_pipeline_name(self):
        self._expect_error('''
        SOURCE s AS CSV { path = "a.csv" }
        PIPELINE p { FETCH FROM s }
        PIPELINE p { FETCH FROM s }
        ''', "duplicate pipeline")

    # ── Undeclared references ──────────────────────────────────

    def test_fetch_undeclared_source(self):
        self._expect_error('''
        PIPELINE p { FETCH FROM missing_source }
        ''', "undeclared source")

    def test_join_undeclared_source(self):
        self._expect_error('''
        SOURCE s AS CSV { path = "a.csv" }
        PIPELINE p {
            FETCH FROM s
            JOIN missing ON s.id = missing.id
        }
        ''', "undeclared source")

    def test_output_undeclared_pipeline(self):
        self._expect_error('''
        OUTPUT o TO CSV { from = "nonexistent" path = "out.csv" }
        ''', "undeclared pipeline")

    # ── Output validation ──────────────────────────────────────

    def test_output_missing_from(self):
        self._expect_error('''
        PIPELINE p { LIMIT 10 }
        OUTPUT o TO CSV { path = "out.csv" }
        ''', "missing required option 'from'")

    # ── Limit validation ──────────────────────────────────────

    def test_limit_zero_invalid(self):
        self._expect_error('''
        SOURCE s AS CSV { path = "a.csv" }
        PIPELINE p {
            FETCH FROM s
            LIMIT 0
        }
        ''', "positive integer")

    # ── analyze() convenience function ────────────────────────

    def test_analyze_function(self):
        ast = parse('SOURCE s AS CSV { path = "x.csv" }')
        analyze(ast)   # should not raise


if __name__ == "__main__":
    pytest.main([__file__, "-v"])