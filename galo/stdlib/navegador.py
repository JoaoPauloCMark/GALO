"""Funções que só existem quando o programa GALO roda no navegador (galo.js).

No servidor elas existem apenas para que o compilador conheça seus nomes e
quantidades de argumentos; chamá-las fora do navegador gera o erro G327.
A implementação real está em galo/web/galo.js.
"""

from __future__ import annotations

from ._util import erro
from .registry import nativa


def _so_no_navegador(nome: str):
    raise erro("G327", f"A função {nome}() só está disponível quando o programa roda no navegador.",
               "Compile o programa e carregue-o em uma página com galo.js (veja docs/full-stack.md).")


@nativa("elemento", assinatura="elemento(seletor)")
def elemento(vm, seletor):
    """Primeiro elemento da página que corresponde ao seletor CSS ("#id", ".classe", "tag"), ou nulo.
    Elementos têm: texto, html, valor, marcado, ao(evento, função), adicionar(filho), remover(), limpar(),
    atributo(nome), definir_atributo(nome, valor), adicionar_classe, remover_classe, alternar_classe,
    procurar(seletor), focar() e estilo(propriedade, valor). Só no navegador."""
    _so_no_navegador("elemento")


@nativa("elementos", retorna="lista", assinatura="elementos(seletor)")
def elementos(vm, seletor):
    """Lista com todos os elementos da página que correspondem ao seletor CSS. Só no navegador."""
    _so_no_navegador("elementos")


@nativa("criar_elemento", assinatura="criar_elemento(etiqueta, [texto])")
def criar_elemento(vm, etiqueta, texto=None):
    """Cria um novo elemento HTML (por exemplo "li"), opcionalmente com um texto. Só no navegador."""
    _so_no_navegador("criar_elemento")


@nativa("depois", retorna="inteiro", assinatura="depois(milissegundos, função)")
def depois(vm, ms, funcao):
    """Executa a função uma vez, depois do tempo indicado. Devolve um identificador. Só no navegador."""
    _so_no_navegador("depois")


@nativa("a_cada", retorna="inteiro", assinatura="a_cada(milissegundos, função)")
def a_cada(vm, ms, funcao):
    """Executa a função repetidamente, a cada intervalo. Devolve um identificador. Só no navegador."""
    _so_no_navegador("a_cada")


@nativa("cancelar_temporizador", retorna="nulo", assinatura="cancelar_temporizador(identificador)")
def cancelar_temporizador(vm, ident):
    """Cancela um temporizador criado por depois() ou a_cada(). Só no navegador."""
    _so_no_navegador("cancelar_temporizador")


@nativa("armazenar", retorna="nulo", assinatura="armazenar(chave, valor)")
def armazenar(vm, chave, valor):
    """Guarda um valor no navegador (localStorage); ele continua lá depois de recarregar a página."""
    _so_no_navegador("armazenar")


@nativa("recuperar", assinatura="recuperar(chave, [padrão])")
def recuperar(vm, chave, padrao=None):
    """Lê um valor guardado com armazenar(), ou o padrão (nulo) se não existir. Só no navegador."""
    _so_no_navegador("recuperar")


@nativa("esquecer", retorna="nulo", assinatura="esquecer(chave)")
def esquecer(vm, chave):
    """Apaga um valor guardado com armazenar(). Só no navegador."""
    _so_no_navegador("esquecer")


@nativa("alerta", retorna="nulo", assinatura="alerta(mensagem)")
def alerta(vm, mensagem):
    """Mostra uma caixa de mensagem no navegador."""
    _so_no_navegador("alerta")


@nativa("confirmar", retorna="booleano", assinatura="confirmar(mensagem)")
def confirmar(vm, mensagem):
    """Pergunta sim/não ao usuário do navegador; devolve verdadeiro se ele confirmar."""
    _so_no_navegador("confirmar")


@nativa("navegar", retorna="nulo", assinatura="navegar(endereço)")
def navegar(vm, endereco):
    """Leva o navegador para outro endereço."""
    _so_no_navegador("navegar")


@nativa("endereço_atual", retorna="texto", assinatura="endereço_atual()")
def endereco_atual(vm):
    """Endereço (URL) da página atual no navegador."""
    _so_no_navegador("endereço_atual")
