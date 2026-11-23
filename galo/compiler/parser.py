"""Analisador sintático da GALO (descida recursiva).

A gramática completa, em EBNF, está em docs/grammar.md. Cada método
`parse_*` corresponde a uma regra da gramática.
"""

from __future__ import annotations

import difflib

from ..errors import GaloSyntaxError
from . import ast as A
from .tokens import (
    BLOCK_ENDERS, DECIMAL, EOF, INTEIRO, KEYWORDS, NL, NOME, STATEMENT_KEYWORDS,
    TEXTO, InterpPart, Token, canonical,
)

COMPARISON_OPS = ("==", "!=", "<", "<=", ">", ">=", "em")
ASSIGN_OPS = ("=", "+=", "-=", "*=", "/=")
EXPR_START = {NOME, INTEIRO, DECIMAL, TEXTO, "(", "[", "{", "verdadeiro", "falso", "nulo", "função", "-", "+", "não", "eu"}

# Palavras que pessoas costumam digitar no lugar das instruções da GALO.
COMMON_MISTAKES = {
    "mostra": "mostre", "mostrar": "mostre", "imprima": "mostre", "imprimir": "mostre",
    "exiba": "mostre", "exibir": "mostre", "print": "mostre", "escreve": "mostre",
    "defini": "defina", "definir": "defina", "var": "defina", "seja": "defina", "let": "defina",
    "if": "se", "while": "enquanto", "for": "para", "return": "retorne", "retorna": "retorne",
    "retornar": "retorne", "def": "função", "function": "função", "func": "função",
    "break": "pare", "parar": "pare", "try": "tente", "catch": "capture", "throw": "lance",
    "repete": "repita", "repetir": "repita", "senao": "senão", "else": "senão", "end": "fim",
    "import": "importe", "importar": "importe", "use": "importe", "class": "registro", "struct": "registro",
}


