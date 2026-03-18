"""
tests/test_lexer_parser.py — Unit tests for DataSync DSL lexer and parser
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from src.lexer import Lexer, TokenType, LexerError
from src.parser import ParseError, parse
from ast_nodes import *



#LEXER TESTS
class TestLexer:

    def _lex(self, src: str):
        return Lexer(src).tokenize()

    def _types(self, src: str):
        return [t.type for t in self._lex(src) if t.type != TokenType.EOF]

    #keywords

    def test_keywords_source(self):
        toks = self._lex("SOURCE myapi AS API")
        assert toks[0].type == TokenType.SOURCE
        assert toks[1].type == TokenType.IDENTIFIER
        assert toks[2].type == TokenType.AS
        assert toks[3].type == TokenType.API

    def test_all_source_types(self):
        src = "API CSV JSON XML DATABASE"
        types = self._types(src)
        assert types == [
            TokenType.API, TokenType.CSV, TokenType.JSON,
            TokenType.XML, TokenType.DATABASE
        ]

    def test_pipeline_keywords(self):
        src = "PIPELINE FETCH FROM FILTER WHERE MAP JOIN ON AGGREGATE SORT BY LIMIT"
        types = self._types(src)
        expected = [
            TokenType.PIPELINE, TokenType.FETCH, TokenType.FROM,
            TokenType.FILTER, TokenType.WHERE, TokenType.MAP,
            TokenType.JOIN, TokenType.ON, TokenType.AGGREGATE,
            TokenType.SORT, TokenType.BY, TokenType.LIMIT,
        ]
        assert types == expected

    def test_aggregate_functions(self):
        src = "SUM COUNT AVG MIN MAX"
        types = self._types(src)
        assert types == [
            TokenType.SUM, TokenType.COUNT, TokenType.AVG,
            TokenType.MIN, TokenType.MAX
        ]

    def test_boolean_keywords(self):
        src = "true false TRUE FALSE"
        types = self._types(src)
        assert all(t == TokenType.TRUE or t == TokenType.FALSE for t in types)

    #literals

    def test_string_double_quote(self):
        toks = self._lex('"hello world"')
        assert toks[0].type  == TokenType.STRING
        assert toks[0].value == "hello world"

    def test_string_single_quote(self):
        toks = self._lex("'hello world'")
        assert toks[0].type  == TokenType.STRING
        assert toks[0].value == "hello world"

    def test_string_escape(self):
        toks = self._lex(r'"line1\nline2"')
        assert toks[0].value == "line1\nline2"

    def test_integer(self):
        toks = self._lex("42")
        assert toks[0].type  == TokenType.INTEGER
        assert toks[0].value == "42"

    def test_float(self):
        toks = self._lex("3.14")
        assert toks[0].type  == TokenType.FLOAT
        assert toks[0].value == "3.14"

    #operators

    def test_comparison_operators(self):
        src = "== != < <= > >="
        types = self._types(src)
        assert types == [
            TokenType.EQ, TokenType.NEQ,
            TokenType.LT, TokenType.LTE,
            TokenType.GT, TokenType.GTE,
        ]

    def test_single_char_operators(self):
        src = "= + - * / . , : ( ) { }"
        types = self._types(src)
        assert TokenType.ASSIGN in types
        assert TokenType.PLUS   in types
        assert TokenType.LBRACE in types

    #comments

    def test_comment_skipped(self):
        toks = self._lex("# this is a comment\nSOURCE")
        assert toks[0].type == TokenType.SOURCE

    def test_inline_comment(self):
        toks = self._lex("SOURCE # comment\nAS")
        types = [t.type for t in toks if t.type != TokenType.EOF]
        assert types == [TokenType.SOURCE, TokenType.AS]

    #identifiers

    def test_identifier(self):
        toks = self._lex("my_source_123")
        assert toks[0].type  == TokenType.IDENTIFIER
        assert toks[0].value == "my_source_123"

    def test_identifier_underscore_start(self):
        toks = self._lex("_private")
        assert toks[0].type == TokenType.IDENTIFIER

    #error handling

    def test_unterminated_string(self):
        with pytest.raises(LexerError) as exc:
            self._lex('"unterminated')
        assert "Unterminated" in str(exc.value)

    def test_unexpected_character(self):
        with pytest.raises(LexerError):
            self._lex("@invalid")

    #line/column tracking

    def test_line_tracking(self):
        toks = self._lex("SOURCE\nAS\nAPI")
        assert toks[0].line == 1
        assert toks[1].line == 2
        assert toks[2].line == 3

    def test_eof_token(self):
        toks = self._lex("SOURCE")
        assert toks[-1].type == TokenType.EOF



#  PARSER TESTS
class TestParser:

    #source declarations

    def test_source_api_basic(self):
        src = '''
        SOURCE my_api AS API {
            url    = "https://example.com/data"
            method = GET
        }
        '''
        ast = parse(src)
        assert len(ast.statements) == 1
        s = ast.statements[0]
        assert isinstance(s, SourceDecl)
        assert s.name == "my_api"
        assert s.source_type == "API"
        assert s.options["url"] == "https://example.com/data"
        assert s.options["method"] == "GET"

    def test_source_csv(self):
        src = '''
        SOURCE products AS CSV {
            path     = "data/products.csv"
            encoding = "utf-8"
        }
        '''
        ast = parse(src)
        s = ast.statements[0]
        assert s.source_type == "CSV"
        assert s.options["path"] == "data/products.csv"

    def test_source_bearer_auth(self):
        src = '''
        SOURCE secure AS API {
            url  = "https://secure.com"
            auth = BEARER "tok123"
        }
        '''
        ast = parse(src)
        auth = ast.statements[0].options["auth"]
        assert isinstance(auth, AuthExpr)
        assert auth.method == "BEARER"
        assert auth.arg1   == "tok123"

    def test_source_basic_auth(self):
        src = '''
        SOURCE db_src AS DATABASE {
            url  = "postgresql://localhost/db"
            auth = BASIC "user" "pass"
        }
        '''
        ast = parse(src)
        auth = ast.statements[0].options["auth"]
        assert auth.method == "BASIC"
        assert auth.arg1   == "user"
        assert auth.arg2   == "pass"

    def test_source_api_key_auth(self):
        src = '''
        SOURCE ext AS API {
            url  = "https://ext.com"
            auth = API_KEY "x-key" "secret"
        }
        '''
        ast = parse(src)
        auth = ast.statements[0].options["auth"]
        assert auth.method == "API_KEY"
        assert auth.arg1   == "x-key"
        assert auth.arg2   == "secret"

    def test_source_headers(self):
        src = '''
        SOURCE h_api AS API {
            url     = "https://api.com"
            headers = {"Accept": "application/json", "X-Version": "2"}
        }
        '''
        ast = parse(src)
        headers = ast.statements[0].options["headers"]
        assert any(h.key == "Accept" for h in headers)

    #pipeline declarations

    def test_pipeline_fetch(self):
        src = '''
        SOURCE s1 AS CSV { path = "a.csv" }
        PIPELINE p1 {
            FETCH FROM s1
        }
        '''
        ast = parse(src)
        pipe = ast.statements[1]
        assert isinstance(pipe, PipelineDecl)
        assert pipe.name == "p1"
        step = pipe.steps[0]
        assert isinstance(step, FetchStep)
        assert "s1" in step.sources

    def test_pipeline_fetch_multiple_sources(self):
        src = '''
        PIPELINE p1 {
            FETCH FROM src1, src2, src3
        }
        '''
        ast = parse(src)
        step = ast.statements[0].steps[0]
        assert step.sources == ["src1", "src2", "src3"]

    def test_pipeline_filter_simple(self):
        src = '''
        PIPELINE p1 {
            FILTER WHERE age >= 18
        }
        '''
        pipe = parse(src).statements[0]
        step = pipe.steps[0]
        assert isinstance(step, FilterStep)
        cond = step.condition
        assert isinstance(cond, Comparison)
        assert cond.operator == ">="

    def test_pipeline_filter_and(self):
        src = '''
        PIPELINE p1 {
            FILTER WHERE age >= 18 AND status == "active"
        }
        '''
        step = parse(src).statements[0].steps[0]
        assert isinstance(step.condition, LogicalOp)
        assert step.condition.operator == "AND"

    def test_pipeline_filter_or(self):
        src = '''
        PIPELINE p1 {
            FILTER WHERE role == "admin" OR role == "manager"
        }
        '''
        cond = parse(src).statements[0].steps[0].condition
        assert isinstance(cond, LogicalOp)
        assert cond.operator == "OR"

    def test_pipeline_filter_not(self):
        src = '''
        PIPELINE p1 {
            FILTER WHERE NOT status == "inactive"
        }
        '''
        cond = parse(src).statements[0].steps[0].condition
        assert isinstance(cond, NotOp)

    def test_pipeline_filter_is_null(self):
        src = '''
        PIPELINE p1 {
            FILTER WHERE email IS NULL
        }
        '''
        cond = parse(src).statements[0].steps[0].condition
        assert isinstance(cond, Comparison)
        assert cond.operator == "IS NULL"

    def test_pipeline_filter_is_not_null(self):
        src = '''
        PIPELINE p1 {
            FILTER WHERE phone IS NOT NULL
        }
        '''
        cond = parse(src).statements[0].steps[0].condition
        assert cond.operator == "IS NOT NULL"

    def test_pipeline_map(self):
        src = '''
        PIPELINE p1 {
            MAP {
                full_name = first_name
                score     = 100
            }
        }
        '''
        step = parse(src).statements[0].steps[0]
        assert isinstance(step, MapStep)
        assert len(step.mappings) == 2
        assert step.mappings[0].target == "full_name"

    def test_pipeline_join_default_inner(self):
        src = '''
        PIPELINE p1 {
            JOIN products ON orders.product_id = products.id
        }
        '''
        step = parse(src).statements[0].steps[0]
        assert isinstance(step, JoinStep)
        assert step.source    == "products"
        assert step.left_key  == "orders.product_id"
        assert step.right_key == "products.id"
        assert step.join_type == "INNER"

    def test_pipeline_join_left(self):
        src = '''
        PIPELINE p1 {
            JOIN b ON a.id = b.id TYPE LEFT
        }
        '''
        step = parse(src).statements[0].steps[0]
        assert step.join_type == "LEFT"

    def test_pipeline_aggregate(self):
        src = '''
        PIPELINE p1 {
            AGGREGATE {
                SUM(amount)  AS total
                COUNT(id)    AS count
                AVG(price)   AS average
            }
        }
        '''
        step = parse(src).statements[0].steps[0]
        assert isinstance(step, AggregateStep)
        assert len(step.rules) == 3
        assert step.rules[0].func  == "SUM"
        assert step.rules[0].alias == "total"

    def test_pipeline_sort_asc_desc(self):
        src = '''
        PIPELINE p1 {
            SORT BY created_at DESC, name ASC
        }
        '''
        step = parse(src).statements[0].steps[0]
        assert isinstance(step, SortStep)
        assert step.keys[0].field     == "created_at"
        assert step.keys[0].direction == "DESC"
        assert step.keys[1].direction == "ASC"

    def test_pipeline_limit(self):
        src = '''
        PIPELINE p1 {
            LIMIT 50
        }
        '''
        step = parse(src).statements[0].steps[0]
        assert isinstance(step, LimitStep)
        assert step.count == 50

    #output declarations

    def test_output_csv(self):
        src = '''
        OUTPUT report TO CSV {
            from      = "pipeline1"
            path      = "out.csv"
            delimiter = ","
        }
        '''
        out = parse(src).statements[0]
        assert isinstance(out, OutputDecl)
        assert out.output_type         == "CSV"
        assert out.options["from"]     == "pipeline1"
        assert out.options["delimiter"] == ","

    def test_output_json_pretty(self):
        src = '''
        OUTPUT result TO JSON {
            from   = "pipe"
            path   = "out.json"
            pretty = true
        }
        '''
        out = parse(src).statements[0]
        assert out.output_type      == "JSON"
        assert out.options["pretty"] is True

    def test_output_stdout(self):
        src = '''
        OUTPUT debug TO STDOUT {
            from = "my_pipeline"
        }
        '''
        out = parse(src).statements[0]
        assert out.output_type == "STDOUT"

    #full programs

    def test_full_program(self):
        src = '''
        SOURCE users AS API {
            url    = "https://api.example.com/users"
            method = GET
            auth   = BEARER "token123"
        }

        PIPELINE user_report {
            FETCH FROM users
            FILTER WHERE age >= 18 AND status == "active"
            MAP {
                name  = first_name
                email = email
            }
            SORT BY name ASC
            LIMIT 100
        }

        OUTPUT csv_out TO CSV {
            from = "user_report"
            path = "users.csv"
        }
        '''
        ast = parse(src)
        assert len(ast.statements) == 3
        assert isinstance(ast.statements[0], SourceDecl)
        assert isinstance(ast.statements[1], PipelineDecl)
        assert isinstance(ast.statements[2], OutputDecl)

    #error handling

    def test_missing_source_type_error(self):
        with pytest.raises(ParseError):
            parse("SOURCE s AS UNKNOWN { }")

    def test_missing_brace_error(self):
        with pytest.raises(ParseError):
            parse("SOURCE s AS API { url = 'x' ")

    def test_unknown_source_option_error(self):
        with pytest.raises(ParseError):
            parse("SOURCE s AS API { bad_option = 'x' }")

    def test_missing_pipeline_keyword(self):
        with pytest.raises(ParseError):
            parse("PIPELINE p1 { UNKNOWN_STEP }")

    def test_empty_program(self):
        ast = parse("")
        assert isinstance(ast, Program)
        assert ast.statements == []


#run directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])