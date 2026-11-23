"""Manipulação de listas e mapas."""

from __future__ import annotations

from ..runtime.values import (
    MISSING, GaloMapa, _position, article, equals, make_range, op_lt, require_bool, type_name,
)
from ._util import erro, exige, exige_funcao, exige_inteiro, exige_lista, exige_mapa
from .registry import nativa


@nativa("adicionar", retorna="nulo")
def adicionar(vm, lista, valor):
    """Adiciona o valor ao final da lista."""
    exige_lista("adicionar", 1, lista).append(valor)
    return None


@nativa("inserir", retorna="nulo", assinatura="inserir(lista, posição, valor)")
def inserir(vm, lista, posicao, valor):
    """Insere o valor na posição indicada, deslocando os demais elementos para a direita."""
    exige_lista("inserir", 1, lista)
    exige_inteiro("inserir", 2, posicao)
    n = len(lista)
    if not 1 <= posicao <= n + 1:
        raise erro("G304", f"Não é possível inserir na posição {posicao}: as posições válidas vão de 1 a {n + 1}.")
    lista.insert(posicao - 1, valor)
    return None


@nativa("remover", assinatura="remover(lista, posição)")
def remover(vm, lista, posicao):
    """Remove o elemento da posição indicada e o devolve."""
    exige_lista("remover", 1, lista)
    exige_inteiro("remover", 2, posicao)
    return lista.pop(_position(lista, posicao, "lista"))


@nativa("remover_valor", retorna="booleano")
def remover_valor(vm, lista, valor):
    """Remove a primeira ocorrência do valor. Devolve verdadeiro se algo foi removido."""
    exige_lista("remover_valor", 1, lista)
    for i, x in enumerate(lista):
        if equals(x, valor):
            del lista[i]
            return True
    return False


def _check_sortable(fname: str, keys: list) -> None:
    kinds = {type_name(k) for k in keys}
    if kinds <= {"inteiro", "decimal"} or kinds == {"texto"} or not kinds:
        return
    shown = " e ".join(sorted(kinds))
    raise erro("G322", f"A função {fname}() só ordena listas só de números ou só de textos, mas encontrou: {shown}.")


@nativa("ordenar", retorna="lista")
def ordenar(vm, lista):
    """Nova lista com os elementos em ordem crescente (números ou textos). A lista original não muda."""
    exige_lista("ordenar", 1, lista)
    _check_sortable("ordenar", lista)
    return sorted(lista)


@nativa("ordenar_por", retorna="lista", assinatura="ordenar_por(lista, função_chave)")
def ordenar_por(vm, lista, funcao):
    """Nova lista ordenada pelo valor que a função devolve para cada elemento."""
    exige_lista("ordenar_por", 1, lista)
    exige_funcao("ordenar_por", 2, funcao)
    keys = [vm.call_value(funcao, [x]) for x in lista]
    _check_sortable("ordenar_por", keys)
    order = sorted(range(len(lista)), key=lambda i: keys[i])
    return [lista[i] for i in order]


@nativa("copiar")
def copiar(vm, valor):
    """Cópia de uma lista ou mapa (os elementos internos não são copiados)."""
    if type(valor) is list:
        return list(valor)
    if type(valor) is GaloMapa:
        return valor.copy()
    return valor


@nativa("intervalo", retorna="lista", assinatura="intervalo(início, fim, [passo])")
def intervalo(vm, inicio, fim, passo=None):
    """Lista com os números de início até fim (inclusive), andando de passo em passo."""
    return list(make_range(inicio, fim, passo))


@nativa("nova_lista", retorna="lista", assinatura="nova_lista(tamanho, [valor_inicial])")
def nova_lista(vm, tamanho, valor=None):
    """Lista com `tamanho` elementos iguais ao valor inicial (nulo se omitido)."""
    exige_inteiro("nova_lista", 1, tamanho)
    if tamanho < 0:
        raise erro("G322", "O tamanho de uma lista não pode ser negativo.")
    if type(valor) is list:
        return [list(valor) for _ in range(tamanho)]
    if type(valor) is GaloMapa:
        return [valor.copy() for _ in range(tamanho)]
    return [valor] * tamanho


@nativa("mapear", retorna="lista", assinatura="mapear(lista, função)")
def mapear(vm, lista, funcao):
    """Nova lista com o resultado da função aplicada a cada elemento."""
    exige_lista("mapear", 1, lista)
    exige_funcao("mapear", 2, funcao)
    return [vm.call_value(funcao, [x]) for x in list(lista)]


@nativa("filtrar", retorna="lista", assinatura="filtrar(lista, função)")
def filtrar(vm, lista, funcao):
    """Nova lista só com os elementos para os quais a função devolve verdadeiro."""
    exige_lista("filtrar", 1, lista)
    exige_funcao("filtrar", 2, funcao)
    out = []
    for x in list(lista):
        if require_bool(vm.call_value(funcao, [x]), "O resultado da função passada para filtrar()"):
            out.append(x)
    return out


