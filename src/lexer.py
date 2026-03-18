"""
lexer.py - Tokenizer for the DataSync DSL
"""

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional


#  token types

class TokenType(Enum):
    #literals
    INTEGER     = auto()
    FLOAT       = auto()
    STRING      = auto()
    BOOLEAN     = auto()
    NULL        = auto()

    #identifiers
    IDENTIFIER  = auto()

    #keywords - source
    SOURCE      = auto()
    AS          = auto()
    API         = auto()
    CSV         = auto()
    JSON        = auto()
    XML         = auto()
    DATABASE    = auto()

    #keywords - HTTP
    GET         = auto()
    POST        = auto()
    PUT         = auto()
    DELETE      = auto()

    #keywords - auth
    BEARER      = auto()
    BASIC       = auto()
    API_KEY     = auto()

    # keywords - pipeline
    PIPELINE    = auto()
    FETCH       = auto()
    FROM        = auto()
    FILTER      = auto()
    WHERE       = auto()
    MAP         = auto()
    JOIN        = auto()
    ON          = auto()
    TYPE        = auto()
    INNER       = auto()
    LEFT        = auto()
    RIGHT       = auto()
    FULL        = auto()
    AGGREGATE   = auto()
    SORT        = auto()
    BY          = auto()
    ASC         = auto()
    DESC        = auto()
    LIMIT       = auto()

    #keywords - aggregate functions
    SUM         = auto()
    COUNT       = auto()
    AVG         = auto()
    MIN         = auto()
    MAX         = auto()

    #keywords - output
    OUTPUT      = auto()
    TO          = auto()
    STDOUT      = auto()

    #keywords - Conditions
    AND         = auto()
    OR          = auto()
    NOT         = auto()
    LIKE        = auto()
    IN          = auto()
    IS          = auto()
    TRUE        = auto()
    FALSE       = auto()

    #operators
    EQ          = auto()   # ==
    NEQ         = auto()   # !=
    LT          = auto()   # <
    LTE         = auto()   # <=
    GT          = auto()   # >
    GTE         = auto()   # >=
    ASSIGN      = auto()   # =
    PLUS        = auto()   # +
    MINUS       = auto()   # -
    STAR        = auto()   # *
    SLASH       = auto()   # /
    DOT         = auto()   # .
    COMMA       = auto()   # ,
    COLON       = auto()   # :
    LPAREN      = auto()   # (
    RPAREN      = auto()   # )
    LBRACE      = auto()   # {
    RBRACE      = auto()   # }

    #special
    EOF         = auto()



#keyword map

KEYWORDS: dict[str, TokenType] = {
    "SOURCE":    TokenType.SOURCE,
    "AS":        TokenType.AS,
    "API":       TokenType.API,
    "CSV":       TokenType.CSV,
    "JSON":      TokenType.JSON,
    "XML":       TokenType.XML,
    "DATABASE":  TokenType.DATABASE,
    "GET":       TokenType.GET,
    "POST":      TokenType.POST,
    "PUT":       TokenType.PUT,
    "DELETE":    TokenType.DELETE,
    "BEARER":    TokenType.BEARER,
    "BASIC":     TokenType.BASIC,
    "API_KEY":   TokenType.API_KEY,
    "PIPELINE":  TokenType.PIPELINE,
    "FETCH":     TokenType.FETCH,
    "FROM":      TokenType.FROM,
    "FILTER":    TokenType.FILTER,
    "WHERE":     TokenType.WHERE,
    "MAP":       TokenType.MAP,
    "JOIN":      TokenType.JOIN,
    "ON":        TokenType.ON,
    "TYPE":      TokenType.TYPE,
    "INNER":     TokenType.INNER,
    "LEFT":      TokenType.LEFT,
    "RIGHT":     TokenType.RIGHT,
    "FULL":      TokenType.FULL,
    "AGGREGATE": TokenType.AGGREGATE,
    "SORT":      TokenType.SORT,
    "BY":        TokenType.BY,
    "ASC":       TokenType.ASC,
    "DESC":      TokenType.DESC,
    "LIMIT":     TokenType.LIMIT,
    "SUM":       TokenType.SUM,
    "COUNT":     TokenType.COUNT,
    "AVG":       TokenType.AVG,
    "MIN":       TokenType.MIN,
    "MAX":       TokenType.MAX,
    "OUTPUT":    TokenType.OUTPUT,
    "TO":        TokenType.TO,
    "STDOUT":    TokenType.STDOUT,
    "AND":       TokenType.AND,
    "OR":        TokenType.OR,
    "NOT":       TokenType.NOT,
    "LIKE":      TokenType.LIKE,
    "IN":        TokenType.IN,
    "IS":        TokenType.IS,
    "NULL":      TokenType.NULL,
    "TRUE":      TokenType.TRUE,
    "FALSE":     TokenType.FALSE,
    "true":      TokenType.TRUE,
    "false":     TokenType.FALSE,
}



