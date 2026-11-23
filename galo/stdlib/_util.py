"""Utilidades para validar argumentos das funções internas."""

from __future__ import annotations

import re

from ..errors import GaloRuntimeError
from ..runtime.values import GaloMapa, article, describe_types, type_name


def erro(code: str, message: str, suggestion: str | None = None) -> GaloRuntimeError:
    return GaloRuntimeError(code, message, suggestion=suggestion)


def exige(fname: str, pos: int, value, *types: str):
    tn = type_name(value)
    if tn in types:
        return value
    if tn == "inteiro" and "decimal" in types:
        return float(value)
    raise erro("G322", f"A função {fname}() espera {describe_types(types)} no argumento {pos}, "
                       f"mas recebeu {article(tn)}.")


def exige_inteiro(fname, pos, v):
    return exige(fname, pos, v, "inteiro")


def exige_numero(fname, pos, v):
    tn = type_name(v)
    if tn in ("inteiro", "decimal"):
        return v
    raise erro("G322", f"A função {fname}() espera um número no argumento {pos}, mas recebeu {article(tn)}.")


def exige_texto(fname, pos, v):
    return exige(fname, pos, v, "texto")


def exige_lista(fname, pos, v):
    return exige(fname, pos, v, "lista")


def exige_mapa(fname, pos, v):
    return exige(fname, pos, v, "mapa")


def exige_funcao(fname, pos, v):
    return exige(fname, pos, v, "função")


_INT_RE = re.compile(r"[+-]?[0-9]+(?:_[0-9]+)*")
_DEC_RE = re.compile(r"[+-]?(?:[0-9]+\.[0-9]*|\.[0-9]+|[0-9]+)(?:[eE][+-]?[0-9]+)?")


def parse_number(s: str):
    """Converte texto em inteiro ou decimal; devolve None se não for número.

    Aceita vírgula como separador decimal quando o texto não contém ponto
    ("3,5" -> 3.5), para facilitar a leitura de valores digitados no Brasil.
    """
    s = s.strip()
    if not s:
        return None
    if _INT_RE.fullmatch(s):
        return int(s.replace("_", ""))
    if "," in s and "." not in s and s.count(",") == 1:
        s = s.replace(",", ".")
    if _DEC_RE.fullmatch(s):
        try:
            return float(s)
        except ValueError:
            return None
    return None


def as_items(colecao):
    """Elementos de uma lista ou de vários argumentos."""
    if type(colecao) is list:
        return colecao
    if type(colecao) is GaloMapa:
        return colecao.keys()
    return None


def arredondar_comercial(numero, casas: int):
    """Arredonda (metade para longe do zero) a forma decimal exata do número.

    Usa precisão suficiente para o tamanho do número, para que valores enormes
    (como 1e300) também possam ser formatados.
    """
    from decimal import ROUND_HALF_UP, Context, Decimal

    d = Decimal(repr(numero) if type(numero) is float else numero)
    precisao = max(d.adjusted() + 1, 1) + casas + 2
    resultado = d.quantize(Decimal(1).scaleb(-casas), rounding=ROUND_HALF_UP, context=Context(prec=precisao))
    return resultado.copy_abs() if resultado == 0 else resultado  # zero nunca é exibido com sinal
