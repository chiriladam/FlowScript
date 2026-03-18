"""
ast_nodes.py — abstract syntax tree node definitions for DataSync DSL
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional

#base node
class ASTNode:
    line: int = 0
    col:  int = 0


#program
@dataclass
class Program(ASTNode):
    statements: List[ASTNode] = field(default_factory=list)

#expressions
@dataclass
class Identifier(ASTNode):
    name: str

@dataclass
class FieldAccess(ASTNode):
    parts: List[str]

@dataclass
class StringLiteral(ASTNode):
    value: str

@dataclass
class NumberLiteral(ASTNode):
    value: float
    is_float: bool = False

@dataclass
class BooleanLiteral(ASTNode):
    value: bool

@dataclass
class NullLiteral(ASTNode):
    pass

@dataclass
class BinaryOp(ASTNode):
    left:     ASTNode
    operator: str
    right:    ASTNode

@dataclass
class UnaryOp(ASTNode):
    operator: str
    operand:  ASTNode

@dataclass
class FunctionCall(ASTNode):
    name: str
    args: List[ASTNode] = field(default_factory=list)


#conditions
@dataclass
class Comparison(ASTNode):
    left:     ASTNode
    operator: str
    right:    Optional[ASTNode]   #none for IS NULL / IS NOT NULL

@dataclass
class LogicalOp(ASTNode):
    left:     ASTNode
    operator: str
    right:    ASTNode

@dataclass
class NotOp(ASTNode):
    operand: ASTNode


#  Source declarations
@dataclass
class HeaderPair(ASTNode):
    key:   str
    value: str

@dataclass
class AuthExpr(ASTNode):
    method: str
    arg1:   str
    arg2:   Optional[str] = None

@dataclass
class SourceDecl(ASTNode):
    name:        str
    source_type: str
    options:     dict = field(default_factory=dict)


#  Pipeline steps
@dataclass
class FetchStep(ASTNode):
    sources: List[str] = field(default_factory=list)

@dataclass
class FilterStep(ASTNode):
    condition: ASTNode = field(default=None)

@dataclass
class FieldMapping(ASTNode):
    target: str = ""
    expr:   ASTNode = field(default=None)

@dataclass
class MapStep(ASTNode):
    mappings: List[FieldMapping] = field(default_factory=list)

@dataclass
class JoinStep(ASTNode):
    source:    str = ""
    left_key:  str = ""
    right_key: str = ""
    join_type: str = "INNER"

@dataclass
class AggRule(ASTNode):
    func:  str = ""
    field: str = ""
    alias: str = ""

@dataclass
class AggregateStep(ASTNode):
    rules: List[AggRule] = field(default_factory=list)

@dataclass
class SortKey(ASTNode):
    field:     str = ""
    direction: str = "ASC"

@dataclass
class SortStep(ASTNode):
    keys: List[SortKey] = field(default_factory=list)

@dataclass
class LimitStep(ASTNode):
    count: int = 0


#  Pipeline declaration
@dataclass
class PipelineDecl(ASTNode):
    name:  str = ""
    steps: List[ASTNode] = field(default_factory=list)

#  Output declaration
@dataclass
class OutputDecl(ASTNode):
    name:        str = ""
    output_type: str = ""
    options:     dict = field(default_factory=dict)