@nativa("reduzir", assinatura="reduzir(lista, função, valor_inicial)")
def reduzir(vm, lista, funcao, inicial):
    """Combina os elementos: aplica função(acumulado, elemento) do primeiro ao último."""
    exige_lista("reduzir", 1, lista)
    exige_funcao("reduzir", 2, funcao)
    acc = inicial
    for x in list(lista):
        acc = vm.call_value(funcao, [acc, x])
    return acc


@nativa("algum", retorna="booleano", assinatura="algum(lista, função)")
def algum(vm, lista, funcao):
    """Verdadeiro se a função devolver verdadeiro para pelo menos um elemento."""
    exige_lista("algum", 1, lista)
    exige_funcao("algum", 2, funcao)
    return any(require_bool(vm.call_value(funcao, [x]), "O resultado da função passada para algum()") for x in list(lista))


@nativa("todos", retorna="booleano", assinatura="todos(lista, função)")
def todos(vm, lista, funcao):
    """Verdadeiro se a função devolver verdadeiro para todos os elementos."""
    exige_lista("todos", 1, lista)
    exige_funcao("todos", 2, funcao)
    return all(require_bool(vm.call_value(funcao, [x]), "O resultado da função passada para todos()") for x in list(lista))


@nativa("primeiro")
def primeiro(vm, lista):
    """Primeiro elemento da lista."""
    exige_lista("primeiro", 1, lista)
    if not lista:
        raise erro("G304", "A lista está vazia: não há primeiro elemento.")
    return lista[0]


@nativa("último")
def ultimo(vm, lista):
    """Último elemento da lista."""
    exige_lista("último", 1, lista)
    if not lista:
        raise erro("G304", "A lista está vazia: não há último elemento.")
    return lista[-1]


@nativa("contar", retorna="inteiro", assinatura="contar(coleção, valor)")
def contar(vm, colecao, valor):
    """Quantas vezes o valor aparece na lista (ou o trecho aparece no texto)."""
    if type(colecao) is list:
        return sum(1 for x in colecao if equals(x, valor))
    if type(colecao) is str:
        exige("contar", 2, valor, "texto")
        if valor == "":
            raise erro("G322", "A função contar() não aceita um texto vazio como trecho procurado.")
        return colecao.count(valor)
    raise erro("G322", f"A função contar() espera uma lista ou um texto, mas recebeu {article(type_name(colecao))}.")


@nativa("limpar", retorna="nulo", assinatura="limpar(coleção)")
def limpar(vm, colecao):
    """Remove todos os elementos de uma lista ou mapa."""
    exige("limpar", 1, colecao, "lista", "mapa")
    colecao.clear()
    return None


@nativa("vazio", retorna="booleano", assinatura="vazio(coleção)")
def vazio(vm, colecao):
    """Verdadeiro se a lista, o texto ou o mapa não tiver elementos."""
    exige("vazio", 1, colecao, "lista", "texto", "mapa")
    return len(colecao) == 0


@nativa("chaves", retorna="lista")
def chaves(vm, mapa):
    """Lista com as chaves do mapa, na ordem em que foram inseridas."""
    return exige_mapa("chaves", 1, mapa).keys()


@nativa("valores", retorna="lista")
def valores(vm, mapa):
    """Lista com os valores do mapa."""
    return exige_mapa("valores", 1, mapa).values()


@nativa("pares", retorna="lista")
def pares(vm, mapa):
    """Lista de pares [chave, valor] do mapa."""
    return [[k, v] for k, v in exige_mapa("pares", 1, mapa).items()]


@nativa("obter", assinatura="obter(coleção, chave, [padrão])")
def obter(vm, colecao, chave, padrao=None):
    """Valor da chave no mapa (ou da posição na lista); devolve o padrão (nulo) se não existir."""
    if type(colecao) is GaloMapa:
        v = colecao.get(chave) if colecao.contains(chave) else MISSING
        return padrao if v is MISSING else v
    if type(colecao) is list:
        if type(chave) is int and chave != 0 and -len(colecao) <= chave <= len(colecao):
            return colecao[chave - 1 if chave > 0 else chave]
        return padrao
    raise erro("G322", f"A função obter() espera um mapa ou uma lista, mas recebeu {article(type_name(colecao))}.")


@nativa("remover_chave", assinatura="remover_chave(mapa, chave)")
def remover_chave(vm, mapa, chave):
    """Remove a chave do mapa e devolve o valor que ela tinha (nulo se não existia)."""
    exige_mapa("remover_chave", 1, mapa)
    v = mapa.delete(chave) if mapa.contains(chave) else MISSING
    return None if v is MISSING else v
