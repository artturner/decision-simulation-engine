"""
Recursive descent parser for the safe expression grammar.

Grammar (highest → lowest precedence)
--------------------------------------
expression  → or_expr
or_expr     → and_expr  ( OR  and_expr  )*
and_expr    → equality  ( AND equality  )*
equality    → comparison ( ( EQ | NEQ )  comparison )*
comparison  → unary     ( ( LT | LTE | GT | GTE ) unary )*
unary       → NOT unary | primary
primary     → NUMBER | BOOLEAN | IDENTIFIER | '(' expression ')'
"""

from expr.ast_nodes import BinaryOp, ExprNode, Literal, UnaryOp, Variable
from expr.lexer import Lexer
from expr.tokens import Token, TokenType


class ParseError(Exception):
    pass


class Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _current(self) -> Token:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return self.tokens[-1]  # safety: return EOF

    def _match(self, *types: TokenType) -> bool:
        return self._current().type in types

    def _consume(self, expected: TokenType | None = None) -> Token:
        tok = self._current()
        if expected is not None and tok.type != expected:
            detail = f" ({tok.value!r})" if tok.value is not None else ""
            raise ParseError(
                f"Expected {expected.name} but got {tok.type.name}{detail}"
            )
        self.pos += 1
        return tok

    # ------------------------------------------------------------------
    # Grammar rules
    # ------------------------------------------------------------------

    def parse(self) -> ExprNode:
        if self._match(TokenType.EOF):
            raise ParseError("Expression is empty")
        node = self._or_expr()
        if not self._match(TokenType.EOF):
            raise ParseError(
                f"Unexpected token {self._current()!r} after expression"
            )
        return node

    def _or_expr(self) -> ExprNode:
        left = self._and_expr()
        while self._match(TokenType.OR):
            self._consume()
            right = self._and_expr()
            left = BinaryOp(left, TokenType.OR, right)
        return left

    def _and_expr(self) -> ExprNode:
        left = self._equality()
        while self._match(TokenType.AND):
            self._consume()
            right = self._equality()
            left = BinaryOp(left, TokenType.AND, right)
        return left

    def _equality(self) -> ExprNode:
        left = self._comparison()
        while self._match(TokenType.EQ, TokenType.NEQ):
            op = self._consume().type
            right = self._comparison()
            left = BinaryOp(left, op, right)
        return left

    def _comparison(self) -> ExprNode:
        left = self._unary()
        while self._match(TokenType.LT, TokenType.LTE, TokenType.GT, TokenType.GTE):
            op = self._consume().type
            right = self._unary()
            left = BinaryOp(left, op, right)
        return left

    def _unary(self) -> ExprNode:
        if self._match(TokenType.NOT):
            self._consume()
            return UnaryOp(TokenType.NOT, self._unary())
        return self._primary()

    def _primary(self) -> ExprNode:
        tok = self._current()

        if tok.type == TokenType.NUMBER:
            self._consume()
            return Literal(tok.value)  # type: ignore[arg-type]

        if tok.type == TokenType.BOOLEAN:
            self._consume()
            return Literal(tok.value)  # type: ignore[arg-type]

        if tok.type == TokenType.IDENTIFIER:
            self._consume()
            return Variable(str(tok.value))

        if tok.type == TokenType.LPAREN:
            self._consume()  # consume '('
            node = self._or_expr()
            self._consume(TokenType.RPAREN)  # raises ParseError if missing
            return node

        if tok.type == TokenType.EOF:
            raise ParseError("Unexpected end of expression")

        raise ParseError(f"Unexpected token {tok!r} in expression")


# ---------------------------------------------------------------------------
# Module-level convenience function (exported from expr.__init__)
# ---------------------------------------------------------------------------


def parse(expression: str) -> ExprNode:
    """Lex and parse *expression*, returning the AST root node.

    Raises :class:`ParseError` (or :class:`~expr.lexer.LexError`) on invalid
    input; callers that want fail-closed behaviour should use
    ``expr.safe_evaluate`` instead.
    """
    tokens = Lexer(expression).tokenize()
    return Parser(tokens).parse()
