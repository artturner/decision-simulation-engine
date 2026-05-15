from enum import Enum, auto
from dataclasses import dataclass


class TokenType(Enum):
    # Logical operators
    AND = auto()
    OR = auto()
    NOT = auto()
    # Comparison operators
    EQ = auto()
    NEQ = auto()
    LT = auto()
    LTE = auto()
    GT = auto()
    GTE = auto()
    # Grouping
    LPAREN = auto()
    RPAREN = auto()
    # Value types
    IDENTIFIER = auto()
    NUMBER = auto()
    BOOLEAN = auto()  # true / false literals
    # Sentinel
    EOF = auto()


@dataclass(frozen=True)
class Token:
    type: TokenType
    value: str | int | float | bool | None = None

    def __repr__(self) -> str:
        if self.value is not None:
            return f"Token({self.type.name}, {self.value!r})"
        return f"Token({self.type.name})"
