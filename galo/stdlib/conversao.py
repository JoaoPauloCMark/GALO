"""Conversão entre tipos."""

from __future__ import annotations

import math

from ..runtime.values import article, display, repr_value, type_name
from ._util import erro, parse_number
from .registry import nativa


@nativa("texto", retorna="texto")
def texto(vm, valor):
    """Converte qualquer valor em texto (a mesma forma usada por `mostre`)."""
    return display(valor)


@nativa("inteiro", retorna="inteiro")
def inteiro(vm, valor):
    """Converte em inteiro. Decimais são truncados (a parte fracionária é descartada);
    textos precisam conter um número inteiro, como "42"."""
    t = type(valor)
    if t is int:
        return valor
    if t is float:
        if math.isnan(valor) or math.isinf(valor):
            raise erro("G312", "Não é possível converter um valor infinito ou indefinido em inteiro.")
        return int(valor)
    if t is bool:
        return 1 if valor else 0
    if t is str:
        n = parse_number(valor)
        if type(n) is int:
            return n
        if type(n) is float:
            raise erro("G312", f"O texto {repr_value(valor)} representa um número decimal, não um inteiro.",
                       "Use decimal(...) para obter o número decimal, ou arredondar(número(...)).")
        raise erro("G312", f"Não foi possível converter o texto {repr_value(valor)} em inteiro.",
                   "Verifique se o texto contém apenas dígitos, como \"42\". Use é_número(texto) para validar antes.")
    raise erro("G312", f"Não é possível converter {article(type_name(valor))} em inteiro.")


@nativa("decimal", retorna="decimal")
def decimal(vm, valor):
    """Converte em número decimal. Aceita textos como "3.5" ou "3,5"."""
    t = type(valor)
    if t is float:
        return valor
    if t is int:
        try:
            return float(valor)
        except OverflowError:
            raise erro("G317", "O inteiro é grande demais para ser representado como decimal.")
    if t is str:
        n = parse_number(valor)
        if n is None:
            raise erro("G312", f"Não foi possível converter o texto {repr_value(valor)} em decimal.",
                       "Use um texto como \"3.5\" ou \"3,5\". Use é_número(texto) para validar antes.")
        return float(n)
    raise erro("G312", f"Não é possível converter {article(type_name(valor))} em decimal.")


@nativa("número", retorna="número")
def numero(vm, valor):
    """Converte um texto em inteiro ou decimal, conforme o conteúdo ("42" -> 42, "3,5" -> 3.5)."""
    t = type(valor)
    if t is int or t is float:
        return valor
    if t is str:
        n = parse_number(valor)
        if n is None:
            raise erro("G312", f"Não foi possível converter o texto {repr_value(valor)} em número.",
                       "Use é_número(texto) para verificar antes de converter.")
        return n
    raise erro("G312", f"Não é possível converter {article(type_name(valor))} em número.")


@nativa("booleano", retorna="booleano")
def booleano(vm, valor):
    """Converte os textos "verdadeiro" e "falso" em booleano."""
    if type(valor) is bool:
        return valor
    if type(valor) is str:
        s = valor.strip().lower()
        if s == "verdadeiro":
            return True
        if s == "falso":
            return False
        raise erro("G312", f"Não foi possível converter o texto {repr_value(valor)} em booleano.",
                   'Apenas os textos "verdadeiro" e "falso" podem ser convertidos.')
    raise erro("G312", f"Não é possível converter {article(type_name(valor))} em booleano.",
               "Para testar um número, use uma comparação, como x != 0.")


@nativa("tipo", retorna="texto")
def tipo(vm, valor):
    """Nome do tipo do valor: "inteiro", "decimal", "texto", "booleano", "lista", "mapa", "nulo" ou "função"."""
    return type_name(valor)
