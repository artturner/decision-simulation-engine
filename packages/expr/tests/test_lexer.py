"""
Lexer tests — 100 % coverage of every TokenType.
"""

import pytest
from expr.lexer import Lexer, LexError
from expr.tokens import Token, TokenType


def tokenize(text: str) -> list[Token]:
    return Lexer(text).tokenize()


def types(text: str) -> list[TokenType]:
    return [t.type for t in tokenize(text)]


# ---------------------------------------------------------------------------
# Individual operator tokens
# ---------------------------------------------------------------------------


class TestOperators:
    def test_and(self):
        assert tokenize("&&")[0] == Token(TokenType.AND)

    def test_or(self):
        assert tokenize("||")[0] == Token(TokenType.OR)

    def test_not(self):
        assert tokenize("!")[0] == Token(TokenType.NOT)

    def test_eq(self):
        assert tokenize("==")[0] == Token(TokenType.EQ)

    def test_neq(self):
        assert tokenize("!=")[0] == Token(TokenType.NEQ)

    def test_lt(self):
        assert tokenize("<")[0] == Token(TokenType.LT)

    def test_lte(self):
        assert tokenize("<=")[0] == Token(TokenType.LTE)

    def test_gt(self):
        assert tokenize(">")[0] == Token(TokenType.GT)

    def test_gte(self):
        assert tokenize(">=")[0] == Token(TokenType.GTE)

    def test_lparen(self):
        assert tokenize("(")[0] == Token(TokenType.LPAREN)

    def test_rparen(self):
        assert tokenize(")")[0] == Token(TokenType.RPAREN)


# ---------------------------------------------------------------------------
# Number literals
# ---------------------------------------------------------------------------


class TestNumbers:
    def test_positive_integer(self):
        assert tokenize("42")[0] == Token(TokenType.NUMBER, 42)

    def test_zero(self):
        assert tokenize("0")[0] == Token(TokenType.NUMBER, 0)

    def test_negative_integer(self):
        assert tokenize("-2")[0] == Token(TokenType.NUMBER, -2)

    def test_positive_float(self):
        assert tokenize("3.14")[0] == Token(TokenType.NUMBER, 3.14)

    def test_negative_float(self):
        assert tokenize("-1.5")[0] == Token(TokenType.NUMBER, -1.5)

    def test_number_value_is_int_not_float(self):
        tok = tokenize("5")[0]
        assert isinstance(tok.value, int)

    def test_number_value_is_float_when_decimal(self):
        tok = tokenize("5.0")[0]
        assert isinstance(tok.value, float)


# ---------------------------------------------------------------------------
# Boolean literals
# ---------------------------------------------------------------------------


class TestBooleans:
    def test_true(self):
        assert tokenize("true")[0] == Token(TokenType.BOOLEAN, True)

    def test_false(self):
        assert tokenize("false")[0] == Token(TokenType.BOOLEAN, False)

    def test_true_value_is_bool(self):
        assert tokenize("true")[0].value is True

    def test_false_value_is_bool(self):
        assert tokenize("false")[0].value is False


# ---------------------------------------------------------------------------
# Identifiers
# ---------------------------------------------------------------------------


class TestIdentifiers:
    def test_simple(self):
        assert tokenize("confidence")[0] == Token(TokenType.IDENTIFIER, "confidence")

    def test_camel_case(self):
        assert tokenize("LargeStateFavor")[0] == Token(
            TokenType.IDENTIFIER, "LargeStateFavor"
        )

    def test_underscore(self):
        assert tokenize("my_var")[0] == Token(TokenType.IDENTIFIER, "my_var")

    def test_alphanumeric(self):
        assert tokenize("var1")[0] == Token(TokenType.IDENTIFIER, "var1")

    def test_leading_underscore(self):
        assert tokenize("_private")[0] == Token(TokenType.IDENTIFIER, "_private")

    def test_not_confused_with_true_prefix(self):
        # 'trueish' is an identifier, not a boolean
        assert tokenize("trueish")[0] == Token(TokenType.IDENTIFIER, "trueish")

    def test_not_confused_with_false_prefix(self):
        assert tokenize("falsehood")[0] == Token(TokenType.IDENTIFIER, "falsehood")


# ---------------------------------------------------------------------------
# EOF
# ---------------------------------------------------------------------------


