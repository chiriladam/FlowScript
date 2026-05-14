"""
interpreter.py — Runtime Interpreter for FlowScript DSL

Executes a FlowScript AST:
  - Reads sources (API, CSV, JSON, XML, DATABASE)
  - Executes pipeline steps (FETCH, FILTER, MAP, JOIN, AGGREGATE, SORT, LIMIT)
  - Writes output (CSV, JSON, XML, DATABASE, STDOUT)

Internal data model: List[Dict[str, Any]]
"""

import sys
import os
import csv
import json
import re
import io
import xml.etree.ElementTree as ET
from copy import deepcopy
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(__file__))

from ast_nodes import (
    Program, SourceDecl, PipelineDecl, OutputDecl,
    FetchStep, FilterStep, MapStep, JoinStep,
    AggregateStep, SortStep, LimitStep,
    FieldMapping, AggRule, SortKey,
    Comparison, LogicalOp, NotOp,
    BinaryOp, Identifier, FieldAccess, FunctionCall,
    StringLiteral, NumberLiteral, BooleanLiteral, NullLiteral,
    AuthExpr, HeaderPair,
)

Row  = Dict[str, Any]
Table = List[Row]


class RuntimeError_(Exception):
    def __init__(self, message: str):
        super().__init__(f"[Runtime]: {message}")


# ─────────────────────────────────────────────────────────────
#  Expression Evaluator
# ─────────────────────────────────────────────────────────────

class Evaluator:
    """Evaluates expression AST nodes against a row."""

    def eval(self, node, row: Row) -> Any:
        if isinstance(node, StringLiteral):
            return node.value
        if isinstance(node, NumberLiteral):
            return node.value
        if isinstance(node, BooleanLiteral):
            return node.value
        if isinstance(node, NullLiteral):
            return None
        if isinstance(node, Identifier):
            return row.get(node.name)
        if isinstance(node, FieldAccess):
            # Try full dotted key first (e.g. "orders.amount")
            full = ".".join(node.parts)
            if full in row:
                return row[full]
            # Fallback: last part as field name
            return row.get(node.parts[-1])
        if isinstance(node, BinaryOp):
            return self._binary(node, row)
        if isinstance(node, FunctionCall):
            return self._funcall(node, row)
        if isinstance(node, Comparison):
            return self._comparison(node, row)
        if isinstance(node, LogicalOp):
            left = self.eval(node.left, row)
            if node.operator == "AND":
                return bool(left) and bool(self.eval(node.right, row))
            return bool(left) or bool(self.eval(node.right, row))
        if isinstance(node, NotOp):
            return not bool(self.eval(node.operand, row))
        raise RuntimeError_(f"Unknown expression node: {type(node).__name__}")

    def _binary(self, node: BinaryOp, row: Row) -> Any:
        l = self.eval(node.left,  row)
        r = self.eval(node.right, row)
        op = node.operator
        if op == "+":
            if isinstance(l, str) or isinstance(r, str):
                return str(l) + str(r)
            return l + r
        if op == "-": return l - r
        if op == "*": return l * r
        if op == "/":
            if r == 0:
                raise RuntimeError_("Division by zero")
            return l / r
        raise RuntimeError_(f"Unknown operator: {op}")

    def _comparison(self, node: Comparison, row: Row) -> bool:
        l = self.eval(node.left, row)
        op = node.operator
        if op == "IS NULL":     return l is None
        if op == "IS NOT NULL": return l is not None
        r = self.eval(node.right, row)
        if op == "==":   return l == r
        if op == "!=":   return l != r
        if op == "<":    return l < r
        if op == "<=":   return l <= r
        if op == ">":    return l > r
        if op == ">=":   return l >= r
        if op == "LIKE":
            pattern = "^" + re.escape(str(r)).replace("%", ".*").replace("_", ".") + "$"
            return bool(re.match(pattern, str(l), re.IGNORECASE))
        if op == "IN":
            return l in (r if isinstance(r, (list, tuple)) else [r])
        raise RuntimeError_(f"Unknown comparison operator: {op}")

    def _funcall(self, node: FunctionCall, row: Row) -> Any:
        name = node.name.upper()
        args = [self.eval(a, row) for a in node.args]
        if name == "UPPER":  return str(args[0]).upper()
        if name == "LOWER":  return str(args[0]).lower()
        if name == "LENGTH": return len(str(args[0]))
        if name == "STR":    return str(args[0])
        if name == "INT":    return int(args[0])
        if name == "FLOAT":  return float(args[0])
        if name == "COALESCE":
            for a in args:
                if a is not None:
                    return a
            return None
        raise RuntimeError_(f"Unknown function: {node.name}")


