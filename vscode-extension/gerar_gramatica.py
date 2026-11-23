"""Gera syntaxes/galo.tmLanguage.json a partir das definições reais da linguagem.

Uso (na raiz do repositório):  python3 vscode-extension/gerar_gramatica.py
"""

from __future__ import annotations

import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from galo.compiler.tokens import canonical  # noqa: E402
from galo.stdlib import BUILTINS, CONSTANTS  # noqa: E402

INICIO = r"(?<![\p{L}\p{N}_])"
FIM = r"(?![\p{L}\p{N}_])"


def alternativas(palavras) -> str:
    formas = set()
    for p in palavras:
        formas.add(p)
        formas.add(canonical(p))
    return "|".join(sorted(formas, key=lambda w: (-len(w), w)))


def palavra(palavras) -> str:
    return f"{INICIO}(?:{alternativas(palavras)}){FIM}"


CONTROLE = ["se", "então", "senão", "fim", "enquanto", "faça", "repita", "vezes", "para", "cada",
            "de", "até", "passo", "em", "retorne", "pare", "continue", "tente", "capture", "lance"]
DECLARACAO = ["defina", "constante", "função", "registro"]
OUTRAS = ["como", "retorna", "programa", "mostre", "importe"]
LOGICOS = ["e", "ou", "não"]
CONSTANTES = ["verdadeiro", "falso", "nulo"]
TIPOS = ["inteiro", "decimal", "número", "texto", "booleano", "lista", "mapa", "qualquer"]
NOME = r"[\p{L}_][\p{L}\p{N}_]*"


def gramatica() -> dict:
    internas = sorted({nf.name for nf in BUILTINS.values()} - set(TIPOS))
    return {
        "$schema": "https://raw.githubusercontent.com/martinring/tmlanguage/master/tmlanguage.json",
        "name": "GALO",
        "scopeName": "source.galo",
        "fileTypes": ["galo"],
        "patterns": [
            {"include": "#comentarios"},
            {"include": "#textos"},
            {"include": "#numeros"},
            {"include": "#declaracao-de-funcao"},
            {"include": "#declaracao-de-registro"},
            {"include": "#palavras-chave"},
            {"include": "#internas"},
            {"include": "#chamadas"},
            {"include": "#operadores"},
        ],
        "repository": {
            "comentarios": {"patterns": [
                {"include": "#comentario-de-bloco"},
                {"name": "comment.line.number-sign.galo", "match": r"#(?!\[).*$"},
            ]},
            "comentario-de-bloco": {
                "name": "comment.block.galo", "begin": r"#\[", "end": r"\]#",
                "patterns": [{"include": "#comentario-de-bloco"}],
            },
            "textos": {"patterns": [
                {"include": "#texto-multilinha"},
                {"include": "#texto-literal-multilinha"},
                {"include": "#texto-literal"},
                {"include": "#texto-simples"},
            ]},
            "texto-literal": {
                "name": "string.quoted.single.galo", "begin": "'", "end": "'|$",
                "patterns": [{"name": "constant.character.escape.galo", "match": r"\\'"}],
            },
            "texto-literal-multilinha": {
                "name": "string.quoted.single.block.galo", "begin": "'''", "end": "'''",
                "patterns": [{"name": "constant.character.escape.galo", "match": r"\\'"}],
            },
            "texto-multilinha": {
                "name": "string.quoted.double.block.galo", "begin": '"""', "end": '"""',
                "patterns": [{"include": "#conteudo-de-texto"}],
            },
            "texto-simples": {
                "name": "string.quoted.double.galo", "begin": '"', "end": '"|$',
                "patterns": [{"include": "#conteudo-de-texto"}],
            },
            "conteudo-de-texto": {
                "patterns": [
                    {"name": "constant.character.escape.galo", "match": r'\\(?:[ntr0"\\{}]|u[0-9a-fA-F]{4})'},
                    {"name": "invalid.illegal.escape.galo", "match": r"\\."},
                    {
                        "name": "meta.interpolation.galo", "begin": r"\{", "end": r"\}",
                        "beginCaptures": {"0": {"name": "punctuation.section.interpolation.begin.galo"}},
                        "endCaptures": {"0": {"name": "punctuation.section.interpolation.end.galo"}},
                        "contentName": "source.galo.embedded",
                        "patterns": [{"include": "$self"}],
                    },
                ],
            },
            "declaracao-de-registro": {
                "match": f"{INICIO}(registro){FIM}\\s+({NOME})",
                "captures": {"1": {"name": "storage.type.class.galo"}, "2": {"name": "entity.name.type.galo"}},
            },
            "numeros": {
                "name": "constant.numeric.galo",
                "match": r"(?<![\p{L}_])\d[\d_]*(?:\.\d[\d_]*)?(?:[eE][+-]?\d+)?",
            },
            "declaracao-de-funcao": {
                "match": f"{INICIO}(função|funcao){FIM}\\s+({NOME})",
                "captures": {"1": {"name": "storage.type.function.galo"}, "2": {"name": "entity.name.function.galo"}},
            },
            "palavras-chave": {"patterns": [
                {"name": "keyword.control.galo", "match": palavra(CONTROLE)},
                {"name": "storage.type.galo", "match": palavra(DECLARACAO)},
                {"name": "keyword.other.galo", "match": palavra(OUTRAS)},
                {"name": "keyword.other.type-annotation.galo", "match": f"{INICIO}do\\s+tipo{FIM}"},
                {"name": "keyword.operator.logical.galo", "match": palavra(LOGICOS)},
                {"name": "constant.language.galo", "match": palavra(CONSTANTES)},
                {"name": "variable.language.self.galo", "match": palavra(["eu"])},
                {"name": "support.type.galo", "match": palavra(TIPOS)},
                {"name": "support.constant.galo", "match": palavra([n for n, _, _ in CONSTANTS.values()])},
            ]},
            "internas": {
                "match": f"{INICIO}({alternativas(internas)}){FIM}(?=\\s*\\()",
                "captures": {"1": {"name": "support.function.builtin.galo"}},
            },
            "chamadas": {
                "match": f"({NOME})(?=\\s*\\()",
                "captures": {"1": {"name": "entity.name.function.call.galo"}},
            },
            "operadores": {"patterns": [
                {"name": "keyword.operator.assignment.compound.galo", "match": r"\+=|-=|\*=|/="},
                {"name": "keyword.operator.comparison.galo", "match": r"==|!=|<=|>=|<|>"},
                {"name": "keyword.operator.arithmetic.galo", "match": r"//|[-+*/%^]"},
                {"name": "keyword.operator.assignment.galo", "match": r"="},
                {"name": "punctuation.separator.galo", "match": r"[,;:.]"},
            ]},
        },
    }


if __name__ == "__main__":
    destino = os.path.join(AQUI, "syntaxes", "galo.tmLanguage.json")
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(gramatica(), f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"Gramática gravada em {destino}")
