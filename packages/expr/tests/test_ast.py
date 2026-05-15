"""
AST node tests — instantiation, attribute access, repr content, immutability,
and recursive nesting.
"""

import pytest
from expr.ast_nodes import BinaryOp, ExprNode, Literal, UnaryOp, Variable
from expr.tokens import TokenType


# ---------------------------------------------------------------------------
# Literal
# ---------------------------------------------------------------------------


class TestLiteral:
    def test_integer_value(self):
        assert Literal(42).value == 42

    def test_float_value(self):
        assert Literal(3.14).value == 3.14

    def test_negative_integer(self):
        assert Literal(-2).value == -2

    def test_bool_true(self):
        assert Literal(True).value is True

    def test_bool_false(self):
        assert Literal(False).value is False

    def test_repr_integer(self):
        assert repr(Literal(42)) == "Literal(42)"

    def test_repr_float(self):
        assert repr(Literal(3.14)) == "Literal(3.14)"

    def test_repr_bool(self):
        assert repr(Literal(True)) == "Literal(True)"

    def test_repr_negative(self):
        assert repr(Literal(-2)) == "Literal(-2)"

    def test_equality(self):
        assert Literal(1) == Literal(1)
        assert Literal(1) != Literal(2)

    def test_immutable(self):
        node = Literal(1)
        with pytest.raises(AttributeError):
            node.value = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Variable
# ---------------------------------------------------------------------------


class TestVariable:
    def test_name(self):
        assert Variable("LargeStateFavor").name == "LargeStateFavor"

    def test_repr(self):
        assert repr(Variable("confidence")) == "Variable('confidence')"

    def test_repr_contains_name(self):
        r = repr(Variable("SouthernStateFavor"))
        assert "SouthernStateFavor" in r

    def test_equality(self):
        assert Variable("x") == Variable("x")
        assert Variable("x") != Variable("y")

    def test_immutable(self):
        node = Variable("x")
        with pytest.raises(AttributeError):
            node.name = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# UnaryOp
# ---------------------------------------------------------------------------


class TestUnaryOp:
    def test_operator(self):
        node = UnaryOp(TokenType.NOT, Variable("flag"))
        assert node.operator == TokenType.NOT

    def test_operand_variable(self):
        operand = Variable("flag")
        node = UnaryOp(TokenType.NOT, operand)
        assert node.operand == operand

    def test_operand_literal(self):
        node = UnaryOp(TokenType.NOT, Literal(True))
        assert node.operand == Literal(True)

    def test_repr_contains_not(self):
        r = repr(UnaryOp(TokenType.NOT, Variable("flag")))
        assert "NOT" in r

    def test_repr_contains_operand(self):
        r = repr(UnaryOp(TokenType.NOT, Variable("flag")))
        assert "flag" in r

    def test_repr_format(self):
        node = UnaryOp(TokenType.NOT, Variable("active"))
        assert repr(node) == "UnaryOp(NOT, Variable('active'))"

    def test_nested_unary(self):
        """UnaryOp can wrap another UnaryOp (double negation)."""
        inner = UnaryOp(TokenType.NOT, Variable("x"))
        outer = UnaryOp(TokenType.NOT, inner)
        assert isinstance(outer.operand, UnaryOp)

    def test_equality(self):
        a = UnaryOp(TokenType.NOT, Variable("x"))
        b = UnaryOp(TokenType.NOT, Variable("x"))
        assert a == b

    def test_immutable(self):
        node = UnaryOp(TokenType.NOT, Literal(True))
        with pytest.raises(AttributeError):
            node.operator = TokenType.AND  # type: ignore[misc]


# ---------------------------------------------------------------------------
# BinaryOp
# ---------------------------------------------------------------------------


class TestBinaryOp:
    def test_left(self):
        left = Variable("score")
        node = BinaryOp(left, TokenType.GTE, Literal(3))
        assert node.left == left

    def test_operator(self):
        node = BinaryOp(Variable("a"), TokenType.GTE, Literal(0))
        assert node.operator == TokenType.GTE

    def test_right(self):
        right = Literal(3)
        node = BinaryOp(Variable("score"), TokenType.GTE, right)
        assert node.right == right

    def test_repr_contains_operator_name(self):
        node = BinaryOp(Variable("a"), TokenType.AND, Variable("b"))
        assert "AND" in repr(node)

    def test_repr_contains_children(self):
        node = BinaryOp(Variable("score"), TokenType.GTE, Literal(3))
        r = repr(node)
        assert "score" in r
        assert "3" in r
        assert "GTE" in r

    def test_repr_format(self):
        node = BinaryOp(Variable("x"), TokenType.EQ, Literal(1))
        assert repr(node) == "BinaryOp(Variable('x'), EQ, Literal(1))"

    def test_nested_left(self):
        """BinaryOp can hold another BinaryOp as its left child."""
        inner = BinaryOp(Variable("a"), TokenType.GT, Literal(0))
        outer = BinaryOp(inner, TokenType.AND, BinaryOp(Variable("b"), TokenType.LT, Literal(10)))
        assert isinstance(outer.left, BinaryOp)
        assert outer.operator == TokenType.AND

    def test_nested_right(self):
        inner = BinaryOp(Variable("b"), TokenType.LT, Literal(10))
        outer = BinaryOp(Variable("a"), TokenType.OR, inner)
        assert isinstance(outer.right, BinaryOp)

    def test_all_comparison_operators(self):
        ops = [
            TokenType.EQ,
            TokenType.NEQ,
            TokenType.LT,
            TokenType.LTE,
            TokenType.GT,
            TokenType.GTE,
        ]
        for op in ops:
            node = BinaryOp(Variable("x"), op, Literal(0))
            assert node.operator == op
            assert op.name in repr(node)

    def test_equality(self):
        a = BinaryOp(Variable("x"), TokenType.EQ, Literal(1))
        b = BinaryOp(Variable("x"), TokenType.EQ, Literal(1))
        assert a == b

    def test_inequality_different_operator(self):
        a = BinaryOp(Variable("x"), TokenType.EQ, Literal(1))
        b = BinaryOp(Variable("x"), TokenType.NEQ, Literal(1))
        assert a != b

    def test_immutable(self):
        node = BinaryOp(Literal(1), TokenType.EQ, Literal(1))
        with pytest.raises(AttributeError):
            node.operator = TokenType.NEQ  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ExprNode type alias covers all four node types
# ---------------------------------------------------------------------------


class TestExprNodeAlias:
    def test_all_types_are_expr_nodes(self):
        nodes = [
            Literal(1),
            Variable("x"),
            UnaryOp(TokenType.NOT, Literal(True)),
            BinaryOp(Literal(1), TokenType.EQ, Literal(1)),
        ]
        for node in nodes:
            assert isinstance(node, (BinaryOp, UnaryOp, Literal, Variable))

    def test_deeply_nested_repr_is_readable(self):
        """Repr of a deeply nested tree should not raise and should contain key names."""
        tree = BinaryOp(
            BinaryOp(Variable("LargeStateFavor"), TokenType.GTE, Literal(-2)),
            TokenType.AND,
            BinaryOp(Variable("LargeStateFavor"), TokenType.LTE, Literal(2)),
        )
        r = repr(tree)
        assert "LargeStateFavor" in r
        assert "AND" in r
        assert "GTE" in r
        assert "LTE" in r
