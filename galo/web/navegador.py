"""Ponte para compilar programas GALO dentro do navegador (Pyodide).

O site estático (GitHub Pages) não tem servidor: o compilador da GALO roda no próprio
navegador, no Pyodide (Python em WebAssembly), e responde no mesmo formato de
`compilar_programa()` — o que o servidor GALO devolveria em /api/compilar.
"""

from __future__ import annotations

import json

LIMITE_CODIGO = 20000


def compilar_json(pedido_json: str) -> tuple[int, str]:
    """Recebe o corpo JSON de /api/compilar e devolve (status HTTP, corpo JSON)."""
    from ..stdlib.dados_json import codificar
    from ..stdlib.programas import compilar_programa

    try:
        pedido = json.loads(pedido_json)
    except ValueError:
        pedido = None
    codigo = pedido.get("código") if isinstance(pedido, dict) else None
    if not isinstance(codigo, str):
        return 400, json.dumps({"erro": 'Envie um JSON com o campo "código" (um texto).'}, ensure_ascii=False)
    if len(codigo) > LIMITE_CODIGO:
        return 413, json.dumps({"erro": f"O programa passou de {LIMITE_CODIGO} caracteres. "
                                        "Que tal dividir em partes menores?"}, ensure_ascii=False)
    return 200, codificar(compilar_programa(None, codigo, "programa.galo"))
