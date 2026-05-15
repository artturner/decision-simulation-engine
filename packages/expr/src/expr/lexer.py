from expr.tokens import Token, TokenType


class LexError(Exception):
    pass


class Lexer:
    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _current(self) -> str | None:
        return self.text[self.pos] if self.pos < len(self.text) else None

    def _peek(self) -> str | None:
        pos = self.pos + 1
        return self.text[pos] if pos < len(self.text) else None

    def _advance(self) -> str:
        ch = self.text[self.pos]
        self.pos += 1
        return ch

    def _skip_whitespace(self) -> None:
        while self._current() is not None and self._current().isspace():
            self.pos += 1

    def _read_identifier_or_boolean(self) -> Token:
        start = self.pos
        while self._current() is not None and (
            self._current().isalnum() or self._current() == "_"
        ):
            self._advance()
        word = self.text[start : self.pos]
        if word == "true":
            return Token(TokenType.BOOLEAN, True)
        if word == "false":
            return Token(TokenType.BOOLEAN, False)
        return Token(TokenType.IDENTIFIER, word)

    def _read_number(self) -> Token:
        """Read an integer or float, optionally starting with '-'."""
        start = self.pos
        if self._current() == "-":
            self._advance()
        # Integer part
        while self._current() is not None and self._current().isdigit():
            self._advance()
        # Optional fractional part
        if self._current() == "." and self._peek() is not None and self._peek().isdigit():
            self._advance()  # consume '.'
            while self._current() is not None and self._current().isdigit():
                self._advance()
        raw = self.text[start : self.pos]
        value: int | float = float(raw) if "." in raw else int(raw)
        return Token(TokenType.NUMBER, value)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def next_token(self) -> Token:
        self._skip_whitespace()
        ch = self._current()

        if ch is None:
            return Token(TokenType.EOF)

        # Identifiers and boolean keywords
        if ch.isalpha() or ch == "_":
            return self._read_identifier_or_boolean()

        # Positive numbers
        if ch.isdigit():
            return self._read_number()

        # Negative numbers: '-' immediately followed by a digit
        if ch == "-" and self._peek() is not None and self._peek().isdigit():
            return self._read_number()

        # '&&'
        if ch == "&":
            if self._peek() == "&":
                self.pos += 2
                return Token(TokenType.AND)
            raise LexError(
                f"Unexpected character '&' at position {self.pos}: expected '&&'"
            )

        # '||'
        if ch == "|":
            if self._peek() == "|":
                self.pos += 2
                return Token(TokenType.OR)
            raise LexError(
                f"Unexpected character '|' at position {self.pos}: expected '||'"
            )

        # '!' or '!='
        if ch == "!":
            if self._peek() == "=":
                self.pos += 2
                return Token(TokenType.NEQ)
            self.pos += 1
            return Token(TokenType.NOT)

        # '=='
        if ch == "=":
            if self._peek() == "=":
                self.pos += 2
                return Token(TokenType.EQ)
            raise LexError(
                f"Unexpected character '=' at position {self.pos}: expected '=='"
            )

        # '<' or '<='
        if ch == "<":
            if self._peek() == "=":
                self.pos += 2
                return Token(TokenType.LTE)
            self.pos += 1
            return Token(TokenType.LT)

        # '>' or '>='
        if ch == ">":
            if self._peek() == "=":
                self.pos += 2
                return Token(TokenType.GTE)
            self.pos += 1
            return Token(TokenType.GT)

        if ch == "(":
            self.pos += 1
            return Token(TokenType.LPAREN)

        if ch == ")":
            self.pos += 1
            return Token(TokenType.RPAREN)

        raise LexError(f"Unexpected character {ch!r} at position {self.pos}")

    def tokenize(self) -> list[Token]:
        """Consume the entire input and return all tokens including EOF."""
        tokens: list[Token] = []
        while True:
            tok = self.next_token()
            tokens.append(tok)
            if tok.type == TokenType.EOF:
                break
        return tokens