# ─────────────────────────────────────────────────────────────
#  Source Readers
# ─────────────────────────────────────────────────────────────

def _build_headers(source: SourceDecl) -> Dict[str, str]:
    headers = {"Accept": "application/json"}
    raw = source.options.get("headers", [])
    for h in raw:
        if isinstance(h, HeaderPair):
            headers[h.key] = h.value
    return headers


def _apply_auth(source: SourceDecl, headers: Dict[str, str],
                params: Dict[str, str]) -> None:
    auth = source.options.get("auth")
    if not isinstance(auth, AuthExpr):
        return
    if auth.method == "BEARER":
        headers["Authorization"] = f"Bearer {auth.arg1}"
    elif auth.method == "BASIC":
        import base64
        creds = base64.b64encode(f"{auth.arg1}:{auth.arg2}".encode()).decode()
        headers["Authorization"] = f"Basic {creds}"
    elif auth.method == "API_KEY":
        params[auth.arg1] = auth.arg2


def read_api(source: SourceDecl) -> Table:
    try:
        import urllib.request
        import urllib.parse
    except ImportError:
        raise RuntimeError_("urllib not available")

    url     = source.options.get("url", "")
    method  = source.options.get("method", "GET").upper()
    headers = _build_headers(source)
    params: Dict[str, str] = {}
    _apply_auth(source, headers, params)

    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)

    req = urllib.request.Request(url, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except Exception as e:
        raise RuntimeError_(f"API request failed for '{source.name}': {e}")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError_(f"API response is not valid JSON for '{source.name}': {e}")

    if isinstance(data, list):
        return [_flatten(row) for row in data]
    if isinstance(data, dict):
        # Try common wrapper keys
        for key in ("data", "results", "items", "records", "rows"):
            if key in data and isinstance(data[key], list):
                return [_flatten(row) for row in data[key]]
        return [_flatten(data)]
    raise RuntimeError_(f"Unexpected API response shape for '{source.name}'")


def read_csv(source: SourceDecl) -> Table:
    path     = source.options.get("path", "")
    encoding = source.options.get("encoding", "utf-8")
    try:
        with open(path, newline="", encoding=encoding) as f:
            reader = csv.DictReader(f)
            return [dict(row) for row in reader]
    except FileNotFoundError:
        raise RuntimeError_(f"CSV file not found: '{path}'")
    except Exception as e:
        raise RuntimeError_(f"Error reading CSV '{path}': {e}")


def read_json(source: SourceDecl) -> Table:
    path     = source.options.get("path", "")
    encoding = source.options.get("encoding", "utf-8")
    try:
        with open(path, encoding=encoding) as f:
            data = json.load(f)
    except FileNotFoundError:
        raise RuntimeError_(f"JSON file not found: '{path}'")
    except json.JSONDecodeError as e:
        raise RuntimeError_(f"Invalid JSON in '{path}': {e}")

    if isinstance(data, list):
        return [_flatten(row) for row in data]
    if isinstance(data, dict):
        return [_flatten(data)]
    raise RuntimeError_(f"JSON file must contain an object or array: '{path}'")


def read_xml(source: SourceDecl) -> Table:
    path = source.options.get("path", "")
    try:
        tree = ET.parse(path)
    except FileNotFoundError:
        raise RuntimeError_(f"XML file not found: '{path}'")
    except ET.ParseError as e:
        raise RuntimeError_(f"Invalid XML in '{path}': {e}")

    root = tree.getroot()
    rows: Table = []
    children = list(root)
    if not children:
        return [_xml_element_to_dict(root)]
    for child in children:
        rows.append(_xml_element_to_dict(child))
    return rows


def read_database(source: SourceDecl) -> Table:
    url   = source.options.get("url", "")
    table = source.options.get("table", "")
    query = source.options.get("query", "")
    auth  = source.options.get("auth")

    try:
        if url.startswith("sqlite"):
            import sqlite3
            db_path = url.replace("sqlite:///", "").replace("sqlite://", "")
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            sql = query if query else f"SELECT * FROM {table}"
            cur.execute(sql)
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            return rows
        else:
            try:
                import psycopg2
                import psycopg2.extras
                conn = psycopg2.connect(url)
                cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                sql  = query if query else f"SELECT * FROM {table}"
                cur.execute(sql)
                rows = [dict(r) for r in cur.fetchall()]
                conn.close()
                return rows
            except ImportError:
                raise RuntimeError_(
                    "psycopg2 is not installed. "
                    "Install it with: pip install psycopg2-binary"
                )
    except RuntimeError_:
        raise
    except Exception as e:
        raise RuntimeError_(f"Database error for '{source.name}': {e}")


# ─────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────

def _flatten(obj: Any, prefix: str = "") -> Dict[str, Any]:
    """Flatten a nested dict into a single-level dict with dot-notation keys."""
    result: Dict[str, Any] = {}
    if not isinstance(obj, dict):
        return {"value": obj}
    for k, v in obj.items():
        full_key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            result.update(_flatten(v, full_key))
        else:
            result[full_key] = v
            result[k] = v   # also store without prefix for convenience
    return result


def _xml_element_to_dict(el: ET.Element) -> Dict[str, Any]:
    result: Dict[str, Any] = dict(el.attrib)
    for child in el:
        result[child.tag] = child.text or ""
    if el.text and el.text.strip():
        result["_text"] = el.text.strip()
    return result


# ─────────────────────────────────────────────────────────────
#  Pipeline Step Executors
# ─────────────────────────────────────────────────────────────

def exec_fetch(step: FetchStep, sources: Dict[str, Table]) -> Table:
    result: Table = []
    for name in step.sources:
        result.extend(deepcopy(sources.get(name, [])))
    return result


def exec_filter(step: FilterStep, table: Table) -> Table:
    ev = Evaluator()
    return [row for row in table if ev.eval(step.condition, row)]


def exec_map(step: MapStep, table: Table) -> Table:
    ev = Evaluator()
    result: Table = []
    for row in table:
        new_row: Row = {}
        for mapping in step.mappings:
            new_row[mapping.target] = ev.eval(mapping.expr, row)
        result.append(new_row)
    return result


def exec_join(step: JoinStep, table: Table,
              sources: Dict[str, Table]) -> Table:
    right_table = sources.get(step.source, [])
    left_key    = step.left_key.split(".")[-1]
    right_key   = step.right_key.split(".")[-1]
    join_type   = step.join_type.upper()

    # Build index on right table
    index: Dict[Any, List[Row]] = {}
    for row in right_table:
        k = row.get(right_key)
        index.setdefault(k, []).append(row)

    result: Table = []
    matched_right = set()

    for left_row in table:
        k = left_row.get(left_key)
        right_matches = index.get(k, [])

        if right_matches:
            for right_row in right_matches:
                merged = {**right_row, **left_row}
                result.append(merged)
                matched_right.add(id(right_row))
        else:
            if join_type in ("LEFT", "FULL"):
                result.append(dict(left_row))

    if join_type in ("RIGHT", "FULL"):
        for right_row in right_table:
            if id(right_row) not in matched_right:
                result.append(dict(right_row))

    return result


def exec_aggregate(step: AggregateStep, table: Table) -> Table:
    if not table:
        return []

    result: Row = {}
    for rule in step.rules:
        field  = rule.field
        values = [row.get(field) for row in table
                  if row.get(field) is not None]
        func   = rule.func.upper()

        if func == "COUNT":
            result[rule.alias] = len(table)
        elif func == "SUM":
            result[rule.alias] = sum(float(v) for v in values) if values else 0
        elif func == "AVG":
            result[rule.alias] = (sum(float(v) for v in values) / len(values)
                                  if values else 0)
        elif func == "MIN":
            result[rule.alias] = min(values) if values else None
        elif func == "MAX":
            result[rule.alias] = max(values) if values else None

    return [result]


def exec_sort(step: SortStep, table: Table) -> Table:
    for key in reversed(step.keys):
        reverse = key.direction.upper() == "DESC"
        field   = key.field
        table = sorted(
            table,
            key=lambda r: (r.get(field) is None, r.get(field)),
            reverse=reverse,
        )
    return table


def exec_limit(step: LimitStep, table: Table) -> Table:
    return table[:step.count]


# ─────────────────────────────────────────────────────────────
#  Output Writers
# ─────────────────────────────────────────────────────────────

def write_csv(table: Table, options: Dict) -> None:
    path      = options.get("path", "output.csv")
    delimiter = options.get("delimiter", ",")
    if not table:
        print(f"[Output] Empty result — nothing written to '{path}'")
        return
    _ensure_dir(path)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=table[0].keys(),
                                delimiter=delimiter)
        writer.writeheader()
        writer.writerows(table)
    print(f"[Output] Written {len(table)} rows to '{path}' (CSV)")


