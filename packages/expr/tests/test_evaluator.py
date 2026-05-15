"""
Evaluator tests.

Covers every operator via ``evaluate``, all README examples via
``safe_evaluate``, and the full range of fail-closed edge cases.
"""

import pytest

from expr.ast_nodes import BinaryOp, Literal, UnaryOp, Variable
from expr.evaluator import EvaluationError, evaluate, safe_evaluate
from expr.tokens import TokenType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def T(name: str) -> TokenType:
    return TokenType[name]


# ---------------------------------------------------------------------------
# evaluate — Literal
# ---------------------------------------------------------------------------


class TestEvaluateLiteral:
    def test_integer(self):
        assert evaluate(Literal(42), {}) == 42

    def test_negative_integer(self):
        assert evaluate(Literal(-2), {}) == -2

    def test_float(self):
        assert evaluate(Literal(3.14), {}) == pytest.approx(3.14)

    def test_bool_true(self):
        assert evaluate(Literal(True), {}) is True

    def test_bool_false(self):
        assert evaluate(Literal(False), {}) is False


# ---------------------------------------------------------------------------
# evaluate — Variable
# ---------------------------------------------------------------------------


class TestEvaluateVariable:
    def test_known_variable(self):
        assert evaluate(Variable("x"), {"x": 5}) == 5

    def test_float_variable(self):
        assert evaluate(Variable("rate"), {"rate": 0.5}) == pytest.approx(0.5)

    def test_bool_variable(self):
        assert evaluate(Variable("flag"), {"flag": True}) is True

    def test_unknown_variable_raises(self):
        with pytest.raises(KeyError, match="unknown_var"):
            evaluate(Variable("unknown_var"), {})

    def test_empty_variables_raises(self):
        with pytest.raises(KeyError):
            evaluate(Variable("x"), {})


# ---------------------------------------------------------------------------
# evaluate — UnaryOp (NOT)
# ---------------------------------------------------------------------------


class TestEvaluateUnaryOp:
    def test_not_true(self):
        assert evaluate(UnaryOp(T("NOT"), Literal(True)), {}) is False

    def test_not_false(self):
        assert evaluate(UnaryOp(T("NOT"), Literal(False)), {}) is True

    def test_not_nonzero_is_false(self):
        # not 5 → False  (5 is truthy)
        assert evaluate(UnaryOp(T("NOT"), Literal(5)), {}) is False

    def test_not_zero_is_true(self):
        # not 0 → True  (0 is falsy)
        assert evaluate(UnaryOp(T("NOT"), Literal(0)), {}) is True

    def test_double_not(self):
        inner = UnaryOp(T("NOT"), Literal(True))
        outer = UnaryOp(T("NOT"), inner)
        assert evaluate(outer, {}) is True

    def test_not_variable(self):
        assert evaluate(UnaryOp(T("NOT"), Variable("flag")), {"flag": False}) is True


# ---------------------------------------------------------------------------
# evaluate — BinaryOp comparisons
# ---------------------------------------------------------------------------


class TestEvaluateComparisons:
    VARS: dict[str, int | float | bool] = {"a": 3, "b": -1, "z": 0}

    def test_lt_true(self):
        assert evaluate(BinaryOp(Literal(1), T("LT"), Literal(2)), {}) is True

    def test_lt_false(self):
        assert evaluate(BinaryOp(Literal(2), T("LT"), Literal(2)), {}) is False

    def test_lte_equal(self):
        assert evaluate(BinaryOp(Literal(2), T("LTE"), Literal(2)), {}) is True

    def test_lte_less(self):
        assert evaluate(BinaryOp(Literal(1), T("LTE"), Literal(2)), {}) is True

    def test_lte_greater(self):
        assert evaluate(BinaryOp(Literal(3), T("LTE"), Literal(2)), {}) is False

    def test_gt_true(self):
        assert evaluate(BinaryOp(Literal(5), T("GT"), Literal(3)), {}) is True

    def test_gt_false(self):
        assert evaluate(BinaryOp(Literal(3), T("GT"), Literal(3)), {}) is False

    def test_gte_equal(self):
        assert evaluate(BinaryOp(Literal(3), T("GTE"), Literal(3)), {}) is True

    def test_gte_less(self):
        assert evaluate(BinaryOp(Literal(2), T("GTE"), Literal(3)), {}) is False

    def test_eq_equal(self):
        assert evaluate(BinaryOp(Literal(7), T("EQ"), Literal(7)), {}) is True

    def test_eq_unequal(self):
        assert evaluate(BinaryOp(Literal(7), T("EQ"), Literal(8)), {}) is False

    def test_neq_unequal(self):
        assert evaluate(BinaryOp(Literal(1), T("NEQ"), Literal(2)), {}) is True

    def test_neq_equal(self):
        assert evaluate(BinaryOp(Literal(1), T("NEQ"), Literal(1)), {}) is False

    def test_eq_bool(self):
        assert evaluate(BinaryOp(Literal(True), T("EQ"), Literal(True)), {}) is True

    def test_comparison_with_variable(self):
        node = BinaryOp(Variable("a"), T("GTE"), Literal(-2))
        assert evaluate(node, {"a": 0}) is True

    def test_comparison_with_negative_literal(self):
        node = BinaryOp(Variable("b"), T("LT"), Literal(0))
        assert evaluate(node, {"b": -1}) is True

    def test_float_comparison(self):
        node = BinaryOp(Variable("rate"), T("GT"), Literal(0.5))
        assert evaluate(node, {"rate": 0.75}) is True


