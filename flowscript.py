#!/usr/bin/env python3
"""
flowscript.py — Command-line runner for FlowScript DSL

Usage:
    python flowscript.py program.ds
    python flowscript.py program.ds --check      # only parse + semantic check
    python flowscript.py program.ds --tokens     # print tokens and exit
    python flowscript.py program.ds --ast        # print AST and exit
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from lexer       import Lexer, LexerError
from parser      import Parser, ParseError
from semantic    import SemanticAnalyzer, SemanticError
from interpreter import Interpreter, RuntimeError_


def main():
    ap = argparse.ArgumentParser(
        prog="flowscript",
        description="FlowScript DSL runner — Multi-Source Data Integration Language",
    )
    ap.add_argument("file",    help="Path to a .ds FlowScript program")
    ap.add_argument("--check",  action="store_true",
                    help="Parse and check semantics only, do not execute")
    ap.add_argument("--tokens", action="store_true",
                    help="Print the token stream and exit")
    ap.add_argument("--ast",    action="store_true",
                    help="Print the AST and exit")
    args = ap.parse_args()

    # Read source file
    try:
        with open(args.file, encoding="utf-8") as f:
            source = f.read()
    except FileNotFoundError:
        print(f"Error: file not found: '{args.file}'", file=sys.stderr)
        sys.exit(1)

    # ── Lex ──────────────────────────────────────────────────
    try:
        tokens = Lexer(source).tokenize()
    except LexerError as e:
        print(f"Lexer error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.tokens:
        for tok in tokens:
            print(tok)
        return

    # ── Parse ─────────────────────────────────────────────────
    try:
        ast = Parser(tokens).parse()
    except ParseError as e:
        print(f"Parse error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.ast:
        _print_ast(ast)
        return

    # ── Semantic analysis ─────────────────────────────────────
    try:
        SemanticAnalyzer(ast).analyze()
    except SemanticError as e:
        print(f"Semantic error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.check:
        print("OK — program is valid.")
        return

    # ── Execute ───────────────────────────────────────────────
    try:
        Interpreter(ast).run()
    except RuntimeError_ as e:
        print(f"Runtime error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)


def _print_ast(node, indent: int = 0):
    prefix = "  " * indent
    name   = type(node).__name__
    fields = {k: v for k, v in vars(node).items()
              if not k.startswith("_") and k not in ("line", "col")}
    print(f"{prefix}{name}")
    for k, v in fields.items():
        if isinstance(v, list):
            print(f"{prefix}  {k}:")
            for item in v:
                if hasattr(item, "__dict__"):
                    _print_ast(item, indent + 2)
                else:
                    print(f"{prefix}    {item!r}")
        elif hasattr(v, "__dict__"):
            print(f"{prefix}  {k}:")
            _print_ast(v, indent + 2)
        else:
            print(f"{prefix}  {k}: {v!r}")


if __name__ == "__main__":
    main()