def write_json(table: Table, options: Dict) -> None:
    path   = options.get("path", "output.json")
    pretty = options.get("pretty", False)
    _ensure_dir(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(table, f, indent=2 if pretty else None,
                  default=str, ensure_ascii=False)
    print(f"[Output] Written {len(table)} rows to '{path}' (JSON)")


def write_xml(table: Table, options: Dict) -> None:
    path = options.get("path", "output.xml")
    _ensure_dir(path)
    root = ET.Element("results")
    for row in table:
        record = ET.SubElement(root, "record")
        for k, v in row.items():
            field = ET.SubElement(record, str(k).replace(" ", "_"))
            field.text = str(v) if v is not None else ""
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="unicode", xml_declaration=True)
    print(f"[Output] Written {len(table)} rows to '{path}' (XML)")


def write_database(table: Table, options: Dict) -> None:
    url   = options.get("url", "")
    tbl   = options.get("table", "output")
    if not table:
        print("[Output] Empty result — nothing written to database")
        return
    try:
        import sqlite3
        db_path = url.replace("sqlite:///", "").replace("sqlite://", "") or "output.db"
        conn = sqlite3.connect(db_path)
        cur  = conn.cursor()
        cols = list(table[0].keys())
        col_defs = ", ".join(f'"{c}" TEXT' for c in cols)
        cur.execute(f'CREATE TABLE IF NOT EXISTS "{tbl}" ({col_defs})')
        placeholders = ", ".join("?" * len(cols))
        for row in table:
            cur.execute(
                f'INSERT INTO "{tbl}" VALUES ({placeholders})',
                [str(row.get(c, "")) for c in cols]
            )
        conn.commit()
        conn.close()
        print(f"[Output] Written {len(table)} rows to table '{tbl}' in '{db_path}'")
    except Exception as e:
        raise RuntimeError_(f"Database write error: {e}")


