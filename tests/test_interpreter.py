"""
tests/test_interpreter.py — Tests for the FlowScript interpreter
"""

import sys
import os
import json
import csv
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from parser      import parse
from semantic    import analyze
from interpreter import (
    Interpreter, RuntimeError_,
    exec_fetch, exec_filter, exec_map, exec_join,
    exec_aggregate, exec_sort, exec_limit,
    read_csv, read_json, read_xml,
    write_csv, write_json, write_stdout,
    Evaluator,
)
from ast_nodes import *


# ── Fixtures ───────────────────────────────────────────────────

SAMPLE_TABLE = [
    {"id": "1", "name": "Alice", "age": 30, "status": "active",  "amount": 250.0},
    {"id": "2", "name": "Bob",   "age": 17, "status": "inactive","amount": 80.0},
    {"id": "3", "name": "Carol", "age": 25, "status": "active",  "amount": 450.0},
    {"id": "4", "name": "Dave",  "age": 15, "status": "active",  "amount": 120.0},
]


# ── Evaluator tests ────────────────────────────────────────────

class TestEvaluator:
    ev = Evaluator()
    row = {"name": "Alice", "age": 30, "price": 10.0, "qty": 3}

    def test_string_literal(self):
        assert self.ev.eval(StringLiteral("hello"), self.row) == "hello"

    def test_number_literal(self):
        assert self.ev.eval(NumberLiteral(42), self.row) == 42

    def test_boolean_literal(self):
        assert self.ev.eval(BooleanLiteral(True), self.row) is True

    def test_null_literal(self):
        assert self.ev.eval(NullLiteral(), self.row) is None

    def test_identifier(self):
        assert self.ev.eval(Identifier("name"), self.row) == "Alice"

    def test_binary_add_numbers(self):
        node = BinaryOp(NumberLiteral(2.0), "+", NumberLiteral(3.0))
        assert self.ev.eval(node, self.row) == 5.0

    def test_binary_add_strings(self):
        node = BinaryOp(StringLiteral("hello"), "+", StringLiteral(" world"))
        assert self.ev.eval(node, self.row) == "hello world"

    def test_binary_multiply(self):
        node = BinaryOp(Identifier("price"), "*", Identifier("qty"))
        assert self.ev.eval(node, self.row) == 30.0

    def test_comparison_eq(self):
        node = Comparison(Identifier("name"), "==", StringLiteral("Alice"))
        assert self.ev.eval(node, self.row) is True

    def test_comparison_gte(self):
        node = Comparison(Identifier("age"), ">=", NumberLiteral(30))
        assert self.ev.eval(node, self.row) is True

    def test_comparison_is_null(self):
        node = Comparison(Identifier("missing"), "IS NULL", None)
        assert self.ev.eval(node, self.row) is True

    def test_logical_and(self):
        node = LogicalOp(
            Comparison(Identifier("age"), ">=", NumberLiteral(18)),
            "AND",
            Comparison(Identifier("name"), "==", StringLiteral("Alice"))
        )
        assert self.ev.eval(node, self.row) is True

    def test_logical_or(self):
        node = LogicalOp(
            Comparison(Identifier("age"), "<", NumberLiteral(10)),
            "OR",
            Comparison(Identifier("name"), "==", StringLiteral("Alice"))
        )
        assert self.ev.eval(node, self.row) is True

    def test_not_op(self):
        node = NotOp(Comparison(Identifier("name"), "==", StringLiteral("Bob")))
        assert self.ev.eval(node, self.row) is True

    def test_like_operator(self):
        node = Comparison(Identifier("name"), "LIKE", StringLiteral("Al%"))
        assert self.ev.eval(node, self.row) is True


# ── Pipeline step tests ────────────────────────────────────────

