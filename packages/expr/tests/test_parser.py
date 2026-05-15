"""
Parser tests.

Covers every grammar rule, operator precedence, parenthesis grouping,
left-associativity, and error paths.
"""

import pytest

from expr.ast_nodes import BinaryOp, Literal, UnaryOp, Variable
from expr.parser import ParseError, parse
from expr.tokens import TokenType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def T(name: str) -> TokenType:
    return TokenType[name]


# ---------------------------------------------------------------------------
# Primary expressions
# ---------------------------------------------------------------------------


class TestPrimary:
    def test_integer_literal(self):
        assert parse("42") == Literal(42)

    def test_negative_integer(self):
        assert parse("-2") == Literal(-2)

    def test_float_literal(self):
        assert parse("3.14") == Literal(3.14)

    def test_boolean_true(self):
        assert parse("true") == Literal(True)

    def test_boolean_false(self):
        assert parse("false") == Literal(False)

    def test_variable(self):
        assert parse("LargeStateFavor") == Variable("LargeStateFavor")

    def test_underscore_variable(self):
        assert parse("my_var") == Variable("my_var")


# ---------------------------------------------------------------------------
# Unary NOT
# ---------------------------------------------------------------------------


class TestUnary:
    def test_not_variable(self):
        assert parse("!flag") == UnaryOp(T("NOT"), Variable("flag"))

    def test_not_literal(self):
        assert parse("!true") == UnaryOp(T("NOT"), Literal(True))

    def test_double_not(self):
        assert parse("!!x") == UnaryOp(T("NOT"), UnaryOp(T("NOT"), Variable("x")))

    def test_not_paren_group(self):
        result = parse("!(a || b)")
        assert isinstance(result, UnaryOp)
        assert result.operator == T("NOT")
        assert isinstance(result.operand, BinaryOp)


# ---------------------------------------------------------------------------
# Comparison operators
# ---------------------------------------------------------------------------


class TestComparison:
    def test_lt(self):
        assert parse("a < 1") == BinaryOp(Variable("a"), T("LT"), Literal(1))

    def test_lte(self):
        assert parse("a <= 1") == BinaryOp(Variable("a"), T("LTE"), Literal(1))

    def test_gt(self):
        assert parse("a > 1") == BinaryOp(Variable("a"), T("GT"), Literal(1))

    def test_gte(self):
        assert parse("score >= -2") == BinaryOp(Variable("score"), T("GTE"), Literal(-2))

    def test_comparison_left_associative(self):
        # a < b < c  →  (a < b) < c  (left-assoc, per grammar)
        result = parse("a < b < 1")
        assert isinstance(result, BinaryOp)
        assert result.operator == T("LT")
        assert isinstance(result.left, BinaryOp)
        assert result.right == Literal(1)


# ---------------------------------------------------------------------------
# Equality operators
# ---------------------------------------------------------------------------


class TestEquality:
    def test_eq(self):
        assert parse("x == 1") == BinaryOp(Variable("x"), T("EQ"), Literal(1))

    def test_neq(self):
        assert parse("x != 0") == BinaryOp(Variable("x"), T("NEQ"), Literal(0))

    def test_eq_boolean(self):
        assert parse("flag == true") == BinaryOp(Variable("flag"), T("EQ"), Literal(True))


# ---------------------------------------------------------------------------
# AND expressions
# ---------------------------------------------------------------------------


class TestAnd:
    def test_simple(self):
        assert parse("a && b") == BinaryOp(Variable("a"), T("AND"), Variable("b"))

    def test_left_associative(self):
        # a && b && c  →  (a && b) && c
        result = parse("a && b && c")
        assert isinstance(result, BinaryOp)
        assert result.operator == T("AND")
        assert isinstance(result.left, BinaryOp)   # (a && b)
        assert result.left.operator == T("AND")
        assert result.right == Variable("c")

    def test_with_comparisons(self):
        # Prompt spec: LargeStateFavor >= -2 && SouthernStateFavor <= 2
        result = parse("LargeStateFavor >= -2 && SouthernStateFavor <= 2")
        expected = BinaryOp(
            BinaryOp(Variable("LargeStateFavor"), T("GTE"), Literal(-2)),
            T("AND"),
            BinaryOp(Variable("SouthernStateFavor"), T("LTE"), Literal(2)),
        )
        assert result == expected


# ---------------------------------------------------------------------------
# OR expressions
# ---------------------------------------------------------------------------


class TestOr:
    def test_simple(self):
        assert parse("a || b") == BinaryOp(Variable("a"), T("OR"), Variable("b"))

    def test_left_associative(self):
        # a || b || c  →  (a || b) || c
        result = parse("a || b || c")
        assert isinstance(result, BinaryOp)
        assert result.operator == T("OR")
        assert isinstance(result.left, BinaryOp)
        assert result.right == Variable("c")


# ---------------------------------------------------------------------------
# Operator precedence (without parentheses)
# ---------------------------------------------------------------------------


