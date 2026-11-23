"""Registro das funções internas da GALO.

Cada função interna é uma função Python decorada com @nativa. O primeiro
parâmetro é sempre a máquina virtual (que dá acesso à entrada/saída e
permite chamar funções GALO, como em mapear(lista, f)). Os demais
parâmetros são os argumentos recebidos do programa GALO.

O nome registrado é canônico (sem acentos), então `maiúsculas` e
`maiusculas` chamam a mesma função.
"""

from __future__ import annotations

import inspect

from ..names import canonical
from ..runtime.values import NativeFunction

BUILTINS: dict[str, NativeFunction] = {}
CONSTANTS: dict[str, tuple[str, object, str]] = {}

_TYPE_EXPANSION = {"número": ("inteiro", "decimal"), "qualquer": None}


def _parse_returns(spec: str | None):
    if spec is None:
        return None
    names: list[str] = []
    for part in spec.split(" ou "):
        part = part.strip()
        expanded = _TYPE_EXPANSION.get(part, (part,))
        if expanded is None:
            return None
        names.extend(expanded)
    return tuple(names)


def nativa(nome: str, retorna: str | None = None, assinatura: str | None = None):
    def decorate(fn):
        params = list(inspect.signature(fn).parameters.values())[1:]
        min_args = sum(1 for p in params if p.kind == p.POSITIONAL_OR_KEYWORD and p.default is p.empty)
        variadic = any(p.kind == p.VAR_POSITIONAL for p in params)
        max_args = None if variadic else len(params)
        if assinatura is None:
            shown = []
            for p in params:
                if p.kind == p.VAR_POSITIONAL:
                    shown.append(f"{p.name}...")
                elif p.default is not p.empty:
                    shown.append(f"[{p.name}]")
                else:
                    shown.append(p.name)
            sig = f"{nome}({', '.join(shown)})"
        else:
            sig = assinatura
        native = NativeFunction(nome, fn, min_args, max_args, _parse_returns(retorna),
                                inspect.getdoc(fn) or "", sig)
        key = canonical(nome)
        if key in BUILTINS:
            raise RuntimeError(f"função interna duplicada: {nome}")
        BUILTINS[key] = native
        return fn

    return decorate


def constante(nome: str, valor, doc: str = "") -> None:
    CONSTANTS[canonical(nome)] = (nome, valor, doc)