class TestPipelineSteps:

    def test_exec_fetch_single(self):
        step = FetchStep(sources=["s1"])
        sources = {"s1": [{"a": 1}, {"a": 2}]}
        result = exec_fetch(step, sources)
        assert len(result) == 2

    def test_exec_fetch_multiple(self):
        step = FetchStep(sources=["s1", "s2"])
        sources = {"s1": [{"a": 1}], "s2": [{"b": 2}, {"b": 3}]}
        result = exec_fetch(step, sources)
        assert len(result) == 3

    def test_exec_filter(self):
        cond = Comparison(Identifier("age"), ">=", NumberLiteral(18))
        step = FilterStep(condition=cond)
        result = exec_filter(step, SAMPLE_TABLE)
        assert len(result) == 2
        assert all(r["age"] >= 18 for r in result)

    def test_exec_filter_status(self):
        cond = Comparison(Identifier("status"), "==", StringLiteral("active"))
        step = FilterStep(condition=cond)
        result = exec_filter(step, SAMPLE_TABLE)
        assert len(result) == 3

    def test_exec_map(self):
        mapping = FieldMapping(
            target="revenue",
            expr=BinaryOp(Identifier("amount"), "*", NumberLiteral(1.1))
        )
        step = MapStep(mappings=[mapping])
        result = exec_map(step, SAMPLE_TABLE[:1])
        assert "revenue" in result[0]
        assert abs(result[0]["revenue"] - 275.0) < 0.01

    def test_exec_join_inner(self):
        left  = [{"id": "1", "val": "A"}, {"id": "2", "val": "B"}]
        right = [{"id": "1", "extra": "X"}]
        step  = JoinStep(source="r", left_key="id", right_key="id", join_type="INNER")
        result = exec_join(step, left, {"r": right})
        assert len(result) == 1
        assert result[0]["val"] == "A"
        assert result[0]["extra"] == "X"

    def test_exec_join_left(self):
        left  = [{"id": "1"}, {"id": "99"}]
        right = [{"id": "1", "extra": "X"}]
        step  = JoinStep(source="r", left_key="id", right_key="id", join_type="LEFT")
        result = exec_join(step, left, {"r": right})
        assert len(result) == 2

    def test_exec_aggregate_sum_count(self):
        rules = [
            AggRule(func="SUM",   field="amount", alias="total"),
            AggRule(func="COUNT", field="amount", alias="cnt"),
            AggRule(func="AVG",   field="amount", alias="avg"),
            AggRule(func="MIN",   field="amount", alias="min_val"),
            AggRule(func="MAX",   field="amount", alias="max_val"),
        ]
        step   = AggregateStep(rules=rules)
        result = exec_aggregate(step, SAMPLE_TABLE)
        assert len(result) == 1
        assert result[0]["total"] == sum(r["amount"] for r in SAMPLE_TABLE)
        assert result[0]["cnt"]   == 4
        assert result[0]["min_val"] == 80.0
        assert result[0]["max_val"] == 450.0

    def test_exec_sort_asc(self):
        step   = SortStep(keys=[SortKey(field="amount", direction="ASC")])
        result = exec_sort(step, SAMPLE_TABLE[:])
        amounts = [r["amount"] for r in result]
        assert amounts == sorted(amounts)

    def test_exec_sort_desc(self):
        step   = SortStep(keys=[SortKey(field="amount", direction="DESC")])
        result = exec_sort(step, SAMPLE_TABLE[:])
        amounts = [r["amount"] for r in result]
        assert amounts == sorted(amounts, reverse=True)

    def test_exec_limit(self):
        step   = LimitStep(count=2)
        result = exec_limit(step, SAMPLE_TABLE)
        assert len(result) == 2

    def test_exec_limit_larger_than_table(self):
        step   = LimitStep(count=100)
        result = exec_limit(step, SAMPLE_TABLE)
        assert len(result) == len(SAMPLE_TABLE)


# ── File reader tests ──────────────────────────────────────────

class TestReaders:

    def test_read_csv(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv",
                                        delete=False, encoding="utf-8") as f:
            f.write("id,name,age\n1,Alice,30\n2,Bob,25\n")
            path = f.name
        src = SourceDecl(name="t", source_type="CSV",
                         options={"path": path, "encoding": "utf-8"})
        result = read_csv(src)
        assert len(result) == 2
        assert result[0]["name"] == "Alice"
        os.unlink(path)

    def test_read_json_list(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                        delete=False, encoding="utf-8") as f:
            json.dump([{"id": 1, "val": "x"}, {"id": 2, "val": "y"}], f)
            path = f.name
        src = SourceDecl(name="t", source_type="JSON",
                         options={"path": path})
        result = read_json(src)
        assert len(result) == 2
        os.unlink(path)

    def test_read_json_dict(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                        delete=False, encoding="utf-8") as f:
            json.dump({"id": 1, "val": "x"}, f)
            path = f.name
        src = SourceDecl(name="t", source_type="JSON",
                         options={"path": path})
        result = read_json(src)
        assert len(result) == 1
        os.unlink(path)

    def test_read_xml(self):
        xml = '<?xml version="1.0"?><root><item id="1" name="A"/><item id="2" name="B"/></root>'
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml",
                                        delete=False, encoding="utf-8") as f:
            f.write(xml)
            path = f.name
        src = SourceDecl(name="t", source_type="XML", options={"path": path})
        result = read_xml(src)
        assert len(result) == 2
        os.unlink(path)

    def test_read_csv_file_not_found(self):
        src = SourceDecl(name="t", source_type="CSV",
                         options={"path": "/nonexistent/file.csv"})
        with pytest.raises(RuntimeError_):
            read_csv(src)


# ── Writer tests ───────────────────────────────────────────────

class TestWriters:

    def test_write_csv(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        write_csv(SAMPLE_TABLE, {"path": path})
        with open(path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 4
        os.unlink(path)

    def test_write_json(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        write_json(SAMPLE_TABLE, {"path": path, "pretty": True})
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 4
        os.unlink(path)

    def test_write_stdout(self, capsys):
        write_stdout(SAMPLE_TABLE[:2], {})
        out = capsys.readouterr().out
        assert "Alice" in out
        assert "Bob"   in out

    def test_write_empty_stdout(self, capsys):
        write_stdout([], {})
        out = capsys.readouterr().out
        assert "Empty" in out


# ── Full integration test ──────────────────────────────────────

class TestIntegration:

    def test_full_csv_pipeline(self, tmp_path):
        # Create input CSV
        orders = tmp_path / "orders.csv"
        orders.write_text("id,amount,status\n1,100,completed\n2,50,pending\n3,200,completed\n")

        out_path = tmp_path / "out.json"

        # Use forward slashes to avoid Windows backslash escape issues
        orders_str   = str(orders).replace("\\", "/")
        out_path_str = str(out_path).replace("\\", "/")

        src = f'''
        SOURCE orders AS CSV {{
            path = "{orders_str}"
        }}
        PIPELINE report {{
            FETCH FROM orders
            FILTER WHERE orders.status == "completed"
            AGGREGATE {{
                SUM(amount)  AS total
                COUNT(id)    AS cnt
            }}
        }}
        OUTPUT result TO JSON {{
            from   = "report"
            path   = "{out_path_str}"
            pretty = true
        }}
        '''
        ast = parse(src)
        analyze(ast)
        Interpreter(ast).run()

        data = json.loads(out_path.read_text())
        assert len(data) == 1
        assert float(data[0]["total"]) == 300.0
        assert int(data[0]["cnt"])     == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])