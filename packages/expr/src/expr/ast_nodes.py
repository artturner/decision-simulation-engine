"""
AST node types for the safe expression parser.

All nodes are immutable (frozen dataclasses) — they are built once during
parsing and never mutated.  The evaluator walks the tree recursively.

Node hierarchy
--------------
ExprNode = BinaryOp | UnaryOp | Literal | Variable

Operator tokens stored on nodes come from TokenType so that the evaluator
can switch on the same enum used by the lexer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from expr.tokens import TokenType


@dataclass(frozen=True)
class Literal:
    """A numeric or boolean constant (e.g. ``-2``, ``3.14``, ``true``)."""

    value: int | float | bool

    def __repr__(self) -> str:
        return f"Literal({self.value!r})"


@dataclass(frozen=True)
class Variable:
    """A reference to a named scenario variable (e.g. ``LargeStateFavor``)."""

    name: str

    def __repr__(self) -> str:
        return f"Variable({self.name!r})"


@dataclass(frozen=True)
class UnaryOp:
    """A unary operation — currently only ``NOT`` (``!``)."""

    operator: TokenType
    operand: ExprNode

    def __repr__(self) -> str:
        return f"UnaryOp({self.operator.name}, {self.operand!r})"


@dataclass(frozen=True)
class BinaryOp:
    """A binary operation: comparisons (``==``, ``!=``, ``<``, …) or logical (``&&``, ``||``)."""

    left: ExprNode
    operator: TokenType
    right: ExprNode

    def __repr__(self) -> str:
        return f"BinaryOp({self.left!r}, {self.operator.name}, {self.right!r})"


# Type alias used for annotations in the parser and evaluator.
# Defined after the classes so all four names are in scope.
ExprNode = Union[BinaryOp, UnaryOp, Literal, Variable]
