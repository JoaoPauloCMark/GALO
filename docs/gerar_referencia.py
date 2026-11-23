"""Gera docs/biblioteca-padrao.md a partir das funções internas registradas.

Uso (na raiz do repositório):  python3 docs/gerar_referencia.py
"""

from __future__ import annotations

import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from galo.runtime.values import describe_spec  # noqa: E402
from galo.stdlib import BUILTINS, CONSTANTS  # noqa: E402

AREAS = [
    ("entrada_saida", "Entrada e saída"),
    ("texto", "Texto"),
    ("matematica", "Matemática"),
    ("colecoes", "Listas e mapas"),
    ("conversao", "Conversão de tipos"),
    ("dados_json", "JSON"),
    ("arquivos", "Arquivos"),
    ("tempo", "Data e hora"),
    ("sistema", "Sistema"),
    ("seguranca", "Segurança e codificação"),
    ("banco", "Banco de dados (SQLite)"),
    ("modelos", "Modelos HTML"),
    ("web", "Web: servidor e cliente HTTP"),
    ("navegador", "Página (somente no navegador)"),
    ("programas", "GALO dentro da GALO: compilar e executar programas"),
]


def _somente_servidor() -> set[str]:
    """Nomes que a VM do navegador (galo.js) não oferece."""
    import re

    from galo.names import canonical

    with open(os.path.join(os.path.dirname(AQUI), "galo", "web", "galo.js"), encoding="utf-8") as f:
        bloco = re.search(r"const SOMENTE_SERVIDOR = new Set\(\[(.*?)\]", f.read(), re.S).group(1)
    return {canonical(n) for n in re.findall(r"'([^']+)'", bloco)}


def gerar() -> str:
    linhas = [
        "# Biblioteca padrão da GALO",
        "",
        "> Arquivo gerado por `docs/gerar_referencia.py` a partir das funções registradas na",
        "> implementação. Não edite à mão.",
        "",
        "Todos os nomes podem ser escritos com ou sem acentos (`maiúsculas` ou `maiusculas`).",
        "Argumentos entre colchetes são opcionais. Posições de listas e textos começam em 1.",
        "A instrução `mostre` não é uma função: veja a [especificação](language-spec.md).",
        "Funções marcadas com *(só no servidor)* não existem na VM do navegador; as da seção",
        "*Página* só existem no navegador. Todo o resto funciona igual nos dois lugares.",
        "",
    ]
    servidor = _somente_servidor()
    por_area: dict[str, list] = {}
    for nf in BUILTINS.values():
        area = nf.fn.__module__.rsplit(".", 1)[-1]
        por_area.setdefault(area, []).append(nf)
    total = 0
    for chave, titulo in AREAS:
        funcoes = sorted(por_area.get(chave, []), key=lambda f: f.key)
        if not funcoes:
            continue
        linhas += [f"## {titulo}", ""]
        for nf in funcoes:
            total += 1
            retorno = f" → `{describe_spec(nf.returns)}`" if nf.returns else ""
            onde = " *(só no servidor)*" if nf.key in servidor else ""
            linhas.append(f"### `{nf.signature}`{retorno}{onde}")
            linhas.append("")
            linhas.append(" ".join(nf.doc.split()))
            linhas.append("")
        if chave == "matematica":
            for nome, valor, doc in CONSTANTS.values():
                linhas += [f"### `{nome}` (constante)", "", doc, ""]
    linhas.insert(8, f"São {total} funções internas e {len(CONSTANTS)} constante(s).")
    return "\n".join(linhas).rstrip() + "\n"


if __name__ == "__main__":
    destino = os.path.join(AQUI, "biblioteca-padrao.md")
    with open(destino, "w", encoding="utf-8") as f:
        f.write(gerar())
    print(f"Referência gravada em {destino}")
