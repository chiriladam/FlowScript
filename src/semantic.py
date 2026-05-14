"""
semantic.py — Semantic Analyzer for FlowScript DSL

Checks:
  - Every SOURCE used in FETCH/JOIN is declared
  - Every PIPELINE referenced in OUTPUT exists
  - No duplicate SOURCE or PIPELINE names
  - JOIN references a declared source
  - LIMIT count is positive
  - OUTPUT has a 'from' option
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from ast_nodes import (
    Program, SourceDecl, PipelineDecl, OutputDecl,
    FetchStep, FilterStep, MapStep, JoinStep,
    AggregateStep, SortStep, LimitStep, ASTNode,
)


class SemanticError(Exception):
    def __init__(self, message: str, node: ASTNode = None):
        loc = f" (line {node.line})" if node and getattr(node, 'line', 0) else ""
        super().__init__(f"[Semantic]{loc}: {message}")


class SemanticAnalyzer:
    """
    Walks the AST and performs semantic validation.

    Usage:
        SemanticAnalyzer(ast).analyze()   # raises SemanticError on failure
    """

    def __init__(self, program: Program):
        self._program = program
        self._sources:   dict[str, SourceDecl]   = {}
        self._pipelines: dict[str, PipelineDecl] = {}

    def analyze(self) -> None:
        # First pass: collect all declarations
        for stmt in self._program.statements:
            if isinstance(stmt, SourceDecl):
                if stmt.name in self._sources:
                    raise SemanticError(
                        f"Duplicate SOURCE name '{stmt.name}'", stmt
                    )
                self._sources[stmt.name] = stmt

            elif isinstance(stmt, PipelineDecl):
                if stmt.name in self._pipelines:
                    raise SemanticError(
                        f"Duplicate PIPELINE name '{stmt.name}'", stmt
                    )
                self._pipelines[stmt.name] = stmt

        # Second pass: validate references
        for stmt in self._program.statements:
            if isinstance(stmt, PipelineDecl):
                self._check_pipeline(stmt)
            elif isinstance(stmt, OutputDecl):
                self._check_output(stmt)

    def _check_pipeline(self, pipe: PipelineDecl) -> None:
        for step in pipe.steps:
            if isinstance(step, FetchStep):
                for src in step.sources:
                    if src not in self._sources:
                        raise SemanticError(
                            f"FETCH references undeclared SOURCE '{src}'", step
                        )

            elif isinstance(step, JoinStep):
                if step.source not in self._sources:
                    raise SemanticError(
                        f"JOIN references undeclared SOURCE '{step.source}'", step
                    )

            elif isinstance(step, LimitStep):
                if step.count <= 0:
                    raise SemanticError(
                        f"LIMIT must be a positive integer, got {step.count}", step
                    )

    def _check_output(self, out: OutputDecl) -> None:
        if "from" not in out.options:
            raise SemanticError(
                f"OUTPUT '{out.name}' is missing required option 'from'", out
            )
        pipeline_name = out.options["from"]
        if pipeline_name not in self._pipelines:
            raise SemanticError(
                f"OUTPUT references undeclared PIPELINE '{pipeline_name}'", out
            )


def analyze(program: Program) -> None:
    """Run semantic analysis on a parsed program. Raises SemanticError on failure."""
    SemanticAnalyzer(program).analyze()