# ---------------------------------------------------------------------------
# evaluate — BinaryOp logical AND / OR
# ---------------------------------------------------------------------------


class TestEvaluateLogical:
    def test_and_both_true(self):
        node = BinaryOp(Literal(True), T("AND"), Literal(True))
        assert evaluate(node, {}) is True

    def test_and_left_false(self):
        node = BinaryOp(Literal(False), T("AND"), Literal(True))
        assert evaluate(node, {}) is False

    def test_and_right_false(self):
        node = BinaryOp(Literal(True), T("AND"), Literal(False))
        assert evaluate(node, {}) is False

    def test_and_both_false(self):
        node = BinaryOp(Literal(False), T("AND"), Literal(False))
        assert evaluate(node, {}) is False

    def test_or_both_true(self):
        node = BinaryOp(Literal(True), T("OR"), Literal(True))
        assert evaluate(node, {}) is True

    def test_or_left_true(self):
        node = BinaryOp(Literal(True), T("OR"), Literal(False))
        assert evaluate(node, {}) is True

    def test_or_right_true(self):
        node = BinaryOp(Literal(False), T("OR"), Literal(True))
        assert evaluate(node, {}) is True

    def test_or_both_false(self):
        node = BinaryOp(Literal(False), T("OR"), Literal(False))
        assert evaluate(node, {}) is False

    def test_and_both_sides_evaluated(self):
        """Both sides always evaluated — exception on right propagates even
        when left is False."""
        node = BinaryOp(
            BinaryOp(Variable("a"), T("GT"), Literal(0)),
            T("AND"),
            BinaryOp(Variable("missing"), T("GT"), Literal(0)),
        )
        with pytest.raises(KeyError):
            evaluate(node, {"a": -1})  # left is False, right raises KeyError


# ---------------------------------------------------------------------------
# safe_evaluate — README examples
# ---------------------------------------------------------------------------


class TestSafeEvaluateReadmeExamples:
    def test_gte_negative_true(self):
        """LargeStateFavor >= -2 with value 0 → True"""
        assert safe_evaluate("LargeStateFavor >= -2", {"LargeStateFavor": 0}) is True

    def test_gte_negative_boundary_true(self):
        """LargeStateFavor >= -2 with value -2 → True (boundary)"""
        assert safe_evaluate("LargeStateFavor >= -2", {"LargeStateFavor": -2}) is True

    def test_gte_negative_false(self):
        """LargeStateFavor >= -2 with value -3 → False"""
        assert safe_evaluate("LargeStateFavor >= -2", {"LargeStateFavor": -3}) is False

    def test_or_extremes_false(self):
        """LargeStateFavor > 3 || LargeStateFavor < -3 with value 0 → False"""
        assert (
            safe_evaluate(
                "LargeStateFavor > 3 || LargeStateFavor < -3",
                {"LargeStateFavor": 0},
            )
            is False
        )

    def test_or_extremes_true_high(self):
        """LargeStateFavor > 3 || LargeStateFavor < -3 with value 4 → True"""
        assert (
            safe_evaluate(
                "LargeStateFavor > 3 || LargeStateFavor < -3",
                {"LargeStateFavor": 4},
            )
            is True
        )

    def test_or_extremes_true_low(self):
        """LargeStateFavor > 3 || LargeStateFavor < -3 with value -4 → True"""
        assert (
            safe_evaluate(
                "LargeStateFavor > 3 || LargeStateFavor < -3",
                {"LargeStateFavor": -4},
            )
            is True
        )

    def test_four_variable_and_chain_true(self):
        """All four within range → True"""
        expr = (
            "LargeStateFavor >= -2 && LargeStateFavor <= 2 "
            "&& SouthernStateFavor >= -2 && SouthernStateFavor <= 2"
        )
        variables = {"LargeStateFavor": 0, "SouthernStateFavor": 0}
        assert safe_evaluate(expr, variables) is True

    def test_four_variable_and_chain_false_on_first(self):
        """First variable out of range → False"""
        expr = (
            "LargeStateFavor >= -2 && LargeStateFavor <= 2 "
            "&& SouthernStateFavor >= -2 && SouthernStateFavor <= 2"
        )
        variables = {"LargeStateFavor": 5, "SouthernStateFavor": 0}
        assert safe_evaluate(expr, variables) is False

    def test_four_variable_and_chain_false_on_last(self):
        """Last variable out of range → False"""
        expr = (
            "LargeStateFavor >= -2 && LargeStateFavor <= 2 "
            "&& SouthernStateFavor >= -2 && SouthernStateFavor <= 2"
        )
        variables = {"LargeStateFavor": 0, "SouthernStateFavor": 3}
        assert safe_evaluate(expr, variables) is False


