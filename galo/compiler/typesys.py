"""Sistema de tipos estático (conservador) da GALO.

Um tipo estático é um frozenset de nomes de tipos básicos, ou None quando o
tipo é desconhecido ("qualquer"). O analisador só acusa erro quando tem
certeza: se qualquer combinação possível for válida, o código é aceito e a
verificação fica para a máquina virtual.
"""

from __future__ import annotations

from .tokens import canonical

BASE = ("inteiro", "decimal", "texto", "booleano", "lista", "mapa", "nulo", "função")
ALL = frozenset(BASE)

T_INT = frozenset({"inteiro"})
T_DEC = frozenset({"decimal"})
T_NUM = frozenset({"inteiro", "decimal"})
T_TEXTO = frozenset({"texto"})
T_BOOL = frozenset({"booleano"})
T_LISTA = frozenset({"lista"})
T_MAPA = frozenset({"mapa"})
T_NULO = frozenset({"nulo"})
T_FUNC = frozenset({"função"})
T_INDEXABLE = frozenset({"lista", "texto", "mapa"})
T_TIPO = frozenset({"tipo"})
T_MODULO = frozenset({"módulo"})
# Tipos que certamente não têm campos acessíveis com '.'
NO_FIELDS = frozenset({"inteiro", "decimal", "texto", "booleano", "lista", "nulo", "função", "tipo"})

TYPE_NAMES = {
    "inteiro": T_INT,
    "decimal": T_DEC,
    "numero": T_NUM,
    "texto": T_TEXTO,
    "booleano": T_BOOL,
    "lista": T_LISTA,
    "mapa": T_MAPA,
    "nulo": T_NULO,
    "funcao": T_FUNC,
    "qualquer": None,
}

DISPLAY_TYPE_NAMES = ("inteiro", "decimal", "número", "texto", "booleano", "lista", "mapa", "função", "nulo", "qualquer")


def type_of_python_value(v) -> frozenset:
    t = type(v)
    if t is bool:
        return T_BOOL
    if t is int:
        return T_INT
    if t is float:
        return T_DEC
    if t is str:
        return T_TEXTO
    if v is None:
        return T_NULO
    return None


def from_names(names) -> frozenset | None:
    if names is None:
        return None
    return frozenset(names)


def spec_tuple(spec: frozenset | None) -> tuple | None:
    """Forma ordenada (e serializável) de um tipo: tipos básicos na ordem de BASE, depois registros."""
    if spec is None:
        return None
    return tuple(n for n in BASE if n in spec) + tuple(sorted(n for n in spec if n not in ALL))


def compatible(value_types: frozenset | None, spec: frozenset | None) -> bool:
    """Algum dos tipos possíveis do valor é aceito pela anotação?"""
    if value_types is None or spec is None:
        return True
    for t in value_types:
        if t in spec or (t == "inteiro" and "decimal" in spec):
            return True
    return False


def lookup(key: str):
    """Tipo correspondente a um nome de tipo (canônico). KeyError se não existir."""
    return TYPE_NAMES[canonical(key)]


_NUMERIC = {
    ("inteiro", "inteiro"): T_INT,
    ("inteiro", "decimal"): T_DEC,
    ("decimal", "inteiro"): T_DEC,
    ("decimal", "decimal"): T_DEC,
}
_DIV = {k: T_DEC for k in _NUMERIC}
_POW = {
    ("inteiro", "inteiro"): T_NUM,
    ("inteiro", "decimal"): T_DEC,
    ("decimal", "inteiro"): T_DEC,
    ("decimal", "decimal"): T_DEC,
}

BINOP_RULES = {
    "+": {**_NUMERIC, ("texto", "texto"): T_TEXTO, ("lista", "lista"): T_LISTA},
    "-": dict(_NUMERIC),
    "*": {**_NUMERIC, ("texto", "inteiro"): T_TEXTO, ("inteiro", "texto"): T_TEXTO},
    "/": _DIV,
    "//": dict(_NUMERIC),
    "%": dict(_NUMERIC),
    "^": _POW,
}

ORDER_PAIRS = {(a, b) for a in ("inteiro", "decimal") for b in ("inteiro", "decimal")} | {("texto", "texto")}
