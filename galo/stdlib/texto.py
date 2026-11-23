"""Manipulação de textos (e algumas funções que também valem para listas)."""

from __future__ import annotations

from ..runtime.values import GaloMapa, article, display, equals, op_in, type_name
from ._util import arredondar_comercial, erro, exige, exige_inteiro, exige_numero, exige_texto, parse_number
from .registry import nativa


@nativa("tamanho", retorna="inteiro")
def tamanho(vm, valor):
    """Quantidade de elementos de uma lista, de caracteres de um texto ou de pares de um mapa."""
    t = type(valor)
    if t is list or t is str or t is GaloMapa:
        return len(valor)
    raise erro("G322", f"A função tamanho() espera uma lista, um texto ou um mapa, mas recebeu {article(type_name(valor))}.")


@nativa("maiúsculas", retorna="texto")
def maiusculas(vm, texto):
    """Converte o texto para letras maiúsculas."""
    return exige_texto("maiúsculas", 1, texto).upper()


@nativa("minúsculas", retorna="texto")
def minusculas(vm, texto):
    """Converte o texto para letras minúsculas."""
    return exige_texto("minúsculas", 1, texto).lower()


@nativa("aparar", retorna="texto")
def aparar(vm, texto):
    """Remove espaços e quebras de linha do início e do fim do texto."""
    return exige_texto("aparar", 1, texto).strip()


@nativa("dividir", retorna="lista", assinatura="dividir(texto, [separador])")
def dividir(vm, texto, separador=None):
    """Divide o texto em uma lista de partes. Sem separador, divide nos espaços."""
    exige_texto("dividir", 1, texto)
    if separador is None:
        return texto.split()
    exige_texto("dividir", 2, separador)
    if separador == "":
        return list(texto)
    return texto.split(separador)


@nativa("juntar", retorna="texto", assinatura="juntar(lista, [separador])")
def juntar(vm, lista, separador=""):
    """Junta os elementos da lista em um único texto, colocando o separador entre eles."""
    exige("juntar", 1, lista, "lista")
    exige_texto("juntar", 2, separador)
    return separador.join(display(x) for x in lista)


@nativa("substituir", retorna="texto")
def substituir(vm, texto, antigo, novo):
    """Troca todas as ocorrências de `antigo` por `novo` no texto."""
    exige_texto("substituir", 1, texto)
    exige_texto("substituir", 2, antigo)
    exige_texto("substituir", 3, novo)
    if antigo == "":
        raise erro("G322", "A função substituir() não aceita um texto vazio como valor a ser trocado.")
    return texto.replace(antigo, novo)


@nativa("contém", retorna="booleano", assinatura="contém(coleção, valor)")
def contem(vm, colecao, valor):
    """Verdadeiro se o valor estiver na lista, no texto ou entre as chaves do mapa (o mesmo que `valor em coleção`)."""
    return op_in(valor, colecao)


@nativa("começa_com", retorna="booleano")
def comeca_com(vm, texto, prefixo):
    """Verdadeiro se o texto começar com o prefixo."""
    return exige_texto("começa_com", 1, texto).startswith(exige_texto("começa_com", 2, prefixo))


@nativa("termina_com", retorna="booleano")
def termina_com(vm, texto, sufixo):
    """Verdadeiro se o texto terminar com o sufixo."""
    return exige_texto("termina_com", 1, texto).endswith(exige_texto("termina_com", 2, sufixo))


@nativa("posição", retorna="inteiro ou nulo", assinatura="posição(coleção, valor)")
def posicao(vm, colecao, valor):
    """Posição (a partir de 1) da primeira ocorrência do valor no texto ou na lista; nulo se não existir."""
    t = type(colecao)
    if t is str:
        exige_texto("posição", 2, valor)
        i = colecao.find(valor)
        return None if i < 0 else i + 1
    if t is list:
        for i, x in enumerate(colecao):
            if equals(x, valor):
                return i + 1
        return None
    raise erro("G322", f"A função posição() espera um texto ou uma lista, mas recebeu {article(type_name(colecao))}.")


def _slice_bounds(n: int, inicio: int, fim: int | None) -> tuple[int, int]:
    def norm(p: int) -> int:
        if p < 0:
            p = n + p + 1
        return min(max(p, 1), n + 1)

    a = norm(inicio) if inicio != 0 else 1
    b = n if fim is None else (norm(fim) if fim != 0 else 0)
    b = min(b, n)
    return a - 1, b


