"""Espaço de nomes interno da máquina virtual.

Reúne as funções internas e constantes registradas pela biblioteca padrão
(galo/stdlib) no dicionário consultado pela instrução LOAD_GLOBAL quando um
nome não é uma variável global do programa. Somente valores GALO entram aqui:
nenhum objeto ou módulo do Python fica acessível aos programas.
"""

from __future__ import annotations

from ..stdlib import BUILTINS, CONSTANTS


def builtin_namespace() -> dict:
    namespace: dict = dict(BUILTINS)
    for key, (_, value, _) in CONSTANTS.items():
        namespace[key] = value
    return namespace