class Parser:
    def __init__(self, tokens: list[Token], filename: str | None = None, repl: bool = False) -> None:
        self.toks = tokens
        self.i = 0
        self.filename = filename
        self.repl = repl
        self.nl_ignore = [False]
        # Blocos cujo 'fim' não está alinhado com a abertura: (abertura, construção, fim).
        self.suspicious: list[tuple[Token, str, Token]] = []

    # ------------------------------------------------------------ tokens

    def _skip(self) -> None:
        if self.nl_ignore[-1]:
            toks = self.toks
            while toks[self.i].kind == NL:
                self.i += 1

    def peek(self, k: int = 0) -> Token:
        self._skip()
        if k == 0:
            return self.toks[self.i]
        j = self.i
        ignore = self.nl_ignore[-1]
        for _ in range(k):
            if self.toks[j].kind == EOF:
                return self.toks[j]
            j += 1
            if ignore:
                while self.toks[j].kind == NL:
                    j += 1
        return self.toks[j]

    def advance(self) -> Token:
        tok = self.peek()
        if tok.kind != EOF:
            self.i += 1
        return tok

    def check(self, *kinds: str) -> bool:
        return self.peek().kind in kinds

    def match(self, *kinds: str) -> Token | None:
        if self.peek().kind in kinds:
            return self.advance()
        return None

    @staticmethod
    def is_word(tok: Token, word: str) -> bool:
        return tok.kind == NOME and tok.key == canonical(word)

    def skip_newlines_after_operator(self) -> None:
        while self.toks[self.i].kind == NL:
            self.i += 1

    def skip_terminators(self) -> None:
        while self.check(NL, ";"):
            self.advance()

    def at_terminator(self) -> bool:
        k = self.peek().kind
        return k in (NL, ";", EOF) or k in BLOCK_ENDERS

    # ------------------------------------------------------------ erros

    def error(self, code: str, message: str, tok: Token | None = None,
              suggestion: str | None = None, length: int | None = None) -> GaloSyntaxError:
        tok = tok or self.peek()
        err = GaloSyntaxError(code, message, tok.line, tok.col, length or tok.length, suggestion, self.filename)
        if tok.kind == EOF:
            err.incomplete = True
        return err

    def expect(self, kind: str, message: str, suggestion: str | None = None) -> Token:
        tok = self.peek()
        if tok.kind == kind:
            return self.advance()
        raise self.error("G102", f"{message}, mas encontrei {tok.describe()}.", tok, suggestion)

    def _expect_name(self, what: str, example: str) -> Token:
        tok = self.peek()
        if tok.kind == NOME:
            return self.advance()
        if tok.kind in KEYWORDS:
            raise self.error(
                "G102", f"'{tok.text}' é uma palavra reservada da GALO e não pode ser usada como {what}.",
                tok, f"Escolha outro nome. Exemplo: {example}",
            )
        raise self.error("G102", f"Esperava {what}, mas encontrei {tok.describe()}.", tok, f"Exemplo: {example}")

    # ------------------------------------------------------------ programa

    def parse_program(self) -> A.Programa:
        self.skip_terminators()
        first = self.peek()
        name = None
        if first.kind == "programa":
            self.advance()
            tok = self.peek()
            if tok.kind != TEXTO:
                raise self.error(
                    "G102", f"Esperava o nome do programa entre aspas depois de 'programa', mas encontrei {tok.describe()}.",
                    tok, 'Exemplo: programa "Meu Primeiro GALO"',
                )
            self.advance()
            if any(not isinstance(p, str) for p in tok.value):
                raise self.error("G102", "O nome do programa não pode conter interpolação '{...}'.", tok)
            name = "".join(tok.value)
            self.end_statement()
        stmts = self.parse_statements((), None, None)
        return A.Programa(first.line, first.col, name, A.Block(first.line, first.col, stmts))

    # ------------------------------------------------------------ blocos

    def parse_statements(self, enders: tuple, opener: Token | None, construct: str | None) -> list:
        stmts = []
        self.skip_terminators()
        while True:
            tok = self.peek()
            if tok.kind == EOF:
                if opener is not None:
                    raise self._unclosed(opener, construct)
                break
            if tok.kind in enders:
                break
            if tok.kind in BLOCK_ENDERS:
                raise self._misplaced_ender(tok, opener, construct)
            stmts.append(self.parse_statement())
            self.end_statement()
            self.skip_terminators()
        return stmts

    def parse_block(self, enders: tuple, opener: Token, construct: str) -> A.Block:
        stmts = self.parse_statements(enders, opener, construct)
        return A.Block(opener.line, opener.col, stmts)

    def close_block(self, opener: Token, construct: str) -> Token:
        fim = self.expect("fim", f"Esperava 'fim' para fechar o bloco '{construct}' da linha {opener.line}")
        if opener.bol and fim.bol and opener.col != fim.col:
            self.suspicious.append((opener, construct, fim))
        return fim

    def _unclosed(self, opener: Token, construct: str) -> GaloSyntaxError:
        message = f"O bloco '{construct}' iniciado na linha {opener.line} não foi fechado com 'fim'."
        suggestion = "Adicione 'fim' ao final do bloco."
        for o, c, f in self.suspicious:
            if (o.line, o.col) > (opener.line, opener.col):
                suggestion += (
                    f"\nProvavelmente falta o 'fim' do bloco '{c}' da linha {o.line}: "
                    f"o 'fim' da linha {f.line} está alinhado com outro bloco."
                )
                break
        err = GaloSyntaxError("G103", message, opener.line, opener.col, opener.length, suggestion, self.filename)
        err.incomplete = True
        return err

    def _misplaced_ender(self, tok: Token, opener: Token | None, construct: str | None) -> GaloSyntaxError:
        word = tok.kind
        if opener is None:
            if word == "fim":
                return self.error(
                    "G104", "Este 'fim' não fecha nenhum bloco.", tok,
                    "Remova este 'fim' ou verifique se algum bloco (se, enquanto, função...) foi fechado duas vezes.",
                )
            owner = "se" if word == "senão" else "tente"
            return self.error("G110", f"'{tok.text}' só pode ser usado dentro de um bloco '{owner}'.", tok)
        if word == "senão" and construct == "se":
            return self.error(
                "G110", f"O 'se' da linha {opener.line} já possui um 'senão' final.", tok,
                "Para testar outra condição, use 'senão se ... então' antes do 'senão' final.",
            )
        if word == "capture" and construct == "tente":
            return self.error("G110", f"O 'tente' da linha {opener.line} já possui um 'capture'.", tok)
        return self.error(
            "G110",
            f"Encontrei '{tok.text}' dentro do bloco '{construct}' iniciado na linha {opener.line}, "
            f"que ainda não foi fechado.",
            tok, f"Feche o bloco '{construct}' com 'fim' antes de '{tok.text}'.",
        )

    def end_statement(self) -> None:
        tok = self.peek()
        if tok.kind in (NL, ";"):
            self.advance()
            return
        if tok.kind in BLOCK_ENDERS or tok.kind == EOF:
            return
        if tok.kind == "=":
            raise self.error("G109", "O símbolo '=' serve para atribuir valores. Para comparar, use '=='.", tok,
                             "Exemplo de comparação: se x == 5 então")
        if tok.kind in STATEMENT_KEYWORDS:
            raise self.error(
                "G101", f"Esperava o fim da instrução, mas encontrei {tok.describe()}.", tok,
                "Coloque cada instrução em sua própria linha (ou separe-as com ';').",
            )
        if tok.kind in EXPR_START:
            raise self.error(
                "G101", f"Esperava o fim da instrução, mas encontrei {tok.describe()}.", tok,
                "Talvez falte um operador (+, -, *, /), uma vírgula entre valores ou uma quebra de linha.",
            )
        raise self.error("G101", f"Esperava o fim da instrução, mas encontrei {tok.describe()}.", tok)

    # ------------------------------------------------------------ instruções

    def parse_statement(self):
        tok = self.peek()
        k = tok.kind
        if k in ("defina", "constante"):
            return self.parse_defina()
        if k == "importe":
            return self.parse_importe()
        if k == "registro":
            return self.parse_registro()
        if k == "função" and self.peek(1).kind == NOME:
            return self.parse_funcao_decl()
        if k == "se":
            return self.parse_se()
        if k == "enquanto":
            return self.parse_enquanto()
        if k == "repita":
            return self.parse_repita()
        if k == "para":
            return self.parse_para()
        if k == "tente":
            return self.parse_tente()
        if k == "mostre":
            return self.parse_mostre()
        if k == "retorne":
            self.advance()
            value = None if self.at_terminator() else self.parse_expression()
            return A.Retorne(tok.line, tok.col, value)
        if k == "pare":
            self.advance()
            return A.Pare(tok.line, tok.col)
        if k == "continue":
            self.advance()
            return A.Continue(tok.line, tok.col)
        if k == "lance":
            self.advance()
            if self.at_terminator():
                raise self.error("G105", "Esperava o erro a ser lançado depois de 'lance'.", None,
                                 'Exemplo: lance "Valor inválido"')
            return A.Lance(tok.line, tok.col, self.parse_expression())
        if k == "programa":
            raise self.error("G111", "A instrução 'programa' só pode aparecer na primeira linha do arquivo.", tok)
        if k == "retorna":
            raise self.error("G112", "'retorna' indica o tipo de retorno no cabeçalho de uma função.", tok,
                             "Para devolver um valor de dentro da função, use 'retorne': retorne resultado")
        if k in ("então", "faça", "como", "em"):
            raise self.error("G101", f"A palavra '{tok.text}' está fora de lugar: ela não pode iniciar uma instrução.", tok)
        return self.parse_expr_statement()

    def parse_defina(self):
        kw = self.advance()
        constant = kw.kind == "constante"
        what = "nome da constante" if constant else "nome da variável"
        name = self._expect_name(what, f"{kw.text} idade como 22")
        typ = None
        if self.is_word(self.peek(), "do") and self.is_word(self.peek(1), "tipo"):
            self.advance()
            self.advance()
            typ = self.parse_type()
        if not self.check("como"):
            t = self.peek()
            if t.kind == "=":
                raise self.error("G102", f"Em GALO, a declaração usa 'como' em vez de '='.", t,
                                 f"{kw.text} {name.text} como ...")
            if t.kind in (NL, EOF, ";"):
                raise self.error("G102", f"A {'constante' if constant else 'variável'} '{name.text}' precisa de um valor inicial.",
                                 t, f"{kw.text} {name.text} como nulo")
            if t.kind == ":":
                raise self.error("G102", "Para indicar o tipo, use 'do tipo'.", t,
                                 f"{kw.text} {name.text} do tipo inteiro como 0")
            self.expect("como", f"Esperava 'como' depois de '{name.text}'", f"{kw.text} {name.text} como 0")
        self.advance()
        value = self.parse_expression()
        return A.Defina(kw.line, kw.col, name.text, name.key, typ, value, constant, name.line, name.col)

    def parse_type(self) -> A.TypeAnnot:
        first = self.peek()
        names, keys = [], []
        while True:
            t = self.advance()
            if t.kind == NOME:
                names.append(t.text)
                keys.append(t.key)
            elif t.kind in ("nulo", "função"):
                names.append(t.text)
                keys.append(canonical(t.kind))
            else:
                raise self.error(
                    "G102", f"Esperava um nome de tipo, mas encontrei {t.describe()}.", t,
                    "Tipos disponíveis: inteiro, decimal, número, texto, booleano, lista, mapa, função, nulo, qualquer.",
                )
            if not self.match("ou"):
                break
        return A.TypeAnnot(first.line, first.col, names, keys)

    def parse_params(self) -> list:
        self.expect("(", "Esperava '(' com os parâmetros da função",
                    "Exemplo: função somar(a, b) — use () quando não houver parâmetros.")
        self.nl_ignore.append(True)
        params = []
        while not self.check(")"):
            params.append(self.parse_param())
            if not self.match(","):
                break
        if not self.check(")"):
            t = self.peek()
            hint = "Separe os parâmetros com vírgulas." if t.kind == NOME else None
            raise self.error("G102", f"Esperava ')' para fechar a lista de parâmetros, mas encontrei {t.describe()}.", t, hint)
        self.advance()
        self.nl_ignore.pop()
        return params

    def _parece_tipo_de_retorno(self, k: int) -> bool:
        """O token na posição k (e os seguintes) formam só um tipo, no fim da linha?"""
        from .typesys import TYPE_NAMES

        while True:
            tok = self.peek(k)
            if not (tok.kind in ("nulo", "função") or (tok.kind == NOME and tok.key in TYPE_NAMES)):
                return False
            if self.peek(k + 1).kind != "ou":
                return self.peek(k + 1).kind in (NL, EOF, ";")
            k += 2

    def parse_param(self, what: str = "o nome de um parâmetro",
                    example: str = "função somar(a como número, b como número = 0)") -> A.Param:
        t = self._expect_name(what, example)
        ptype = None
        if self.match("como"):
            ptype = self.parse_type()
        default = None
        if self.match("="):
            self.skip_newlines_after_operator()
            default = self.parse_expression()
        return A.Param(t.line, t.col, t.text, t.key, ptype, default)

    def _plain_text(self, tok: Token, what: str) -> str:
        if any(not isinstance(p, str) for p in tok.value):
            raise self.error("G102", f"{what.capitalize()} não pode conter interpolação '{{...}}'.", tok)
        return "".join(tok.value)

    def parse_importe(self):
        kw = self.advance()
        tok = self.peek()
        if tok.kind == TEXTO:
            self.advance()
            path = self._plain_text(tok, "o caminho do módulo")
            if not self.check("como"):
                stem = path.rsplit("/", 1)[-1].removesuffix(".galo") or "modulo"
                raise self.error("G102", f"Esperava 'como' e um nome para o módulo, mas encontrei {self.peek().describe()}.",
                                 None, f'importe "{path}" como {canonical(stem)}')
            self.advance()
            n = self._expect_name("o nome do módulo", 'importe "util.galo" como util')
            return A.Importe(kw.line, kw.col, path, A.VarDecl(n.line, n.col, n.text, n.key), [])
        names = []
        while True:
            n = self._expect_name("o nome a importar ou o caminho do arquivo entre aspas",
                                  'importe "util.galo" como util   ou   importe somar, media de "util.galo"')
            names.append(A.VarDecl(n.line, n.col, n.text, n.key))
            if not self.match(","):
                break
        t = self.peek()
        if not self.is_word(t, "de"):
            raise self.error("G102", f"Esperava 'de' e o caminho do arquivo, mas encontrei {t.describe()}.", t,
                             f'importe {", ".join(v.name for v in names)} de "arquivo.galo"')
        self.advance()
        t = self.peek()
        if t.kind != TEXTO:
            raise self.error("G102", f"Esperava o caminho do arquivo entre aspas, mas encontrei {t.describe()}.", t,
                             'importe somar de "util.galo"')
        self.advance()
        return A.Importe(kw.line, kw.col, self._plain_text(t, "o caminho do módulo"), None, names)

    def parse_registro(self):
        kw = self.advance()
        name = self._expect_name("o nome do registro", "registro Pessoa")
        if self.check("("):
            fields = self.parse_params()
            return A.DefRegistro(kw.line, kw.col, name.text, name.key, fields, [], name.line, name.col)
        fields, methods = [], []
        self.skip_terminators()
        while True:
            tok = self.peek()
            if tok.kind == EOF:
                raise self._unclosed(kw, "registro")
            if tok.kind == "fim":
                break
            if tok.kind == "função":
                if self.peek(1).kind != NOME:
                    raise self.error("G102", "Um método precisa de um nome: função nome(...).", tok)
                methods.append(self.parse_funcao_decl())
            elif tok.kind == NOME:
                fields.append(self.parse_param("o nome do campo", "nome como texto"))
            else:
                raise self.error(
                    "G102", f"Dentro de um registro, esperava um campo ou um método, mas encontrei {tok.describe()}.",
                    tok, "registro Pessoa\n    nome como texto\n    idade como inteiro = 0\n"
                         "    função apresentar()\n        mostre eu.nome\n    fim\nfim",
                )
            self.end_statement()
            self.skip_terminators()
        self.close_block(kw, "registro")
        return A.DefRegistro(kw.line, kw.col, name.text, name.key, fields, methods, name.line, name.col)

    def parse_funcao_decl(self):
        kw = self.advance()
        name = self.advance()
        params = self.parse_params()
        ret = None
        if self.match("retorna"):
            ret = self.parse_type()
        elif self.check("retorne") and self._parece_tipo_de_retorno(1):
            # "função f() retorne inteiro": provável confusão com 'retorna'. Já
            # "função f(n) retorne n * 2 fim" é um corpo de uma linha e é válido.
            raise self.error("G112", "No cabeçalho da função, o tipo de retorno é indicado com 'retorna'.", self.peek(),
                             f"função {name.text}(...) retorna inteiro")
        body = self.parse_block(("fim",), kw, "função")
        self.close_block(kw, "função")
        return A.DefFuncao(kw.line, kw.col, name.text, name.key, params, ret, body, name.line, name.col)

    def _expect_after_condition(self, word: str, construct: str) -> None:
        tok = self.peek()
        if tok.kind == word:
            self.advance()
            return
        if word == "então" and tok.kind == "faça":
            raise self.error("G102", "No 'se', use 'então' depois da condição ('faça' é usado nos laços).", tok,
                             "se idade >= 18 então")
        if word == "faça" and tok.kind == "então":
            raise self.error("G102", f"No '{construct}', use 'faça' depois da condição ('então' é usado no 'se').", tok,
                             "enquanto contador <= 10 faça")
        if tok.kind == "=":
            raise self.error("G109", "Para comparar valores use '=='. O símbolo '=' serve apenas para atribuir.", tok,
                             f"{construct} x == 5 {word}")
        example = {"se": "se idade >= 18 então", "para cada": "para cada item em lista faça",
                   "para": "para i de 1 até 10 faça", "enquanto": "enquanto contador <= 10 faça"}.get(
            construct, f"{construct} ... {word}")
        raise self.error("G102", f"Esperava '{word}' depois da condição do '{construct}', mas encontrei {tok.describe()}.",
                         tok, example)

    def parse_se(self):
        kw = self.advance()
        cond = self.parse_expression()
        self._expect_after_condition("então", "se")
        branches = [(cond, self.parse_block(("senão", "fim"), kw, "se"))]
        else_block = None
        while self.check("senão"):
            senao = self.advance()
            if self.check("se"):
                self.advance()
                c = self.parse_expression()
                self._expect_after_condition("então", "se")
                branches.append((c, self.parse_block(("senão", "fim"), kw, "se")))
            else:
                else_block = self.parse_block(("fim",), kw, "se")
                break
        self.close_block(kw, "se")
        return A.Se(kw.line, kw.col, branches, else_block)

    def parse_enquanto(self):
        kw = self.advance()
        cond = self.parse_expression()
        self._expect_after_condition("faça", "enquanto")
        body = self.parse_block(("fim",), kw, "enquanto")
        self.close_block(kw, "enquanto")
        return A.Enquanto(kw.line, kw.col, cond, body)

    def parse_repita(self):
        kw = self.advance()
        count = self.parse_expression()
        tok = self.peek()
        if not self.is_word(tok, "vezes"):
            raise self.error("G102", f"Esperava 'vezes' depois da quantidade de repetições, mas encontrei {tok.describe()}.",
                             tok, "repita 3 vezes")
        self.advance()
        body = self.parse_block(("fim",), kw, "repita")
        self.close_block(kw, "repita")
        return A.Repita(kw.line, kw.col, count, body)

    def parse_para(self):
        kw = self.advance()
        tok = self.peek()
        if self.is_word(tok, "cada") and self.peek(1).kind == NOME:
            self.advance()
            n1 = self._expect_name("o nome da variável do laço", "para cada item em lista faça")
            v1 = A.VarDecl(n1.line, n1.col, n1.text, n1.key)
            v2 = None
            if self.match(","):
                n2 = self._expect_name("o nome da segunda variável do laço", "para cada chave, valor em mapa faça")
                v2 = A.VarDecl(n2.line, n2.col, n2.text, n2.key)
            self.expect("em", "Esperava 'em' depois da variável do 'para cada'", "para cada item em lista faça")
            iterable = self.parse_expression()
            self._expect_after_condition("faça", "para cada")
            body = self.parse_block(("fim",), kw, "para")
            self.close_block(kw, "para")
            return A.ParaCada(kw.line, kw.col, v1, v2, iterable, body)

        if tok.kind != NOME:
            raise self.error(
                "G102", f"Esperava 'cada' ou o nome da variável do laço depois de 'para', mas encontrei {tok.describe()}.",
                tok, "para i de 1 até 10 faça   ou   para cada item em lista faça",
            )
        n = self.advance()
        var = A.VarDecl(n.line, n.col, n.text, n.key)
        t = self.peek()
        if not self.is_word(t, "de"):
            if t.kind == "em":
                raise self.error("G102", "Para percorrer uma coleção, use 'para cada'.", t,
                                 f"para cada {n.text} em ... faça")
            raise self.error("G102", f"Esperava 'de' depois de '{n.text}', mas encontrei {t.describe()}.", t,
                             f"para {n.text} de 1 até 10 faça")
        self.advance()
        start = self.parse_expression()
        t = self.peek()
        if not self.is_word(t, "até"):
            raise self.error("G102", f"Esperava 'até' depois do valor inicial, mas encontrei {t.describe()}.", t,
                             f"para {n.text} de 1 até 10 faça")
        self.advance()
        end = self.parse_expression()
        step = None
        if self.is_word(self.peek(), "passo"):
            self.advance()
            step = self.parse_expression()
        self._expect_after_condition("faça", "para")
        body = self.parse_block(("fim",), kw, "para")
        self.close_block(kw, "para")
        return A.ParaIntervalo(kw.line, kw.col, var, start, end, step, body)

    def parse_tente(self):
        kw = self.advance()
        body = self.parse_block(("capture", "fim"), kw, "tente")
        if self.check("fim"):
            raise self.error(
                "G102", "O bloco 'tente' precisa de uma parte 'capture' antes do 'fim'.", self.peek(),
                "tente\n    ...\ncapture erro\n    mostre erro.mensagem\nfim",
            )
        self.advance()  # capture
        err_var = None
        t = self.peek()
        if t.kind == NOME:
            self.advance()
            err_var = A.VarDecl(t.line, t.col, t.text, t.key)
        elif t.kind in KEYWORDS and t.kind not in STATEMENT_KEYWORDS + BLOCK_ENDERS + ("verdadeiro", "falso", "nulo"):
            raise self.error(
                "G102", f"'{t.text}' é uma palavra reservada da GALO e não pode ser o nome da variável do erro.", t,
                "Escolha outro nome, por exemplo: capture erro",
            )
        handler = self.parse_block(("fim",), kw, "tente")
        self.close_block(kw, "tente")
        return A.Tente(kw.line, kw.col, body, err_var, handler)

    def parse_mostre(self):
        kw = self.advance()
        values = []
        if not self.at_terminator():
            values.append(self.parse_expression())
            while self.match(","):
                values.append(self.parse_expression())
            if self.peek().kind in EXPR_START:
                raise self.error("G101", f"Esperava o fim da instrução, mas encontrei {self.peek().describe()}.", None,
                                 'Para mostrar vários valores, separe-os com vírgulas: mostre "Total:", total')
        return A.Mostre(kw.line, kw.col, values)

    def parse_expr_statement(self):
        start = self.peek()
        expr = self.parse_expression()
        if self.check(*ASSIGN_OPS):
            op = self.advance()
            if not isinstance(expr, (A.Nome, A.Indice, A.Campo)):
                raise self.error(
                    "G108", "Não é possível atribuir um valor a esta expressão.", op,
                    "O lado esquerdo do '=' deve ser uma variável (x = 1), uma posição de lista "
                    "(lista[1] = 2) ou um campo de mapa (pessoa.nome = \"Ana\").",
                )
            self.skip_newlines_after_operator()
            value = self.parse_expression()
            return A.Atribuicao(op.line, op.col, expr, op.kind, value)
        if isinstance(expr, A.Chamada) or self.repl:
            return A.ExprStmt(start.line, start.col, expr)
        nxt = self.peek()
        if isinstance(expr, A.Nome):
            suggestion = self._keyword_suggestion(expr.key)
            if suggestion and (nxt.kind not in (NL, ";", EOF) or suggestion in ("pare", "continue")):
                raise GaloSyntaxError(
                    "G106", f"Comando desconhecido: '{expr.name}'.", expr.line, expr.col, expr.length,
                    f"Você quis dizer '{suggestion}'?", self.filename,
                )
            if nxt.kind in EXPR_START:
                raise self.error(
                    "G101", f"Instrução inválida: depois de '{expr.name}' veio {nxt.describe()}.", nxt,
                    f"Se '{expr.name}' é uma função, chame-a com parênteses: {expr.name}(...)",
                )
            if nxt.kind in (NL, ";", EOF) or nxt.kind in BLOCK_ENDERS:
                raise GaloSyntaxError(
                    "G107", f"A linha contém apenas o nome '{expr.name}', o que não faz nada.",
                    expr.line, expr.col, expr.length,
                    f"Para mostrar o valor, use: mostre {expr.name}\nSe for uma função, chame-a com parênteses: {expr.name}()",
                    self.filename,
                )
            raise self.error("G101", f"Esperava o fim da instrução, mas encontrei {nxt.describe()}.", nxt)
        if isinstance(expr, A.Comparacao) and expr.ops == ["=="]:
            raise GaloSyntaxError(
                "G107", "Esta comparação é calculada, mas o resultado não é usado.", expr.line, expr.col, 1,
                "Para atribuir um valor, use um único '=': x = 5", self.filename,
            )
        if nxt.kind in (NL, ";", EOF) or nxt.kind in BLOCK_ENDERS:
            raise GaloSyntaxError(
                "G107", "Esta expressão é calculada, mas o resultado não é usado.", expr.line, expr.col, 1,
                "Para mostrar o resultado, use: mostre <expressão>", self.filename,
            )
        raise self.error("G101", f"Esperava o fim da instrução, mas encontrei {nxt.describe()}.", nxt)

    @staticmethod
    def _keyword_suggestion(key: str) -> str | None:
        if key in COMMON_MISTAKES:
            return COMMON_MISTAKES[key]
        options = {canonical(k): k for k in STATEMENT_KEYWORDS}
        found = difflib.get_close_matches(key, list(options), n=1, cutoff=0.75)
        return options[found[0]] if found else None

    # ------------------------------------------------------------ expressões

    def parse_expression(self):
        return self.parse_or()

    def parse_or(self):
        left = self.parse_and()
        while self.check("ou"):
            op = self.advance()
            self.skip_newlines_after_operator()
            right = self.parse_and()
            left = A.Logico(op.line, op.col, "ou", left, right)
        return left

    def parse_and(self):
        left = self.parse_not()
        while self.check("e"):
            op = self.advance()
            self.skip_newlines_after_operator()
            right = self.parse_not()
            left = A.Logico(op.line, op.col, "e", left, right)
        return left

    def parse_not(self):
        if self.check("não"):
            op = self.advance()
            operand = self.parse_not()
            return A.Unario(op.line, op.col, "não", operand)
        return self.parse_comparison()

    def parse_comparison(self):
        first = self.parse_additive()
        ops, operands, positions = [], [first], []
        while self.check(*COMPARISON_OPS):
            op = self.advance()
            self.skip_newlines_after_operator()
            ops.append(op.kind)
            positions.append((op.line, op.col))
            operands.append(self.parse_additive())
        if not ops:
            return first
        return A.Comparacao(positions[0][0], positions[0][1], ops, operands, positions)

    def parse_additive(self):
        left = self.parse_multiplicative()
        while self.check("+", "-"):
            op = self.advance()
            self.skip_newlines_after_operator()
            right = self.parse_multiplicative()
            left = A.Binario(op.line, op.col, op.kind, left, right)
        return left

    def parse_multiplicative(self):
        left = self.parse_unary()
        while self.check("*", "/", "//", "%"):
            op = self.advance()
            self.skip_newlines_after_operator()
            right = self.parse_unary()
            left = A.Binario(op.line, op.col, op.kind, left, right)
        return left

    def parse_unary(self):
        if self.check("-", "+"):
            op = self.advance()
            operand = self.parse_unary()
            if isinstance(operand, A.Literal) and type(operand.value) in (int, float):
                value = -operand.value if op.kind == "-" else operand.value
                return A.Literal(op.line, op.col, value)
            return A.Unario(op.line, op.col, op.kind, operand)
        return self.parse_power()

    def parse_power(self):
        base = self.parse_postfix()
        if self.check("^"):
            op = self.advance()
            self.skip_newlines_after_operator()
            exponent = self.parse_unary()
            return A.Binario(op.line, op.col, "^", base, exponent)
        return base

    def parse_postfix(self):
        expr = self.parse_primary()
        while True:
            tok = self.peek()
            if tok.kind == "(":
                self.advance()
                self.nl_ignore.append(True)
                args, kwargs = [], []
                while not self.check(")"):
                    t = self.peek()
                    if t.kind == NOME and self.peek(1).kind == ":":
                        self.advance()
                        self.advance()
                        if any(k.key == t.key for k in kwargs):
                            raise self.error("G102", f"O argumento '{t.text}' foi informado mais de uma vez.", t)
                        kwargs.append(A.ArgNomeado(t.line, t.col, t.text, t.key, self.parse_expression()))
                    else:
                        if kwargs:
                            raise self.error("G102", "Argumentos sem nome devem vir antes dos argumentos nomeados.", t,
                                             "criar(\"Ana\", idade: 30)")
                        args.append(self.parse_expression())
                    if not self.match(","):
                        break
                if not self.check(")"):
                    t = self.peek()
                    hint = "Separe os argumentos com vírgulas." if t.kind in EXPR_START else None
                    raise self.error("G102", f"Esperava ')' para fechar a chamada iniciada na linha {tok.line}, mas encontrei {t.describe()}.", t, hint)
                self.advance()
                self.nl_ignore.pop()
                expr = A.Chamada(expr.line, expr.col, expr, args, kwargs)
            elif tok.kind == "[":
                self.advance()
                self.nl_ignore.append(True)
                if self.check("]"):
                    raise self.error("G105", "Esperava a posição ou chave entre os colchetes.", None, "Exemplo: lista[1]")
                index = self.parse_expression()
                self.expect("]", "Esperava ']' para fechar o acesso por posição")
                self.nl_ignore.pop()
                expr = A.Indice(tok.line, tok.col, expr, index)
            elif tok.kind == ".":
                self.advance()
                t = self.peek()
                if t.kind != NOME and t.kind not in KEYWORDS:
                    raise self.error("G102", f"Esperava o nome de um campo depois de '.', mas encontrei {t.describe()}.", t,
                                     "Exemplo: pessoa.nome")
                self.advance()
                expr = A.Campo(t.line, t.col, expr, t.text)
            else:
                return expr

    def parse_primary(self):
        tok = self.peek()
        k = tok.kind
        if k == INTEIRO or k == DECIMAL:
            self.advance()
            return A.Literal(tok.line, tok.col, tok.value)
        if k == TEXTO:
            self.advance()
            return self._text(tok)
        if k == "verdadeiro":
            self.advance()
            return A.Literal(tok.line, tok.col, True)
        if k == "falso":
            self.advance()
            return A.Literal(tok.line, tok.col, False)
        if k == "nulo":
            self.advance()
            return A.Literal(tok.line, tok.col, None)
        if k == NOME:
            self.advance()
            return A.Nome(tok.line, tok.col, tok.text, tok.key, tok.length)
        if k == "(":
            self.advance()
            self.nl_ignore.append(True)
            expr = self.parse_expression()
            self.expect(")", f"Esperava ')' para fechar o parêntese aberto na linha {tok.line}")
            self.nl_ignore.pop()
            return expr
        if k == "[":
            return self.parse_list()
        if k == "{":
            return self.parse_map()
        if k == "função":
            return self.parse_anonymous_function()
        if k == "eu":
            self.advance()
            return A.Nome(tok.line, tok.col, tok.text, "eu", tok.length)
        if k == "se":
            self.advance()
            cond = self.parse_expression()
            self._expect_after_condition("então", "se")
            then = self.parse_expression()
            if not self.check("senão"):
                raise self.error(
                    "G102", f"Uma expressão 'se' precisa de 'senão' com o valor alternativo, mas encontrei {self.peek().describe()}.",
                    None, 'defina situação como se nota >= 6 então "aprovado" senão "reprovado"',
                )
            self.advance()
            return A.SeExpr(tok.line, tok.col, cond, then, self.parse_expression())
        if k in (NL, EOF, ";"):
            raise self.error("G105", f"A expressão está incompleta: esperava um valor, mas encontrei {tok.describe()}.", tok)
        if k == "=":
            raise self.error("G109", "Encontrei '=' onde esperava um valor. Para comparar, use '=='.", tok)
        if k in KEYWORDS or k in BLOCK_ENDERS:
            raise self.error("G105", f"Esperava um valor ou expressão antes de '{tok.text}'.", tok)
        raise self.error("G105", f"Esperava um valor ou expressão, mas encontrei {tok.describe()}.", tok)

    def _text(self, tok: Token):
        parts = []
        for p in tok.value:
            if isinstance(p, str):
                parts.append(p)
                continue
            assert isinstance(p, InterpPart)
            sub = Parser(p.tokens, self.filename)
            sub.nl_ignore = [True]
            expr = sub.parse_expression()
            if sub.peek().kind != EOF:
                raise sub.error("G105", "Uma interpolação '{...}' deve conter uma única expressão.", sub.peek())
            parts.append(expr)
        if all(isinstance(p, str) for p in parts):
            return A.Literal(tok.line, tok.col, "".join(parts))
        return A.TextoInterpolado(tok.line, tok.col, parts)

    def parse_list(self):
        lb = self.advance()
        self.nl_ignore.append(True)
        elements = []
        while not self.check("]"):
            elements.append(self.parse_expression())
            if not self.match(","):
                break
        if not self.check("]"):
            t = self.peek()
            hint = "Separe os elementos com vírgulas: [1, 2, 3]" if t.kind in EXPR_START else None
            raise self.error("G102", f"Esperava ']' para fechar a lista iniciada na linha {lb.line}, mas encontrei {t.describe()}.", t, hint)
        self.advance()
        self.nl_ignore.pop()
        return A.ListaLit(lb.line, lb.col, elements)

    def parse_map(self):
        lb = self.advance()
        self.nl_ignore.append(True)
        pairs = []
        while not self.check("}"):
            key = self.parse_expression()
            if isinstance(key, A.Nome):
                key.is_map_key = True
            if not self.check(":"):
                t = self.peek()
                raise self.error("G102", f"Esperava ':' entre a chave e o valor do mapa, mas encontrei {t.describe()}.", t,
                                 'Exemplo: {"nome": "Ana", "idade": 30}')
            self.advance()
            value = self.parse_expression()
            pairs.append((key, value))
            if not self.match(","):
                break
        if not self.check("}"):
            t = self.peek()
            hint = 'Separe os pares com vírgulas: {"a": 1, "b": 2}' if t.kind in EXPR_START else None
            raise self.error("G102", f"Esperava '}}' para fechar o mapa iniciado na linha {lb.line}, mas encontrei {t.describe()}.", t, hint)
        self.advance()
        self.nl_ignore.pop()
        return A.MapaLit(lb.line, lb.col, pairs)

    def parse_anonymous_function(self):
        kw = self.advance()
        if not self.check("("):
            raise self.error("G102", f"Esperava '(' depois de 'função', mas encontrei {self.peek().describe()}.", None,
                             "Uma função sem nome é escrita assim: função(x) retorne x * 2 fim")
        params = self.parse_params()
        ret = None
        if self.match("retorna"):
            ret = self.parse_type()
        self.nl_ignore.append(False)
        body = self.parse_block(("fim",), kw, "função")
        self.close_block(kw, "função")
        self.nl_ignore.pop()
        return A.FuncaoAnonima(kw.line, kw.col, params, ret, body)


def parse(tokens: list[Token], filename: str | None = None, repl: bool = False) -> A.Programa:
    return Parser(tokens, filename, repl).parse_program()
