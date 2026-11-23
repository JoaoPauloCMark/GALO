"""Funções matemáticas."""

from __future__ import annotations

import math

from ..runtime.values import op_lt, op_pow, type_name, article
from ._util import arredondar_comercial, erro, exige_inteiro, exige_lista, exige_numero
from ..runtime import matematica_exata as exata
from .registry import constante, nativa

constante("pi", math.pi, "A constante π (3.141592653589793).")


@nativa("absoluto", retorna="número")
def absoluto(vm, x):
    """Valor absoluto (distância até zero)."""
    return abs(exige_numero("absoluto", 1, x))


@nativa("raiz", retorna="decimal")
def raiz(vm, x):
    """Raiz quadrada."""
    exige_numero("raiz", 1, x)
    if x < 0:
        raise erro("G322", f"Não existe raiz quadrada real de um número negativo ({x}).")
    if type(x) is int:
        r = math.isqrt(x)
        if r * r == x:
            return float(r)
    return math.sqrt(x)


@nativa("potência", retorna="número")
def potencia(vm, base, expoente):
    """base elevada ao expoente (o mesmo que base ^ expoente)."""
    exige_numero("potência", 1, base)
    exige_numero("potência", 2, expoente)
    return op_pow(base, expoente)


def _round_half_up(x, casas: int):
    return arredondar_comercial(x, casas)


@nativa("arredondar", retorna="número", assinatura="arredondar(número, [casas])")
def arredondar(vm, x, casas=0):
    """Arredonda para o inteiro mais próximo (ou para a quantidade de casas decimais).
    Metades são arredondadas para longe do zero: arredondar(2.5) é 3."""
    exige_numero("arredondar", 1, x)
    exige_inteiro("arredondar", 2, casas)
    if type(x) is int:
        return x
    if x != x or x in (math.inf, -math.inf):
        raise erro("G322", "Não é possível arredondar um valor infinito ou indefinido.")
    if casas <= 0:
        return int(_round_half_up(x, 0))
    return float(_round_half_up(x, casas))


@nativa("piso", retorna="inteiro")
def piso(vm, x):
    """Maior inteiro menor ou igual ao número."""
    exige_numero("piso", 1, x)
    if type(x) is int:
        return x
    try:
        return math.floor(x)
    except (OverflowError, ValueError):
        raise erro("G322", "Não é possível calcular o piso de um valor infinito ou indefinido.")


@nativa("teto", retorna="inteiro")
def teto(vm, x):
    """Menor inteiro maior ou igual ao número."""
    exige_numero("teto", 1, x)
    if type(x) is int:
        return x
    try:
        return math.ceil(x)
    except (OverflowError, ValueError):
        raise erro("G322", "Não é possível calcular o teto de um valor infinito ou indefinido.")


def _values(fname, valores):
    if len(valores) == 1 and type(valores[0]) is list:
        valores = valores[0]
    if not valores:
        raise erro("G322", f"A função {fname}() precisa de pelo menos um valor.")
    return list(valores)


@nativa("mínimo", assinatura="mínimo(valores...)")
def minimo(vm, *valores):
    """Menor valor entre os argumentos (ou entre os elementos de uma lista)."""
    vals = _values("mínimo", valores)
    best = vals[0]
    for v in vals[1:]:
        if op_lt(v, best):
            best = v
    return best


@nativa("máximo", assinatura="máximo(valores...)")
def maximo(vm, *valores):
    """Maior valor entre os argumentos (ou entre os elementos de uma lista)."""
    vals = _values("máximo", valores)
    best = vals[0]
    for v in vals[1:]:
        if op_lt(best, v):
            best = v
    return best


@nativa("soma", retorna="número")
def soma(vm, lista):
    """Soma dos números de uma lista."""
    exige_lista("soma", 1, lista)
    total = 0
    for i, v in enumerate(lista, 1):
        if type(v) not in (int, float):
            raise erro("G322", f"A função soma() só soma números, mas o elemento {i} é {article(type_name(v))}.")
        total += v
    return total


@nativa("média", retorna="decimal")
def media(vm, lista):
    """Média aritmética dos números de uma lista."""
    exige_lista("média", 1, lista)
    if not lista:
        raise erro("G322", "Não é possível calcular a média de uma lista vazia.")
    return soma(vm, lista) / len(lista)


@nativa("aleatório", retorna="decimal")
def aleatorio(vm):
    """Número decimal aleatório entre 0 (inclusive) e 1 (exclusive)."""
    return vm.random.random()


@nativa("aleatório_entre", retorna="inteiro")
def aleatorio_entre(vm, minimo_, maximo_):
    """Inteiro aleatório entre os dois valores (ambos inclusive)."""
    exige_inteiro("aleatório_entre", 1, minimo_)
    exige_inteiro("aleatório_entre", 2, maximo_)
    if minimo_ > maximo_:
        raise erro("G322", f"Em aleatório_entre({minimo_}, {maximo_}), o primeiro valor não pode ser maior que o segundo.")
    return vm.random.randint(minimo_, maximo_)


@nativa("semente_aleatória", retorna="nulo")
def semente_aleatoria(vm, semente):
    """Fixa a semente dos números aleatórios, tornando a sequência reproduzível — a mesma no
    servidor e no navegador. Para senhas e sessões, use token_aleatório()."""
    exige_inteiro("semente_aleatória", 1, semente)
    vm.random.seed(semente)
    return None


def _decimal_finito(fname: str, pos: int, x) -> float:
    exige_numero(fname, pos, x)
    try:
        v = float(x)
    except OverflowError:
        raise erro("G317", f"O número passado para {fname}() é grande demais para ser um decimal.")
    if v != v or v in (math.inf, -math.inf):
        raise erro("G322", f"A função {fname}() não aceita valores infinitos ou indefinidos.")
    return v


@nativa("seno", retorna="decimal")
def seno(vm, x):
    """Seno de um ângulo em radianos (resultado corretamente arredondado, igual em qualquer plataforma)."""
    return exata.seno(_decimal_finito("seno", 1, x))


@nativa("cosseno", retorna="decimal")
def cosseno(vm, x):
    """Cosseno de um ângulo em radianos (resultado corretamente arredondado, igual em qualquer plataforma)."""
    return exata.cosseno(_decimal_finito("cosseno", 1, x))


@nativa("tangente", retorna="decimal")
def tangente(vm, x):
    """Tangente de um ângulo em radianos (resultado corretamente arredondado, igual em qualquer plataforma)."""
    return exata.tangente(_decimal_finito("tangente", 1, x))


@nativa("logaritmo", retorna="decimal", assinatura="logaritmo(x, [base])")
def logaritmo(vm, x, base=None):
    """Logaritmo de x. Sem base, usa o logaritmo natural (base e). O resultado é corretamente
    arredondado e igual em qualquer plataforma: logaritmo(1000, 10) é exatamente 3.0."""
    x = _decimal_finito("logaritmo", 1, x)
    if x <= 0:
        raise erro("G322", "O logaritmo só existe para números maiores que zero.")
    if base is None:
        return exata.logaritmo(x)
    base = _decimal_finito("logaritmo", 2, base)
    if base <= 0 or base == 1:
        raise erro("G322", "A base do logaritmo deve ser maior que zero e diferente de 1.")
    return exata.logaritmo_base(x, base)
