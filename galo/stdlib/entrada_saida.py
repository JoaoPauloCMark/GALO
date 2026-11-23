"""Entrada e saída no terminal."""

from __future__ import annotations

from ..runtime.values import display
from .registry import nativa


@nativa("leia", retorna="texto ou nulo", assinatura="leia([mensagem])")
def leia(vm, mensagem=None):
    """Lê uma linha digitada no terminal e devolve o texto (sem a quebra de linha).
    Se a mensagem for informada, ela é mostrada antes da leitura.
    Devolve nulo quando não há mais entrada disponível."""
    return vm.read_line("" if mensagem is None else display(mensagem))


@nativa("escreva", retorna="nulo", assinatura="escreva(valores...)")
def escreva(vm, *valores):
    """Escreve os valores separados por espaço, sem pular de linha."""
    vm.write(" ".join(display(v) for v in valores))
    return None