class TestPrecedence:
    def test_and_binds_tighter_than_or(self):
        # a || b && c  →  a || (b && c)
        result = parse("a || b && c")
        assert isinstance(result, BinaryOp)
        assert result.operator == T("OR")
        assert result.left == Variable("a")
        assert result.right == BinaryOp(Variable("b"), T("AND"), Variable("c"))

    def test_comparison_binds_tighter_than_and(self):
        # a < 2 && b > 0  →  (a < 2) && (b > 0)
        result = parse("a < 2 && b > 0")
        assert result.operator == T("AND")
        assert result.left == BinaryOp(Variable("a"), T("LT"), Literal(2))
        assert result.right == BinaryOp(Variable("b"), T("GT"), Literal(0))

    def test_equality_binds_tighter_than_and(self):
        # x == 1 && y != 0  →  (x == 1) && (y != 0)
        result = parse("x == 1 && y != 0")
        assert result.operator == T("AND")
        assert result.left == BinaryOp(Variable("x"), T("EQ"), Literal(1))

    def test_not_binds_tighter_than_comparison(self):
        # !a && b  →  (!a) && b
        result = parse("!a && b")
        assert result.operator == T("AND")
        assert isinstance(result.left, UnaryOp)
        assert result.left.operator == T("NOT")

    def test_full_precedence_chain(self):
        # !a || b && c >= 1  →  (!a) || (b && (c >= 1))
        result = parse("!a || b && c >= 1")
        assert result.operator == T("OR")
        assert isinstance(result.left, UnaryOp)
        right = result.right
        assert right.operator == T("AND")  # type: ignore[union-attr]
        assert right.right == BinaryOp(Variable("c"), T("GTE"), Literal(1))  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Parentheses
# ---------------------------------------------------------------------------


class TestParentheses:
    def test_parens_override_precedence(self):
        # (a || b) && c  — OR is forced to bind tighter than AND
        result = parse("(a || b) && c")
        assert isinstance(result, BinaryOp)
        assert result.operator == T("AND")
        assert isinstance(result.left, BinaryOp)
        assert result.left.operator == T("OR")
        assert result.right == Variable("c")

    def test_parens_around_single_value(self):
        assert parse("(x)") == Variable("x")

    def test_nested_parens(self):
        assert parse("((x))") == Variable("x")

    def test_parens_both_sides_of_or(self):
        result = parse("(a && b) || (c && d)")
        assert result.operator == T("OR")
        assert result.left.operator == T("AND")   # type: ignore[union-attr]
        assert result.right.operator == T("AND")  # type: ignore[union-attr]

    def test_not_of_parens(self):
        result = parse("!(a && b)")
        assert isinstance(result, UnaryOp)
        assert isinstance(result.operand, BinaryOp)
        assert result.operand.operator == T("AND")


# ---------------------------------------------------------------------------
# README examples (end-to-end)
# ---------------------------------------------------------------------------


class TestReadmeExamples:
    def test_four_variable_and_chain(self):
        """
        LargeStateFavor >= -2 && LargeStateFavor <= 2
        && SouthernStateFavor >= -2 && SouthernStateFavor <= 2
        """
        expr = (
            "LargeStateFavor >= -2 && LargeStateFavor <= 2 "
            "&& SouthernStateFavor >= -2 && SouthernStateFavor <= 2"
        )
        result = parse(expr)
        # Left-associative AND chain → root is AND, leftmost nesting
        assert isinstance(result, BinaryOp)
        assert result.operator == T("AND")
        # Rightmost comparison is SouthernStateFavor <= 2
        assert result.right == BinaryOp(
            Variable("SouthernStateFavor"), T("LTE"), Literal(2)
        )

    def test_or_extremes_expression(self):
        """
        LargeStateFavor > 3 || LargeStateFavor < -3 || SouthernStateFavor < -3
        """
        expr = "LargeStateFavor > 3 || LargeStateFavor < -3 || SouthernStateFavor < -3"
        result = parse(expr)
        assert isinstance(result, BinaryOp)
        assert result.operator == T("OR")
        # Left-associative: rightmost operand is SouthernStateFavor < -3
        assert result.right == BinaryOp(
            Variable("SouthernStateFavor"), T("LT"), Literal(-3)
        )


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


class TestErrors:
    def test_empty_expression(self):
        with pytest.raises(ParseError, match="empty"):
            parse("")

    def test_whitespace_only(self):
        with pytest.raises(ParseError, match="empty"):
            parse("   ")

    def test_unclosed_paren(self):
        with pytest.raises(ParseError):
            parse("(a && b")

    def test_empty_parens(self):
        with pytest.raises(ParseError):
            parse("()")

    def test_missing_right_operand_and(self):
        with pytest.raises(ParseError):
            parse("a &&")

    def test_missing_right_operand_or(self):
        with pytest.raises(ParseError):
            parse("a ||")

    def test_missing_right_operand_comparison(self):
        with pytest.raises(ParseError):
            parse("a >=")

    def test_extra_token_after_expr(self):
        with pytest.raises(ParseError):
            parse("a b")

    def test_extra_close_paren(self):
        with pytest.raises(ParseError):
            parse("a)")

    def test_operator_at_start(self):
        with pytest.raises(ParseError):
            parse("&& b")

    def test_bare_operator(self):
        with pytest.raises(ParseError):
            parse("&&")

    def test_double_operator(self):
        with pytest.raises(ParseError):
            parse("a && && b")