# ---------------------------------------------------------------------------
# safe_evaluate — fail-closed behaviour
# ---------------------------------------------------------------------------


class TestSafeEvaluateFailClosed:
    def test_unknown_variable_returns_false(self):
        assert safe_evaluate("unknown_var > 0", {}) is False

    def test_unknown_variable_in_and_returns_false(self):
        assert safe_evaluate("x > 0 && missing < 1", {"x": 1}) is False

    def test_malformed_expression_returns_false(self):
        assert safe_evaluate("not valid @@@", {}) is False

    def test_empty_expression_returns_false(self):
        assert safe_evaluate("", {}) is False

    def test_whitespace_only_returns_false(self):
        assert safe_evaluate("   ", {}) is False

    def test_parse_error_returns_false(self):
        assert safe_evaluate("a &&", {}) is False

    def test_unclosed_paren_returns_false(self):
        assert safe_evaluate("(a > 0", {"a": 1}) is False

    def test_invalid_character_returns_false(self):
        assert safe_evaluate("@var > 0", {}) is False

    def test_never_raises(self):
        """safe_evaluate must never propagate an exception."""
        bad_inputs = [
            ("", {}),
            ("@@@", {}),
            ("unknown > 0", {}),
            ("a &&", {"a": 1}),
            ("(unclosed", {"a": 1}),
        ]
        for expr, variables in bad_inputs:
            result = safe_evaluate(expr, variables)
            assert result is False, f"Expected False for {expr!r}, got {result!r}"

    def test_returns_bool_not_truthy_value(self):
        """safe_evaluate always returns a strict bool."""
        result = safe_evaluate("x >= 1", {"x": 5})
        assert result is True
        assert type(result) is bool

    def test_returns_false_not_zero(self):
        result = safe_evaluate("x >= 10", {"x": 5})
        assert result is False
        assert type(result) is bool


# ---------------------------------------------------------------------------
# safe_evaluate — boolean and NOT expressions
# ---------------------------------------------------------------------------


class TestSafeEvaluateBooleanOps:
    def test_not_true(self):
        assert safe_evaluate("!flag", {"flag": True}) is False

    def test_not_false(self):
        assert safe_evaluate("!flag", {"flag": False}) is True

    def test_eq_boolean_literal(self):
        assert safe_evaluate("flag == true", {"flag": True}) is True

    def test_neq_boolean_literal(self):
        assert safe_evaluate("flag != false", {"flag": True}) is True

    def test_boolean_literal_standalone_true(self):
        assert safe_evaluate("true", {}) is True

    def test_boolean_literal_standalone_false(self):
        assert safe_evaluate("false", {}) is False


# ---------------------------------------------------------------------------
# Public import surface
# ---------------------------------------------------------------------------


class TestPublicImports:
    def test_safe_evaluate_importable_from_expr(self):
        from expr import safe_evaluate as se  # noqa: F401

        assert callable(se)

    def test_parse_importable_from_expr(self):
        from expr import parse as p  # noqa: F401

        assert callable(p)
