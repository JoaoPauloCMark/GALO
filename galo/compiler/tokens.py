"""Definição dos tokens da GALO."""

from __future__ import annotations

from dataclasses import dataclass

from ..names import canonical  # noqa: F401  (reexportado para o restante do compilador)

# Palavras reservadas: não podem ser usadas como nomes.
KEYWORDS = (
    "programa", "defina", "constante", "como", "mostre",
    "se", "então", "senão", "fim",
    "enquanto", "faça", "repita", "para", "em",
    "função", "retorna", "retorne", "pare", "continue",
    "tente", "capture", "lance",
    "e", "ou", "não",
    "verdadeiro", "falso", "nulo",
    "importe", "registro", "eu",
)

KEYWORD_BY_KEY = {canonical(k): k for k in KEYWORDS}

# Palavras contextuais: só têm significado especial em posições específicas
# (ex.: `passo` em `para i de 1 até 10 passo 2`) e podem ser usadas como nomes.
CONTEXTUAL_WORDS = ("cada", "de", "até", "passo", "vezes", "do", "tipo")

# Palavras que iniciam instruções (usadas para sugerir correções de digitação).
STATEMENT_KEYWORDS = (
    "defina", "constante", "mostre", "se", "enquanto", "repita", "para",
    "função", "retorne", "pare", "continue", "tente", "lance", "programa",
    "importe", "registro",
)

# Palavras que encerram blocos.
BLOCK_ENDERS = ("fim", "senão", "capture")

# Categorias de token (os demais tipos são a própria palavra-chave ou símbolo).
NOME = "NOME"
INTEIRO = "INTEIRO"
DECIMAL = "DECIMAL"
TEXTO = "TEXTO"
NL = "NL"
EOF = "EOF"

OPERATORS_2 = ("//", "==", "!=", "<=", ">=", "+=", "-=", "*=", "/=")
OPERATORS_1 = "+-*/%^<>=()[]{},:.;"


@dataclass(slots=True)
class InterpPart:
    """Trecho `{expressão}` dentro de um texto: já tokenizado."""

    tokens: list
    line: int
    col: int


@dataclass(slots=True)
class Token:
    kind: str
    value: object
    line: int
    col: int
    length: int = 1
    key: str = ""
    text: str = ""
    bol: bool = False  # primeiro token da linha

    def describe(self) -> str:
        """Descrição legível, usada nas mensagens de erro."""
        k = self.kind
        if k == NOME:
            return f'o nome "{self.text}"'
        if k in (INTEIRO, DECIMAL):
            return f"o número {self.text}"
        if k == TEXTO:
            return "um texto entre aspas"
        if k == NL:
            return "o fim da linha"
        if k == EOF:
            return "o fim do arquivo"
        if k in KEYWORDS:
            return f'a palavra "{self.text or k}"'
        return f'o símbolo "{k}"'

    def __repr__(self) -> str:  # pragma: no cover
        return f"Token({self.kind!r}, {self.value!r}, {self.line}:{self.col})"
