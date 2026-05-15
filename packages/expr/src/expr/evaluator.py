"""
AST evaluator for the safe expression grammar.

``evaluate`` walks the tree recursively and returns a raw Python value.
It raises on unknown variables or unsupported nodes — callers that need
fail-closed behaviour should use ``safe_evaluate`` instead.

``safe_evaluate`` is the primary public API: it parses *and* evaluates in
one call, returning ``False`` on any exception (unknown variable, parse
error, lex error, type error, …).  No ``eval()`` is used anywhere.
"""

from expr.ast_nodes import BinaryOp, ExprNode, Literal, UnaryOp, Variable
from expr.parser import parse
from expr.tokens import TokenType

# Raw value type produced by the AST — always coerced to bool at the top level.
_Value = int | float | bool


class EvaluationError(Exception):
    """Raised for unsupported operators or unexpected node types."""


def evaluate(node: ExprNode, variables: dict[str, _Value]) -> _Value:
    """Recursively evaluate *node* against *variables*.

    Args:
        node:       Root (or sub-tree) of the expression AST.
        variables:  Mapping of variable name → current numeric/bool value.

    Returns:
        The raw Python value produced by the (sub-)expression.

    Raises:
        KeyError:         Variable name not present in *variables*.
        EvaluationError:  Unsupported operator or unknown node type.
        TypeError:        Comparison between incompatible types.
    """
    # --- Leaf nodes -------------------------------------------------------

    if isinstance(node, Literal):
        return node.value

    if isinstance(node, Variable):
        if node.name not in variables:
            raise KeyError(f"Unknown variable: {node.name!r}")
        return variables[node.name]

    # --- Unary NOT --------------------------------------------------------

    if isinstance(node, UnaryOp):
        if node.operator == TokenType.NOT:
            return not bool(evaluate(node.operand, variables))
        raise EvaluationError(f"Unsupported unary operator: {node.operator!r}")

    # --- Binary operators -------------------------------------------------

    if isinstance(node, BinaryOp):
        op = node.operator

        # Logical operators — evaluate both sides fully (fail-closed: any
        # exception on either side propagates up to safe_evaluate).
        if op == TokenType.AND:
            left_val = bool(evaluate(node.left, variables))
            right_val = bool(evaluate(node.right, variables))
            return left_val and right_val

        if op == TokenType.OR:
            left_val = bool(evaluate(node.left, variables))
            right_val = bool(evaluate(node.right, variables))
            return left_val or right_val

        # Comparison / equality — evaluate both sides then compare.
        lhs = evaluate(node.left, variables)
        rhs = evaluate(node.right, variables)

        if op == TokenType.EQ:
            return lhs == rhs
        if op == TokenType.NEQ:
            return lhs != rhs
        if op == TokenType.LT:
            return lhs < rhs  # type: ignore[operator]
        if op == TokenType.LTE:
            return lhs <= rhs  # type: ignore[operator]
        if op == TokenType.GT:
            return lhs > rhs  # type: ignore[operator]
        if op == TokenType.GTE:
            return lhs >= rhs  # type: ignore[operator]

        raise EvaluationError(f"Unsupported binary operator: {op!r}")

    raise EvaluationError(f"Unknown AST node type: {type(node).__name__!r}")


def safe_evaluate(expression_str: str, variables: dict[str, _Value]) -> bool:
    """Parse and evaluate *expression_str*, returning ``False`` on any error.

    Fail-closed semantics:
    - Malformed expression (lex / parse error) → ``False``
    - Unknown variable reference                → ``False``
    - Type error in comparison                  → ``False``
    - Any other exception                       → ``False``

    This is the function used by the engine's conditional-scene handler.
    """
    try:
        node = parse(expression_str)
        return bool(evaluate(node, variables))
    except Exception:
        return False