class TestEOF:
    def test_empty_string(self):
        assert tokenize("") == [Token(TokenType.EOF)]

    def test_whitespace_only(self):
        assert tokenize("   \t\n") == [Token(TokenType.EOF)]

    def test_eof_always_last(self):
        toks = tokenize("a")
        assert toks[-1].type == TokenType.EOF


# ---------------------------------------------------------------------------
# Multi-token expressions (README examples)
# ---------------------------------------------------------------------------


class TestExpressions:
    def test_large_state_favor_gte_negative(self):
        """LargeStateFavor >= -2  →  IDENTIFIER GTE NUMBER(-2) EOF"""
        toks = tokenize("LargeStateFavor >= -2")
        assert toks == [
            Token(TokenType.IDENTIFIER, "LargeStateFavor"),
            Token(TokenType.GTE),
            Token(TokenType.NUMBER, -2),
            Token(TokenType.EOF),
        ]

    def test_compound_with_and(self):
        """confidence >= 2 && risk < 1"""
        toks = tokenize("confidence >= 2 && risk < 1")
        assert toks == [
            Token(TokenType.IDENTIFIER, "confidence"),
            Token(TokenType.GTE),
            Token(TokenType.NUMBER, 2),
            Token(TokenType.AND),
            Token(TokenType.IDENTIFIER, "risk"),
            Token(TokenType.LT),
            Token(TokenType.NUMBER, 1),
            Token(TokenType.EOF),
        ]

    def test_full_readme_expression(self):
        """Full expression from README with four variables."""
        expr = (
            "LargeStateFavor >= -2 && LargeStateFavor <= 2 "
            "&& SouthernStateFavor >= -2 && SouthernStateFavor <= 2"
        )
        toks = tokenize(expr)
        tt = [t.type for t in toks]
        assert tt.count(TokenType.IDENTIFIER) == 4
        assert tt.count(TokenType.AND) == 3
        assert tt.count(TokenType.GTE) == 2
        assert tt.count(TokenType.LTE) == 2
        assert tt.count(TokenType.NUMBER) == 4

    def test_or_expression(self):
        """LargeStateFavor > 3 || LargeStateFavor < -3"""
        toks = tokenize("LargeStateFavor > 3 || LargeStateFavor < -3")
        tt = [t.type for t in toks]
        assert tt.count(TokenType.OR) == 1
        assert tt.count(TokenType.GT) == 1
        assert tt.count(TokenType.LT) == 1

    def test_not_identifier(self):
        """!flag  →  NOT IDENTIFIER"""
        toks = tokenize("!flag")
        assert toks[0] == Token(TokenType.NOT)
        assert toks[1] == Token(TokenType.IDENTIFIER, "flag")

    def test_parenthesized_expression(self):
        """(a || b) && c"""
        toks = tokenize("(a || b) && c")
        assert toks[0].type == TokenType.LPAREN
        assert toks[2].type == TokenType.OR
        assert toks[4].type == TokenType.RPAREN
        assert toks[5].type == TokenType.AND

    def test_equality(self):
        toks = tokenize("x == 1")
        assert toks[1].type == TokenType.EQ

    def test_inequality(self):
        toks = tokenize("x != 0")
        assert toks[1].type == TokenType.NEQ

    def test_boolean_in_expression(self):
        toks = tokenize("flag == true")
        assert toks[2] == Token(TokenType.BOOLEAN, True)

    def test_whitespace_variants(self):
        """Tabs and multiple spaces are both stripped."""
        a = tokenize("a  &&  b")
        b = tokenize("a\t&&\tb")
        assert [t.type for t in a] == [t.type for t in b]


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrors:
    def test_invalid_character(self):
        with pytest.raises(LexError):
            tokenize("@var")

    def test_single_ampersand(self):
        with pytest.raises(LexError):
            tokenize("&")

    def test_single_pipe(self):
        with pytest.raises(LexError):
            tokenize("|")

    def test_single_equals(self):
        with pytest.raises(LexError):
            tokenize("=")

    def test_stray_minus(self):
        """'-' not followed by a digit is not valid in this grammar."""
        with pytest.raises(LexError):
            tokenize("-")

    def test_hash(self):
        with pytest.raises(LexError):
            tokenize("# comment")

    def test_dollar(self):
        with pytest.raises(LexError):
            tokenize("$var")
