"""parser.py - recursive-descent parser for the DataSync DSL"""

from __future__ import annotations
from typing import List, Optional

from lexer import Lexer, Token, TokenType
from ast_nodes import *


#parse error

class ParseError(Exception):
    def __init__(self, message: str, token: Token):
        super().__init__(
            f"[Parser] Line {token.line}, Col {token.column}: {message} "
            f"(got {token.type.name} {token.value!r})"
        )
        self.token = token


#parser

class Parser:
    """recursive-descent parser, builds an AST from a token list

    usage:
        tokens = Lexer(source_code).tokenize()
        ast    = Parser(tokens).parse()
    """

    def __init__(self, tokens: List[Token]):
        self._tokens  = tokens
        self._pos     = 0

    #helpers

    def _peek(self, offset: int = 0) -> Token:
        idx = self._pos + offset
        if idx >= len(self._tokens):
            return self._tokens[-1]   #eof
        return self._tokens[idx]

    def _current(self) -> Token:
        return self._peek(0)

    def _advance(self) -> Token:
        tok = self._current()
        if tok.type != TokenType.EOF:
            self._pos += 1
        return tok

    def _check(self, *types: TokenType) -> bool:
        return self._current().type in types

    def _match(self, *types: TokenType) -> Optional[Token]:
        if self._check(*types):
            return self._advance()
        return None

    def _expect(self, ttype: TokenType, msg: str = "") -> Token:
        if self._check(ttype):
            return self._advance()
        tok = self._current()
        raise ParseError(msg or f"Expected {ttype.name}", tok)

    def _loc(self) -> tuple[int, int]:
        t = self._current()
        return t.line, t.column

    #entry point

    def parse(self) -> Program:
        line, col = self._loc()
        stmts: List[ASTNode] = []
        while not self._check(TokenType.EOF):
            stmts.append(self._statement())
        node = Program(statements=stmts)
        node.line, node.col = line, col
        return node

    #statements

    def _statement(self) -> ASTNode:
        if self._check(TokenType.SOURCE):
            return self._source_decl()
        if self._check(TokenType.PIPELINE):
            return self._pipeline_decl()
        if self._check(TokenType.OUTPUT):
            return self._output_decl()
        raise ParseError("Expected SOURCE, PIPELINE, or OUTPUT", self._current())

    #source declaration

    def _source_decl(self) -> SourceDecl:
        line, col = self._loc()
        self._expect(TokenType.SOURCE)
        name = self._expect(TokenType.IDENTIFIER, "Expected source name").value
        self._expect(TokenType.AS, "Expected AS after source name")

        stype = self._source_type()

        self._expect(TokenType.LBRACE, "Expected '{' to open source body")
        options = self._source_body()
        self._expect(TokenType.RBRACE, "Expected '}' to close source body")

        node = SourceDecl(name=name, source_type=stype, options=options)
        node.line, node.col = line, col
        return node

    def _source_type(self) -> str:
        valid = (
            TokenType.API, TokenType.CSV, TokenType.JSON,
            TokenType.XML, TokenType.DATABASE
        )
        tok = self._current()
        if tok.type in valid:
            self._advance()
            return tok.value
        raise ParseError("Expected source type (API, CSV, JSON, XML, DATABASE)", tok)

    def _source_body(self) -> dict:
        options: dict = {}
        OPTION_KEYS = {
            "url", "path", "method", "headers", "auth",
            "query", "table", "encoding"
        }
        while not self._check(TokenType.RBRACE, TokenType.EOF):
            key_tok = self._expect(TokenType.IDENTIFIER, "Expected option name")
            key = key_tok.value
            if key not in OPTION_KEYS:
                raise ParseError(f"Unknown source option '{key}'", key_tok)
            self._expect(TokenType.ASSIGN, f"Expected '=' after '{key}'")

            if key == "headers":
                options[key] = self._header_dict()
            elif key == "auth":
                options[key] = self._auth_expr()
            elif key == "method":
                options[key] = self._http_method()
            else:
                options[key] = self._expect(TokenType.STRING,
                                             f"Expected string value for '{key}'").value
        return options

    def _http_method(self) -> str:
        valid = (TokenType.GET, TokenType.POST, TokenType.PUT, TokenType.DELETE)
        tok = self._current()
        if tok.type in valid:
            self._advance()
            return tok.value
        raise ParseError("Expected HTTP method (GET, POST, PUT, DELETE)", tok)

    def _header_dict(self) -> List[HeaderPair]:
        line, col = self._loc()
        self._expect(TokenType.LBRACE, "Expected '{' for headers")
        pairs: List[HeaderPair] = []
        while not self._check(TokenType.RBRACE, TokenType.EOF):
            k = self._expect(TokenType.STRING, "Expected header key (string)").value
            self._expect(TokenType.COLON, "Expected ':' between header key and value")
            v = self._expect(TokenType.STRING, "Expected header value (string)").value
            hp = HeaderPair(key=k, value=v)
            hp.line, hp.col = line, col
            pairs.append(hp)
            self._match(TokenType.COMMA)
        self._expect(TokenType.RBRACE, "Expected '}' to close headers")
        return pairs

    def _auth_expr(self) -> AuthExpr:
        line, col = self._loc()
        tok = self._current()
        if tok.type == TokenType.BEARER:
            self._advance()
            token_val = self._expect(TokenType.STRING, "Expected token for BEARER").value
            node = AuthExpr(method="BEARER", arg1=token_val)
        elif tok.type == TokenType.BASIC:
            self._advance()
            user = self._expect(TokenType.STRING, "Expected username for BASIC").value
            pw   = self._expect(TokenType.STRING, "Expected password for BASIC").value
            node = AuthExpr(method="BASIC", arg1=user, arg2=pw)
        elif tok.type == TokenType.API_KEY:
            self._advance()
            param = self._expect(TokenType.STRING, "Expected param name for API_KEY").value
            val   = self._expect(TokenType.STRING, "Expected value for API_KEY").value
            node  = AuthExpr(method="API_KEY", arg1=param, arg2=val)
        else:
            raise ParseError("Expected BEARER, BASIC, or API_KEY", tok)
        node.line, node.col = line, col
        return node

    #pipeline declaration

    def _pipeline_decl(self) -> PipelineDecl:
        line, col = self._loc()
        self._expect(TokenType.PIPELINE)
        name = self._expect(TokenType.IDENTIFIER, "Expected pipeline name").value
        self._expect(TokenType.LBRACE, "Expected '{' to open pipeline")
        steps: List[ASTNode] = []
        while not self._check(TokenType.RBRACE, TokenType.EOF):
            steps.append(self._pipeline_step())
        self._expect(TokenType.RBRACE, "Expected '}' to close pipeline")
        node = PipelineDecl(name=name, steps=steps)
        node.line, node.col = line, col
        return node

    def _pipeline_step(self) -> ASTNode:
        tok = self._current()
        if tok.type == TokenType.FETCH:     return self._fetch_step()
        if tok.type == TokenType.FILTER:    return self._filter_step()
        if tok.type == TokenType.MAP:       return self._map_step()
        if tok.type == TokenType.JOIN:      return self._join_step()
        if tok.type == TokenType.AGGREGATE: return self._aggregate_step()
        if tok.type == TokenType.SORT:      return self._sort_step()
        if tok.type == TokenType.LIMIT:     return self._limit_step()
        raise ParseError("Expected pipeline step keyword "
                         "(FETCH, FILTER, MAP, JOIN, AGGREGATE, SORT, LIMIT)", tok)

    def _fetch_step(self) -> FetchStep:
        line, col = self._loc()
        self._expect(TokenType.FETCH)
        self._expect(TokenType.FROM, "Expected FROM after FETCH")
        sources = [self._expect(TokenType.IDENTIFIER, "Expected source name").value]
        while self._match(TokenType.COMMA):
            sources.append(self._expect(TokenType.IDENTIFIER, "Expected source name").value)
        node = FetchStep(sources=sources)
        node.line, node.col = line, col
        return node

    def _filter_step(self) -> FilterStep:
        line, col = self._loc()
        self._expect(TokenType.FILTER)
        self._expect(TokenType.WHERE, "Expected WHERE after FILTER")
        cond = self._condition()
        node = FilterStep(condition=cond)
        node.line, node.col = line, col
        return node

    def _map_step(self) -> MapStep:
        line, col = self._loc()
        self._expect(TokenType.MAP)
        self._expect(TokenType.LBRACE, "Expected '{' after MAP")
        mappings: List[FieldMapping] = []
        while not self._check(TokenType.RBRACE, TokenType.EOF):
            fl, fc = self._loc()
            target = self._expect(TokenType.IDENTIFIER, "Expected field name").value
            self._expect(TokenType.ASSIGN, "Expected '=' in field mapping")
            expr = self._expr()
            fm = FieldMapping(target=target, expr=expr)
            fm.line, fm.col = fl, fc
            mappings.append(fm)
        self._expect(TokenType.RBRACE, "Expected '}' to close MAP")
        node = MapStep(mappings=mappings)
        node.line, node.col = line, col
        return node

    def _join_key(self) -> str:
        """parse a join key: simple identifier or dotted access (a.b.c)"""
        name = self._expect(TokenType.IDENTIFIER, "Expected field name in join key").value
        parts = [name]
        while self._check(TokenType.DOT):
            self._advance()
            part = self._expect(TokenType.IDENTIFIER, "Expected field after '.'").value
            parts.append(part)
        return ".".join(parts)

    def _join_step(self) -> JoinStep:
        line, col = self._loc()
        self._expect(TokenType.JOIN)
        source = self._expect(TokenType.IDENTIFIER, "Expected source name for JOIN").value
        self._expect(TokenType.ON, "Expected ON in JOIN")
        left_key  = self._join_key()
        self._expect(TokenType.ASSIGN, "Expected '=' between join keys")
        right_key = self._join_key()
        join_type = "INNER"
        if self._match(TokenType.TYPE):
            jt_tok = self._current()
            if jt_tok.type in (TokenType.INNER, TokenType.LEFT,
                               TokenType.RIGHT, TokenType.FULL):
                join_type = self._advance().value
            else:
                raise ParseError("Expected INNER, LEFT, RIGHT, or FULL", jt_tok)
        node = JoinStep(source=source, left_key=left_key,
                        right_key=right_key, join_type=join_type)
        node.line, node.col = line, col
        return node

    def _aggregate_step(self) -> AggregateStep:
        line, col = self._loc()
        self._expect(TokenType.AGGREGATE)
        self._expect(TokenType.LBRACE, "Expected '{' after AGGREGATE")
        rules: List[AggRule] = []
        FUNCS = (TokenType.SUM, TokenType.COUNT, TokenType.AVG,
                 TokenType.MIN, TokenType.MAX)
        while not self._check(TokenType.RBRACE, TokenType.EOF):
            fl, fc = self._loc()
            func_tok = self._current()
            if func_tok.type not in FUNCS:
                raise ParseError("Expected aggregate function (SUM, COUNT, AVG, MIN, MAX)",
                                 func_tok)
            func = self._advance().value
            self._expect(TokenType.LPAREN, "Expected '(' after aggregate function")
            field_name = self._expect(TokenType.IDENTIFIER, "Expected field name").value
            self._expect(TokenType.RPAREN, "Expected ')' after field name")
            self._expect(TokenType.AS, "Expected AS after aggregate expression")
            alias = self._expect(TokenType.IDENTIFIER, "Expected alias name").value
            ar = AggRule(func=func, field=field_name, alias=alias)
            ar.line, ar.col = fl, fc
            rules.append(ar)
        self._expect(TokenType.RBRACE, "Expected '}' to close AGGREGATE")
        node = AggregateStep(rules=rules)
        node.line, node.col = line, col
        return node

    def _sort_step(self) -> SortStep:
        line, col = self._loc()
        self._expect(TokenType.SORT)
        self._expect(TokenType.BY, "Expected BY after SORT")
        keys: List[SortKey] = []
        while True:
            fl, fc = self._loc()
            field_name = self._expect(TokenType.IDENTIFIER, "Expected field name for SORT").value
            direction = "ASC"
            if self._match(TokenType.ASC):
                direction = "ASC"
            elif self._match(TokenType.DESC):
                direction = "DESC"
            sk = SortKey(field=field_name, direction=direction)
            sk.line, sk.col = fl, fc
            keys.append(sk)
            if not self._match(TokenType.COMMA):
                break
        node = SortStep(keys=keys)
        node.line, node.col = line, col
        return node

    def _limit_step(self) -> LimitStep:
        line, col = self._loc()
        self._expect(TokenType.LIMIT)
        count = int(self._expect(TokenType.INTEGER, "Expected integer after LIMIT").value)
        node = LimitStep(count=count)
        node.line, node.col = line, col
        return node

    #output declaration

    def _output_decl(self) -> OutputDecl:
        line, col = self._loc()
        self._expect(TokenType.OUTPUT)
        name = self._expect(TokenType.IDENTIFIER, "Expected output name").value
        self._expect(TokenType.TO, "Expected TO after output name")

        valid_types = (
            TokenType.CSV, TokenType.JSON, TokenType.XML,
            TokenType.DATABASE, TokenType.STDOUT
        )
        out_tok = self._current()
        if out_tok.type not in valid_types:
            raise ParseError("Expected output type (CSV, JSON, XML, DATABASE, STDOUT)", out_tok)
        out_type = self._advance().value

        self._expect(TokenType.LBRACE, "Expected '{' to open output body")
        options = self._output_body()
        self._expect(TokenType.RBRACE, "Expected '}' to close output body")

        node = OutputDecl(name=name, output_type=out_type, options=options)
        node.line, node.col = line, col
        return node

    def _output_body(self) -> dict:
        options: dict = {}
        VALID_KEYS = {"from", "path", "table", "delimiter", "pretty"}
        while not self._check(TokenType.RBRACE, TokenType.EOF):
            key_tok = self._expect(TokenType.IDENTIFIER, "Expected output option name")
            key = key_tok.value
            if key not in VALID_KEYS:
                raise ParseError(f"Unknown output option '{key}'", key_tok)
            self._expect(TokenType.ASSIGN, f"Expected '=' after '{key}'")
            if key == "pretty":
                val_tok = self._current()
                if val_tok.type in (TokenType.TRUE, TokenType.FALSE):
                    options[key] = self._advance().value == "true"
                else:
                    raise ParseError("Expected boolean for 'pretty'", val_tok)
            else:
                options[key] = self._expect(TokenType.STRING,
                                             f"Expected string value for '{key}'").value
        return options

    #conditions

    def _condition(self) -> ASTNode:
        return self._or_expr()

    def _or_expr(self) -> ASTNode:
        line, col = self._loc()
        left = self._and_expr()
        while self._match(TokenType.OR):
            right = self._and_expr()
            node = LogicalOp(left=left, operator="OR", right=right)
            node.line, node.col = line, col
            left = node
        return left

    def _and_expr(self) -> ASTNode:
        line, col = self._loc()
        left = self._not_expr()
        while self._match(TokenType.AND):
            right = self._not_expr()
            node = LogicalOp(left=left, operator="AND", right=right)
            node.line, node.col = line, col
            left = node
        return left

    def _not_expr(self) -> ASTNode:
        line, col = self._loc()
        if self._match(TokenType.NOT):
            operand = self._not_expr()
            node = NotOp(operand=operand)
            node.line, node.col = line, col
            return node
        return self._comparison()

    def _comparison(self) -> ASTNode:
        line, col = self._loc()
        if self._check(TokenType.LPAREN):
            self._advance()
            cond = self._condition()
            self._expect(TokenType.RPAREN, "Expected ')' to close grouped condition")
            return cond

        left = self._expr()

        #IS NULL / IS NOT NULL
        if self._check(TokenType.IS):
            self._advance()
            if self._match(TokenType.NOT):
                self._expect(TokenType.NULL, "Expected NULL after IS NOT")
                node = Comparison(left=left, operator="IS NOT NULL", right=None)
            else:
                self._expect(TokenType.NULL, "Expected NULL after IS")
                node = Comparison(left=left, operator="IS NULL", right=None)
            node.line, node.col = line, col
            return node

        #standard comparison operators
        op_map = {
            TokenType.EQ:   "==",
            TokenType.NEQ:  "!=",
            TokenType.LT:   "<",
            TokenType.LTE:  "<=",
            TokenType.GT:   ">",
            TokenType.GTE:  ">=",
            TokenType.LIKE: "LIKE",
            TokenType.IN:   "IN",
        }
        tok = self._current()
        if tok.type in op_map:
            op = op_map[self._advance().type]
            right = self._expr()
            node = Comparison(left=left, operator=op, right=right)
            node.line, node.col = line, col
            return node

        raise ParseError("Expected comparison operator", tok)

    #expressions (arithmetic)

    def _expr(self) -> ASTNode:
        line, col = self._loc()
        left = self._term()
        while self._check(TokenType.PLUS, TokenType.MINUS):
            op  = self._advance().value
            right = self._term()
            node = BinaryOp(left=left, operator=op, right=right)
            node.line, node.col = line, col
            left = node
        return left

    def _term(self) -> ASTNode:
        line, col = self._loc()
        left = self._factor()
        while self._check(TokenType.STAR, TokenType.SLASH):
            op    = self._advance().value
            right = self._factor()
            node  = BinaryOp(left=left, operator=op, right=right)
            node.line, node.col = line, col
            left  = node
        return left

    def _factor(self) -> ASTNode:
        line, col = self._loc()
        tok = self._current()

        #grouped expression
        if tok.type == TokenType.LPAREN:
            self._advance()
            inner = self._expr()
            self._expect(TokenType.RPAREN, "Expected ')' to close expression")
            return inner

        #literals
        if tok.type == TokenType.STRING:
            self._advance()
            n = StringLiteral(value=tok.value); n.line, n.col = line, col; return n

        if tok.type == TokenType.INTEGER:
            self._advance()
            n = NumberLiteral(value=int(tok.value), is_float=False)
            n.line, n.col = line, col; return n

        if tok.type == TokenType.FLOAT:
            self._advance()
            n = NumberLiteral(value=float(tok.value), is_float=True)
            n.line, n.col = line, col; return n

        if tok.type in (TokenType.TRUE, TokenType.FALSE):
            self._advance()
            n = BooleanLiteral(value=(tok.value.lower() == "true"))
            n.line, n.col = line, col; return n

        if tok.type == TokenType.NULL:
            self._advance()
            n = NullLiteral(); n.line, n.col = line, col; return n

        #identifier, field access, or function call
        if tok.type == TokenType.IDENTIFIER:
            name = self._advance().value
            #function call
            if self._check(TokenType.LPAREN):
                self._advance()
                args: List[ASTNode] = []
                if not self._check(TokenType.RPAREN):
                    args.append(self._expr())
                    while self._match(TokenType.COMMA):
                        args.append(self._expr())
                self._expect(TokenType.RPAREN, "Expected ')' to close function call")
                n = FunctionCall(name=name, args=args)
                n.line, n.col = line, col; return n
            #field access (a.b.c)
            parts = [name]
            while self._check(TokenType.DOT):
                self._advance()
                part = self._expect(TokenType.IDENTIFIER,
                                     "Expected field name after '.'").value
                parts.append(part)
            if len(parts) > 1:
                n = FieldAccess(parts=parts); n.line, n.col = line, col; return n
            n = Identifier(name=name); n.line, n.col = line, col; return n

        raise ParseError("Expected expression", tok)


#convenience function

def parse(source_code: str) -> Program:
    """lex and parse a DataSync DSL program, return the AST root"""
    tokens = Lexer(source_code).tokenize()
    return Parser(tokens).parse()