#token dataclass
@dataclass
class Token:
    type:    TokenType
    value:   str
    line:    int
    column:  int

    def __repr__(self) -> str:
        return f"Token({self.type.name}, {self.value!r}, line={self.line}, col={self.column})"


#lexerError

class LexerError(Exception):
    def __init__(self, message: str, line: int, column: int):
        super().__init__(f"[Lexer] Line {line}, Col {column}: {message}")
        self.line   = line
        self.column = column



#lexer

class Lexer:
    def __init__(self, source: str):
        self._source  = source
        self._pos     = 0
        self._line    = 1
        self._col     = 1
        self._tokens: List[Token] = []

    #public

    def tokenize(self) -> List[Token]:
        while not self._at_end():
            self._skip_whitespace_and_comments()
            if self._at_end():
                break
            tok = self._next_token()
            if tok:
                self._tokens.append(tok)
        self._tokens.append(Token(TokenType.EOF, "", self._line, self._col))
        return self._tokens

    #internal helpers

    def _at_end(self) -> bool:
        return self._pos >= len(self._source)

    def _peek(self, offset: int = 0) -> str:
        idx = self._pos + offset
        if idx >= len(self._source):
            return "\0"
        return self._source[idx]

    def _advance(self) -> str:
        ch = self._source[self._pos]
        self._pos += 1
        if ch == "\n":
            self._line += 1
            self._col   = 1
        else:
            self._col += 1
        return ch

    def _match(self, expected: str) -> bool:
        if self._at_end():
            return False
        if self._source[self._pos] != expected:
            return False
        self._advance()
        return True

    #skip whitespace and comments

    def _skip_whitespace_and_comments(self):
        while not self._at_end():
            ch = self._peek()
            if ch in (" ", "\t", "\r", "\n"):
                self._advance()
            elif ch == "#":          # line comment
                while not self._at_end() and self._peek() != "\n":
                    self._advance()
            else:
                break

    #dispatch

    def _next_token(self) -> Optional[Token]:
        line, col = self._line, self._col
        ch = self._advance()

        #two-char operators
        if ch == "=" and self._peek() == "=":
            self._advance(); return Token(TokenType.EQ,  "==", line, col)
        if ch == "!" and self._peek() == "=":
            self._advance(); return Token(TokenType.NEQ, "!=", line, col)
        if ch == "<" and self._peek() == "=":
            self._advance(); return Token(TokenType.LTE, "<=", line, col)
        if ch == ">" and self._peek() == "=":
            self._advance(); return Token(TokenType.GTE, ">=", line, col)

        #single-char operators & punctuation
        single = {
            "=": TokenType.ASSIGN, "+": TokenType.PLUS,
            "-": TokenType.MINUS,  "*": TokenType.STAR,
            "/": TokenType.SLASH,  ".": TokenType.DOT,
            ",": TokenType.COMMA,  ":": TokenType.COLON,
            "(": TokenType.LPAREN, ")": TokenType.RPAREN,
            "{": TokenType.LBRACE, "}": TokenType.RBRACE,
            "<": TokenType.LT,     ">": TokenType.GT,
        }
        if ch in single:
            return Token(single[ch], ch, line, col)

        #string literals
        if ch in ('"', "'"):
            return self._read_string(ch, line, col)

        #numbers
        if ch.isdigit():
            return self._read_number(ch, line, col)

        #identifiers / keywords
        if ch.isalpha() or ch == "_":
            return self._read_identifier(ch, line, col)

        raise LexerError(f"Unexpected character: {ch!r}", line, col)

    #string reader

    def _read_string(self, quote: str, line: int, col: int) -> Token:
        buf = []
        while not self._at_end() and self._peek() != quote:
            c = self._advance()
            if c == "\\" and not self._at_end():   # escape sequences
                esc = self._advance()
                buf.append({"n": "\n", "t": "\t", "r": "\r"}.get(esc, esc))
            else:
                buf.append(c)
        if self._at_end():
            raise LexerError("Unterminated string literal", line, col)
        self._advance()   # closing quote
        return Token(TokenType.STRING, "".join(buf), line, col)

    #number reader

    def _read_number(self, first: str, line: int, col: int) -> Token:
        buf = [first]
        is_float = False
        while not self._at_end() and self._peek().isdigit():
            buf.append(self._advance())
        if self._peek() == "." and self._peek(1).isdigit():
            is_float = True
            buf.append(self._advance())   # dot
            while not self._at_end() and self._peek().isdigit():
                buf.append(self._advance())
        text = "".join(buf)
        ttype = TokenType.FLOAT if is_float else TokenType.INTEGER
        return Token(ttype, text, line, col)

    #identifier / keyword reader

    def _read_identifier(self, first: str, line: int, col: int) -> Token:
        buf = [first]
        while not self._at_end() and (self._peek().isalnum() or self._peek() == "_"):
            buf.append(self._advance())
        text = "".join(buf)
        ttype = KEYWORDS.get(text, TokenType.IDENTIFIER)
        return Token(ttype, text, line, col)