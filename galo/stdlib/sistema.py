"""Interação com o sistema."""

from __future__ import annotations

from ..errors import GaloExit
from ._util import exige_inteiro
from .registry import nativa


@nativa("argumentos", retorna="lista")
def argumentos(vm):
    """Lista com os argumentos passados ao programa na linha de comando
    (por exemplo: galo executar programa.galo um dois)."""
    return list(vm.program_args)


@nativa("sair", retorna="nulo", assinatura="sair([código])")
def sair(vm, codigo=0):
    """Encerra o programa imediatamente com o código de saída indicado (0 = sucesso)."""
    exige_inteiro("sair", 1, codigo)
    raise GaloExit(codigo)


@nativa("variável_ambiente", assinatura="variável_ambiente(nome, [padrão])")
def variavel_ambiente(vm, nome, padrao=None):
    """Valor (texto) de uma variável de ambiente do sistema, ou o padrão (nulo) se ela não existir.
    Útil para configurar porta, senhas e caminhos sem alterar o código."""
    import os

    from ._util import exige_texto

    return os.environ.get(exige_texto("variável_ambiente", 1, nome), padrao)


@nativa("afirmar", retorna="nulo", assinatura="afirmar(condição, [mensagem])")
def afirmar(vm, condicao, mensagem="a condição é falsa"):
    """Verifica uma condição (útil em testes): se ela for falsa, interrompe com o erro G329 e a mensagem."""
    from ..runtime.values import display, require_bool

    if not require_bool(condicao, "A condição de afirmar()"):
        from ._util import erro

        raise erro("G329", f"Verificação falhou: {display(mensagem)}.")
    return None