def write_stdout(table: Table, options: Dict) -> None:
    if not table:
        print("[Output] Empty result")
        return
    cols   = list(table[0].keys())
    widths = {c: max(len(c), max((len(str(r.get(c, ""))) for r in table), default=0))
              for c in cols}
    sep    = "+-" + "-+-".join("-" * widths[c] for c in cols) + "-+"
    header = "| " + " | ".join(c.ljust(widths[c]) for c in cols) + " |"
    print(sep)
    print(header)
    print(sep)
    for row in table:
        line = "| " + " | ".join(str(row.get(c, "")).ljust(widths[c])
                                  for c in cols) + " |"
        print(line)
    print(sep)
    print(f"[Output] {len(table)} row(s)")


def _ensure_dir(path: str) -> None:
    import os
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)


# ─────────────────────────────────────────────────────────────
#  Main Interpreter
# ─────────────────────────────────────────────────────────────

SOURCE_READERS = {
    "API":      read_api,
    "CSV":      read_csv,
    "JSON":     read_json,
    "XML":      read_xml,
    "DATABASE": read_database,
}

OUTPUT_WRITERS = {
    "CSV":      write_csv,
    "JSON":     write_json,
    "XML":      write_xml,
    "DATABASE": write_database,
    "STDOUT":   write_stdout,
}