@nativa("fatia", retorna="texto ou lista", assinatura="fatia(coleção, início, [fim])")
def fatia(vm, colecao, inicio, fim=None):
    """Parte de um texto ou lista, da posição início até a posição fim (inclusive).
    Posições negativas contam a partir do fim. Sem `fim`, vai até o último elemento."""
    if type(colecao) not in (str, list):
        raise erro("G322", f"A função fatia() espera um texto ou uma lista, mas recebeu {article(type_name(colecao))}.")
    exige_inteiro("fatia", 2, inicio)
    if fim is not None:
        exige_inteiro("fatia", 3, fim)
    a, b = _slice_bounds(len(colecao), inicio, fim)
    return colecao[a:b] if a < b else colecao[0:0]


@nativa("caracteres", retorna="lista")
def caracteres(vm, texto):
    """Lista com cada caractere do texto."""
    return list(exige_texto("caracteres", 1, texto))


@nativa("código", retorna="inteiro", assinatura="código(caractere)")
def codigo(vm, caractere):
    """Código Unicode de um caractere (por exemplo, código("A") é 65)."""
    exige_texto("código", 1, caractere)
    if len(caractere) != 1:
        raise erro("G322", f"A função código() espera um texto com exatamente 1 caractere, mas recebeu {len(caractere)}.")
    return ord(caractere)


@nativa("caractere", retorna="texto", assinatura="caractere(código)")
def caractere(vm, codigo_):
    """Caractere correspondente a um código Unicode (por exemplo, caractere(65) é "A")."""
    exige_inteiro("caractere", 1, codigo_)
    if not 0 <= codigo_ <= 0x10FFFF:
        raise erro("G322", f"O código {codigo_} não corresponde a nenhum caractere Unicode.")
    return chr(codigo_)


@nativa("repetir", retorna="texto")
def repetir(vm, texto, vezes):
    """Repete o texto o número de vezes indicado."""
    exige_texto("repetir", 1, texto)
    exige_inteiro("repetir", 2, vezes)
    return texto * max(0, vezes)


@nativa("inverter", retorna="texto ou lista")
def inverter(vm, valor):
    """Novo texto ou nova lista com os elementos em ordem inversa."""
    if type(valor) is str:
        return valor[::-1]
    if type(valor) is list:
        return valor[::-1]
    raise erro("G322", f"A função inverter() espera um texto ou uma lista, mas recebeu {article(type_name(valor))}.")


@nativa("formatar", retorna="texto", assinatura="formatar(número, casas)")
def formatar(vm, numero, casas):
    """Texto com o número escrito com a quantidade fixa de casas decimais (arredondamento comercial)."""
    exige_numero("formatar", 1, numero)
    exige_inteiro("formatar", 2, casas)
    if casas < 0 or casas > 100:
        raise erro("G322", "A quantidade de casas decimais deve estar entre 0 e 100.")
    if type(numero) is float and (numero != numero or numero in (float("inf"), float("-inf"))):
        raise erro("G322", "Não é possível formatar um valor infinito ou indefinido.")
    return f"{arredondar_comercial(numero, casas):f}"


@nativa("é_número", retorna="booleano", assinatura="é_número(texto)")
def e_numero(vm, texto):
    """Verdadeiro se o texto representa um número (útil para validar o que foi digitado)."""
    if type(texto) in (int, float):
        return True
    if type(texto) is not str:
        return False
    return parse_number(texto) is not None


def _regex(fname: str, padrao: str):
    import re

    exige_texto(fname, 2, padrao)
    try:
        return re.compile(padrao)
    except re.error as exc:
        raise erro("G322", f"Expressão regular inválida em {fname}(): {exc}.")


@nativa("corresponde", retorna="booleano", assinatura="corresponde(texto, padrão)")
def corresponde(vm, texto, padrao):
    """Verdadeiro se o texto contém um trecho que segue a expressão regular.
    Use ^ e $ para exigir o texto inteiro: corresponde(email, "^[^@]+@[^@]+$")."""
    return _regex("corresponde", padrao).search(exige_texto("corresponde", 1, texto)) is not None


@nativa("procurar_todos", retorna="lista", assinatura="procurar_todos(texto, padrão)")
def procurar_todos(vm, texto, padrao):
    """Lista com todos os trechos do texto que seguem a expressão regular."""
    return [m.group(0) for m in _regex("procurar_todos", padrao).finditer(exige_texto("procurar_todos", 1, texto))]


@nativa("substituir_padrão", retorna="texto", assinatura="substituir_padrão(texto, padrão, novo)")
def substituir_padrao(vm, texto, padrao, novo):
    """Troca todos os trechos que seguem a expressão regular por `novo` (\\1, \\2... repetem grupos)."""
    exige_texto("substituir_padrão", 3, novo)
    return _regex("substituir_padrão", padrao).sub(novo, exige_texto("substituir_padrão", 1, texto))
