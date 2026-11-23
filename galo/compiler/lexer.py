"""Analisador léxico da GALO: transforma código-fonte em tokens."""

from __future__ import annotations

import unicodedata

from ..errors import GaloLexError
from .tokens import (
    DECIMAL, EOF, INTEIRO, KEYWORD_BY_KEY, NL, NOME, OPERATORS_1, OPERATORS_2,
    TEXTO, InterpPart, Token, canonical,
)

DIGITS = "0123456789"

ESCAPES = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    '"': '"',
    "\\": "\\",
    "{": "{",
    "}": "}",
    "0": "\0",
}


def _is_ident_start(c: str) -> bool:
    return c == "_" or c.isalpha()


def _is_ident_char(c: str) -> bool:
    if c == "_" or c.isalpha() or c in DIGITS:
        return True
    return unicodedata.category(c) in ("Mn", "Mc", "Nd")


def normalize_source(source: str) -> str:
    if source.startswith("﻿"):
        source = source[1:]
    source = source.replace("\r\n", "\n").replace("\r", "\n")
    return unicodedata.normalize("NFC", source)


class Lexer:
    def __init__(self, source: str, filename: str | None = None) -> None:
        self.src = normalize_source(source)
        self.n = len(self.src)
        self.i = 0
        self.line = 1
        self.col = 1
        self.filename = filename

    # -- utilidades ---------------------------------------------------------

    def _error(self, code, message, line=None, col=None, length=1, suggestion=None, incomplete=False):
        err = GaloLexError(
            code, message,
            line if line is not None else self.line,
            col if col is not None else self.col,
            length, suggestion, self.filename,
        )
        err.incomplete = incomplete
        return err

    def _peek(self, k: int = 0) -> str:
        j = self.i + k
        return self.src[j] if j < self.n else ""

    def _adv(self) -> str:
        c = self.src[self.i]
        self.i += 1
        if c == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return c

    # -- ponto de entrada ---------------------------------------------------

    def tokenize(self) -> list[Token]:
        return self._scan(in_interp=False)

    def _scan(self, in_interp: bool, opened_at: tuple[int, int] | None = None) -> list[Token]:
        toks: list[Token] = []
        depth = 0
        bol = not in_interp
        while True:
            if self.i >= self.n:
                if in_interp:
                    line, col = opened_at or (None, None)
                    raise self._error(
                        "G005", "A interpolação iniciada com '{' não foi fechada com '}'.", line, col,
                        suggestion="Feche a expressão com '}' antes das aspas finais.",
                    )
                break
            c = self.src[self.i]
            if c == " " or c == "\t":
                self._adv()
                continue
            if c == "\n":
                if in_interp:
                    raise self._error(
                        "G005", "A interpolação '{...}' precisa ser fechada na mesma linha.",
                        suggestion="Feche a expressão com '}' e o texto com aspas na mesma linha.",
                    )
                if toks and toks[-1].kind != NL:
                    toks.append(Token(NL, None, self.line, self.col, 1))
                self._adv()
                bol = True
                continue
            if c == "#":
                if in_interp:
                    raise self._error("G005", "Comentários não são permitidos dentro de uma interpolação '{...}'.")
                self._comment()
                continue

            if c in DIGITS:
                tok = self._number()
            elif c == "'":
                tok = self._string("'")
            elif c == '"':
                if in_interp:
                    try:
                        tok = self._string()
                    except GaloLexError as err:
                        if err.code != "G002" or opened_at is None:
                            raise
                        raise self._error(
                            "G005", "A interpolação iniciada com '{' não foi fechada com '}'.",
                            opened_at[0], opened_at[1], 1,
                            suggestion="Feche a expressão com '}' antes das aspas finais. "
                                       "Para escrever uma chave literal, use \\{.",
                        ) from None
                else:
                    tok = self._string()
            elif _is_ident_start(c):
                tok = self._word()
            else:
                if in_interp and c == "}" and depth == 0:
                    self._adv()
                    toks.append(Token(EOF, None, self.line, self.col, 1))
                    return toks
                tok = self._operator()
                if in_interp:
                    if tok.kind == "{":
                        depth += 1
                    elif tok.kind == "}":
                        depth -= 1
            tok.bol = bol
            bol = False
            toks.append(tok)

        if toks and toks[-1].kind != NL:
            toks.append(Token(NL, None, self.line, self.col, 1))
        toks.append(Token(EOF, None, self.line, self.col, 1))
        return toks

    # -- comentários --------------------------------------------------------

    def _comment(self) -> None:
        if self._peek(1) == "[":
            start_line, start_col = self.line, self.col
            self._adv()
            self._adv()
            depth = 1
            while depth > 0:
                if self.i >= self.n:
                    raise self._error(
                        "G006", "O comentário de bloco iniciado com '#[' não foi fechado.",
                        start_line, start_col, 2,
                        suggestion="Feche o comentário com ']#'.", incomplete=True,
                    )
                if self._peek() == "#" and self._peek(1) == "[":
                    self._adv(); self._adv()
                    depth += 1
                elif self._peek() == "]" and self._peek(1) == "#":
                    self._adv(); self._adv()
                    depth -= 1
                else:
                    self._adv()
            return
        while self.i < self.n and self.src[self.i] != "\n":
            self._adv()

    # -- números ------------------------------------------------------------

    def _digits(self) -> None:
        while True:
            c = self._peek()
            if c in DIGITS and c:
                self._adv()
            elif c == "_" and self._peek(1) in DIGITS and self._peek(1):
                self._adv()
            else:
                return

    def _number(self) -> Token:
        start, line, col = self.i, self.line, self.col
        self._digits()
        is_dec = False
        if self._peek() == "." and self._peek(1) and self._peek(1) in DIGITS:
            self._adv()
            self._digits()
            is_dec = True
        elif self._peek() == "." and not (_is_ident_start(self._peek(1) or "0")):
            text = self.src[start:self.i]
            raise self._error(
                "G003", f"Número decimal incompleto: '{text}.'.", line, col, len(text) + 1,
                suggestion=f"Escreva os dígitos depois do ponto, por exemplo: {text}.0",
            )
        c = self._peek()
        if c in ("e", "E") and c:
            nxt = self._peek(1)
            if (nxt and nxt in DIGITS) or (nxt in ("+", "-") and nxt and self._peek(2) and self._peek(2) in DIGITS):
                self._adv()
                if self._peek() in ("+", "-"):
                    self._adv()
                self._digits()
                is_dec = True
        c = self._peek()
        if c and (_is_ident_char(c)):
            while self._peek() and _is_ident_char(self._peek()):
                self._adv()
            text = self.src[start:self.i]
            raise self._error(
                "G003", f"Número malformado: '{text}'.", line, col, len(text),
                suggestion="Nomes de variáveis não podem começar com dígitos, e números não podem conter letras.",
            )
        text = self.src[start:self.i]
        if "__" in text or text.endswith("_"):
            raise self._error("G003", f"Número malformado: '{text}'.", line, col, len(text),
                              suggestion="Use '_' apenas entre dígitos, como em 1_000_000.")
        clean = text.replace("_", "")
        if is_dec:
            return Token(DECIMAL, float(clean), line, col, len(text), text=text)
        return Token(INTEIRO, int(clean), line, col, len(text), text=text)

    # -- textos -------------------------------------------------------------
    #
    # "..." e \"\"\"...\"\"\" aceitam interpolação {expressão} e escapes (\n, \t...).
    # '...' e '''...''' são textos literais: nada é especial, exceto \' (a própria aspa).

    def _long_string_indent(self, delim: str) -> int:
        """Recuo comum de um texto multilinha, calculado pelas linhas do código-fonte.

        Considera as linhas depois da primeira (a das aspas de abertura), inclusive a
        linha das aspas de fechamento: assim a posição das aspas finais define o recuo.
        """
        j = self.i + 3
        while j < self.n and not (self.src.startswith(delim, j) and self.src[j - 1] != "\\"):
            j += 1
        body = self.src[self.i + 3:j]
        lines = body.split("\n")[1:]
        indents = []
        for k, ln in enumerate(lines):
            stripped = ln.lstrip(" \t")
            if stripped or k == len(lines) - 1:
                indents.append(len(ln) - len(stripped))
        return min(indents) if indents else 0

    def _interpolation(self, parts: list, buf: list) -> None:
        bline, bcol = self.line, self.col
        self._adv()
        if buf:
            parts.append("".join(buf))
            buf.clear()
        sub = self._scan(in_interp=True, opened_at=(bline, bcol))
        if len(sub) == 1:
            raise self._error(
                "G005", "Interpolação vazia: '{}' precisa conter uma expressão.", bline, bcol, 2,
                suggestion="Coloque uma expressão entre as chaves, como {nome}, escreva \\{ para mostrar uma chave "
                           "ou use aspas simples ('...') para um texto sem interpolação.",
            )
        parts.append(InterpPart(sub, bline, bcol + 1))

    def _long_string(self, quote: str) -> Token:
        delim = quote * 3
        interpolate = quote == '"'
        line, col = self.line, self.col
        indent = self._long_string_indent(delim)
        for _ in range(3):
            self._adv()
        parts: list = []
        buf: list[str] = []
        # A quebra de linha logo depois das aspas de abertura não faz parte do texto.
        k = self.i
        while k < self.n and self.src[k] in " \t":
            k += 1
        if k < self.n and self.src[k] == "\n":
            while self.i <= k:
                self._adv()
            self._skip_indent(indent)
        line_start = 0
        while True:
            if self.i >= self.n:
                raise self._error(
                    "G002", f"O texto multilinha iniciado na linha {line}, coluna {col} não foi fechado.",
                    line, col, 3, suggestion=f"Feche o texto com três aspas: {delim}", incomplete=True,
                )
            if self.src.startswith(delim, self.i):
                for _ in range(3):
                    self._adv()
                # Linha final só com espaços (antes das aspas de fechamento) não é conteúdo.
                if all(ch in " \t" for ch in buf[line_start:]):
                    del buf[line_start:]
                break
            c = self._peek()
            if c == "\n":
                buf.append(self._adv())
                self._skip_indent(indent)
                line_start = len(buf)
                continue
            if c == "\\":
                if interpolate:
                    self._escape(buf)
                else:
                    self._raw_backslash(buf, quote)
                continue
            if c == "{" and interpolate:
                self._interpolation(parts, buf)
                line_start = 0
                continue
            buf.append(self._adv())
        if buf or not parts:
            parts.append("".join(buf))
        return Token(TEXTO, parts, line, col, 3, text=delim)

    def _raw_backslash(self, buf: list, quote: str) -> None:
        """Em textos com aspas simples a barra é literal; só \' representa a própria aspa."""
        self._adv()
        if self._peek() == quote:
            buf.append(self._adv())
        else:
            buf.append("\\")

    def _skip_indent(self, indent: int) -> None:
        skipped = 0
        while skipped < indent and self.i < self.n and self.src[self.i] in " \t":
            self._adv()
            skipped += 1

    def _escape(self, buf: list) -> None:
        eline, ecol = self.line, self.col
        self._adv()
        e = self._peek()
        if e == "'":
            self._adv()
            buf.append("'")
        elif e in ESCAPES and e:
            self._adv()
            buf.append(ESCAPES[e])
        elif e == "u":
            self._adv()
            hexa = self.src[self.i:self.i + 4]
            if len(hexa) == 4 and all(h in "0123456789abcdefABCDEF" for h in hexa):
                for _ in range(4):
                    self._adv()
                buf.append(chr(int(hexa, 16)))
            else:
                raise self._error("G004", "Sequência '\\u' deve ser seguida de 4 dígitos hexadecimais.",
                                  eline, ecol, 2, suggestion="Exemplo: \\u00e9 representa 'é'.")
        else:
            raise self._error(
                "G004", f"Sequência de escape inválida: '\\{e}'.", eline, ecol, 2,
                suggestion='Sequências válidas: \\n (nova linha), \\t (tabulação), \\" e \\\' (aspas), '
                           '\\\\ (barra), \\{ e \\} (chaves), \\uXXXX (caractere Unicode).',
            )

    def _string(self, quote: str = '"') -> Token:
        if self.src.startswith(quote * 3, self.i):
            return self._long_string(quote)
        interpolate = quote == '"'
        start, line, col = self.i, self.line, self.col
        self._adv()  # aspas de abertura
        parts: list = []
        buf: list[str] = []
        while True:
            if self.i >= self.n or self._peek() == "\n":
                raise self._error(
                    "G002", f"O texto iniciado na linha {line}, coluna {col} não foi fechado.",
                    line, col, max(1, self.i - start),
                    suggestion=f"Feche o texto com aspas ({quote}) na mesma linha. Para quebrar linhas dentro do texto, "
                               f"use \\n ou um texto de várias linhas entre {quote * 3}.",
                )
            c = self._peek()
            if c == quote:
                self._adv()
                break
            if c == "\\":
                if interpolate:
                    self._escape(buf)
                else:
                    self._raw_backslash(buf, quote)
                continue
            if c == "{" and interpolate:
                self._interpolation(parts, buf)
                continue
            buf.append(self._adv())
        if buf or not parts:
            parts.append("".join(buf))
        return Token(TEXTO, parts, line, col, self.i - start, text=self.src[start:self.i])

    # -- palavras -----------------------------------------------------------

    def _word(self) -> Token:
        start, line, col = self.i, self.line, self.col
        while self.i < self.n and _is_ident_char(self.src[self.i]):
            self._adv()
        text = self.src[start:self.i]
        key = canonical(text)
        kw = KEYWORD_BY_KEY.get(key)
        if kw is not None:
            return Token(kw, text, line, col, len(text), key=key, text=text)
        return Token(NOME, text, line, col, len(text), key=key, text=text)

    # -- operadores ---------------------------------------------------------

    def _operator(self) -> Token:
        line, col = self.line, self.col
        two = self.src[self.i:self.i + 2]
        if two in OPERATORS_2:
            self._adv(); self._adv()
            return Token(two, two, line, col, 2, text=two)
        if two == "&&":
            raise self._error("G007", "O operador '&&' não existe em GALO.", line, col, 2,
                              suggestion="Use a palavra 'e': se a > 0 e b > 0 então")
        if two == "||":
            raise self._error("G007", "O operador '||' não existe em GALO.", line, col, 2,
                              suggestion="Use a palavra 'ou': se a > 0 ou b > 0 então")
        c = self.src[self.i]
        if c in OPERATORS_1:
            self._adv()
            return Token(c, c, line, col, 1, text=c)
        if c == "!":
            raise self._error("G007", "O símbolo '!' não existe sozinho em GALO.", line, col, 1,
                              suggestion="Use 'não' para negar (não pronto) e '!=' para 'diferente de'.")
        if c in "&|":
            raise self._error("G007", f"O símbolo '{c}' não existe em GALO.", line, col, 1,
                              suggestion="Use as palavras 'e' e 'ou' para combinar condições.")
        if c in "“”„«»":
            raise self._error("G001", f"Aspas tipográficas '{c}' não são reconhecidas.", line, col, 1,
                              suggestion='Use aspas retas ("), como as do teclado. Editores de texto às vezes trocam as aspas automaticamente.')
        try:
            name = unicodedata.name(c)
        except ValueError:
            name = "sem nome"
        raise self._error("G001", f"Caractere inválido '{c}' (U+{ord(c):04X}, {name}).", line, col, 1,
                          suggestion="Remova este caractere ou coloque-o dentro de um texto entre aspas.")


def tokenize(source: str, filename: str | None = None) -> list[Token]:
    return Lexer(source, filename).tokenize()