class Interpreter:
    """
    Executes a FlowScript program.

    Usage:
        Interpreter(ast).run()
    """

    def __init__(self, program: Program):
        self._program   = program
        self._sources:   Dict[str, SourceDecl]   = {}
        self._pipelines: Dict[str, PipelineDecl] = {}
        self._outputs:   Dict[str, OutputDecl]   = {}
        self._loaded:    Dict[str, Table]         = {}
        self._results:   Dict[str, Table]         = {}

    def run(self) -> None:
        # Collect declarations
        for stmt in self._program.statements:
            if isinstance(stmt, SourceDecl):
                self._sources[stmt.name] = stmt
            elif isinstance(stmt, PipelineDecl):
                self._pipelines[stmt.name] = stmt
            elif isinstance(stmt, OutputDecl):
                self._outputs[stmt.name] = stmt

        # Load all sources
        for name, src in self._sources.items():
            print(f"[Source] Loading '{name}' ({src.source_type})...")
            reader = SOURCE_READERS.get(src.source_type)
            if not reader:
                raise RuntimeError_(f"Unknown source type: {src.source_type}")
            self._loaded[name] = reader(src)
            print(f"[Source] '{name}' loaded — {len(self._loaded[name])} rows")

        # Execute all pipelines
        for name, pipe in self._pipelines.items():
            print(f"\n[Pipeline] Running '{name}'...")
            self._results[name] = self._run_pipeline(pipe)
            print(f"[Pipeline] '{name}' done — {len(self._results[name])} rows")

        # Write all outputs
        for name, out in self._outputs.items():
            print(f"\n[Output] Writing '{name}' ({out.output_type})...")
            pipeline_name = out.options.get("from", "")
            table = self._results.get(pipeline_name, [])
            writer = OUTPUT_WRITERS.get(out.output_type)
            if not writer:
                raise RuntimeError_(f"Unknown output type: {out.output_type}")
            writer(table, out.options)

    def _run_pipeline(self, pipe: PipelineDecl) -> Table:
        table: Table = []
        for step in pipe.steps:
            if isinstance(step, FetchStep):
                table = exec_fetch(step, self._loaded)
                print(f"  FETCH → {len(table)} rows")
            elif isinstance(step, FilterStep):
                before = len(table)
                table = exec_filter(step, table)
                print(f"  FILTER → {len(table)} rows (removed {before - len(table)})")
            elif isinstance(step, MapStep):
                table = exec_map(step, table)
                print(f"  MAP → {len(table)} rows")
            elif isinstance(step, JoinStep):
                before = len(table)
                table = exec_join(step, table, self._loaded)
                print(f"  JOIN '{step.source}' ({step.join_type}) → {len(table)} rows")
            elif isinstance(step, AggregateStep):
                table = exec_aggregate(step, table)
                print(f"  AGGREGATE → {len(table)} rows")
            elif isinstance(step, SortStep):
                table = exec_sort(step, table)
                print(f"  SORT → {len(table)} rows")
            elif isinstance(step, LimitStep):
                table = exec_limit(step, table)
                print(f"  LIMIT {step.count} → {len(table)} rows")
        return table


def run(program: Program) -> None:
    """Execute a FlowScript program."""
    Interpreter(program).run()