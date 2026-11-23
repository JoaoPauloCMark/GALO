"""GALO dentro da GALO: compilar e executar outros programas.

O servidor compila (compilar_programa) e o navegador executa (executar_programa), isolado
num Web Worker, com limite de tempo e de saída. É assim que um "playground" é feito em GALO
sem executar no servidor o código de quem visita a página.
"""

from __future__ import annotations

import base64

from ..runtime.values import GaloMapa
from ._util import erro, exige_texto
from .registry import nativa

LIMITE_CODIGO = 200_000  # caracteres


def _diagnostico(e, fontes: dict) -> GaloMapa:
    from ..errors import format_diagnostic

    return GaloMapa.from_pairs([
        ("código", e.code),
        ("tipo", e.kind),
        ("gravidade", "aviso" if e.is_warning else "erro"),
        ("mensagem", e.message),
        ("sugestão", e.suggestion),
        ("linha", e.line),
        ("coluna", e.col),
        ("comprimento", e.length),
        ("texto", format_diagnostic(e, fontes.get(e.file))),
    ])


@nativa("compilar_programa", retorna="mapa", assinatura="compilar_programa(código, [nome])")
def compilar_programa(vm, codigo, nome="programa.galo"):
    """Compila código GALO (um texto) sem executá-lo. Devolve um mapa com ok (booleano), bytecode
    (o programa compilado, em base64, pronto para executar_programa no navegador), erros e avisos
    (listas de mapas com código, tipo, mensagem, sugestão, linha, coluna e texto — a mensagem
    completa, como no terminal). O código não pode usar importe: compilar nunca lê arquivos do
    servidor."""
    from ..compiler import ModuleLoader, compile_source
    from ..compiler.bytecode import dump_module
    from ..errors import CompilationError, GaloSemanticError

    exige_texto("compilar_programa", 1, codigo)
    exige_texto("compilar_programa", 2, nome)
    if len(codigo) > LIMITE_CODIGO:
        raise erro("G322", f"O código tem {len(codigo)} caracteres; compilar_programa() aceita até {LIMITE_CODIGO}.")

    class SemImportacoes(ModuleLoader):
        def load(self, path_text, importer_dir, node, importer_file):
            raise CompilationError([GaloSemanticError(
                "G220", f'Este programa não pode importar módulos (importe "{path_text}").', node.line, node.col, 7,
                "Programas compilados com compilar_programa() ficam em um único arquivo.", importer_file)])

    carregador = SemImportacoes(".")
    try:
        resultado = compile_source(codigo, nome, loader=carregador)
    except CompilationError as exc:
        fontes = getattr(exc, "sources", {}) or {nome: codigo}
        return GaloMapa.from_pairs([
            ("ok", False), ("bytecode", None),
            ("erros", [_diagnostico(e, fontes) for e in exc.errors]),
            ("avisos", [_diagnostico(e, fontes) for e in exc.warnings]),
        ])
    except RecursionError:
        return GaloMapa.from_pairs([
            ("ok", False), ("bytecode", None),
            ("erros", [GaloMapa.from_pairs([
                ("código", "G105"), ("tipo", "erro sintático"), ("gravidade", "erro"),
                ("mensagem", "O programa tem expressões ou blocos aninhados demais para compilar."),
                ("sugestão", "Divida as expressões muito longas em variáveis intermediárias."),
                ("linha", None), ("coluna", None), ("comprimento", 1),
                ("texto", "Erro GALO [G105] — erro sintático\n\nO programa tem expressões ou blocos aninhados demais."),
            ])]),
            ("avisos", []),
        ])
    bytecode = base64.b64encode(dump_module(resultado.module)).decode("ascii")
    return GaloMapa.from_pairs([
        ("ok", True), ("bytecode", bytecode), ("erros", []),
        ("avisos", [_diagnostico(e, {nome: codigo}) for e in resultado.warnings]),
    ])


@nativa("executar_programa", retorna="nulo", assinatura="executar_programa(bytecode, opções, ao_concluir)")
def executar_programa(vm, bytecode, opcoes, ao_concluir):
    """Executa um programa compilado por compilar_programa(), isolado da página (num Web Worker:
    a página não trava). opções (mapa ou nulo): entradas (lista de textos para leia()),
    limite_segundos (padrão 5), ao_escrever (função chamada com cada trecho de saída). Ao terminar,
    ao_concluir recebe {saída, erro, tempo, interrompido}; erro é nulo ou um mapa com código,
    mensagem, linha, coluna, sugestão e texto. Programas que passam do tempo são interrompidos
    (G330); saída acima de 1 MB também (G331). Só no navegador."""
    raise erro("G327", "A função executar_programa() só está disponível quando o programa roda no navegador.",
               "No servidor, use compilar_programa() e envie o bytecode para a página.")
