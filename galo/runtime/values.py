"""Valores da GALO e a semântica de suas operações.

Representação interna (nunca exposta diretamente aos programas GALO):

    inteiro   -> int (precisão arbitrária)
    decimal   -> float (IEEE 754, 64 bits)
    texto     -> str (imutável)
    booleano  -> bool (mas NUNCA tratado como número)
    nulo      -> None
    lista     -> list (mutável, posições a partir de 1)
    mapa      -> GaloMapa (ordem de inserção preservada)
    função    -> Closure (função GALO) ou NativeFunction (função interna)

Todas as verificações usam `type(v) is ...` para que `verdadeiro` jamais
seja confundido com o inteiro 1, como aconteceria em Python.
"""

from __future__ import annotations

import math
from fractions import Fraction

from ..errors import GaloRuntimeError
from ..names import canonical


class _Sentinel:
    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:  # pragma: no cover
        return self.name


UNSET = _Sentinel("<sem valor>")
MISSING = _Sentinel("<ausente>")

# Limite de tamanho para resultados de potência inteira (em bits). Evita que
# um programa trave a máquina calculando, por exemplo, 10 ^ 10 ^ 10.
MAX_POW_BITS = 1 << 26


class Cell:
    """Caixa que guarda uma variável capturada por uma função interna (closure)."""

    __slots__ = ("value",)

    def __init__(self, value=UNSET) -> None:
        self.value = value


class Closure:
    """Função definida em GALO: código compilado + variáveis capturadas + globais do módulo."""

    __slots__ = ("code", "cells", "name", "globals")

    def __init__(self, code, cells: tuple, globals_: dict | None = None) -> None:
        self.code = code
        self.cells = cells
        self.name = code.name
        self.globals = globals_ if globals_ is not None else {}


class GaloTipoRegistro:
    """Tipo definido pelo usuário com `registro`. Chamá-lo cria uma instância."""

    __slots__ = ("name", "fields", "specs", "index", "ctor", "methods")

    def __init__(self, name: str, fields: tuple, specs: tuple, ctor, methods: dict) -> None:
        self.name = name
        self.fields = fields
        self.specs = specs
        self.index = {canonical(f): i for i, f in enumerate(fields)}
        self.ctor = ctor
        self.methods = methods  # chave canônica -> Closure (primeiro parâmetro: eu)


class GaloRegistro:
    """Instância de um registro: valores dos campos na ordem da declaração."""

    __slots__ = ("tipo", "valores")

    def __init__(self, tipo: GaloTipoRegistro, valores: list) -> None:
        self.tipo = tipo
        self.valores = valores


class MetodoLigado:
    """Método obtido de uma instância (`tarefa.concluir`): já sabe quem é `eu`."""

    __slots__ = ("receptor", "funcao")

    def __init__(self, receptor, funcao) -> None:
        self.receptor = receptor
        self.funcao = funcao


class GaloModulo:
    """Módulo importado: globais próprias e a lista de nomes exportados."""

    __slots__ = ("name", "globals", "exports", "ready")

    def __init__(self, name: str, exports) -> None:
        self.name = name
        self.globals: dict = {}
        self.exports = {canonical(e): e for e in exports}
        self.ready = False


class GaloObjetoNativo:
    """Objeto fornecido pelo runtime (servidor web, banco de dados, elemento...).

    Expõe apenas métodos (funções internas já ligadas ao objeto) e propriedades
    explicitamente declarados; nenhum atributo Python fica acessível.
    """

    __slots__ = ("tipo", "metodos", "props", "setters", "dados")

    def __init__(self, tipo: str, dados=None) -> None:
        self.tipo = tipo
        self.metodos: dict = {}
        self.props: dict = {}      # chave -> função sem argumentos que devolve o valor
        self.setters: dict = {}    # chave -> função(valor)
        self.dados = dados

    def metodo(self, nome: str, fn, min_args: int, max_args, retorna=None, doc: str = "") -> None:
        alvo = self

        def ligado(vm, *args):
            return fn(vm, alvo, *args)

        self.metodos[canonical(nome)] = NativeFunction(f"{self.tipo}.{nome}", ligado, min_args, max_args, retorna, doc,
                                                       f"{nome}(...)")

    def propriedade(self, nome: str, getter, setter=None) -> None:
        self.props[canonical(nome)] = getter
        if setter is not None:
            self.setters[canonical(nome)] = setter


class NativeFunction:
    """Função interna implementada pelo runtime."""

    __slots__ = ("name", "key", "fn", "min_args", "max_args", "returns", "doc", "signature")

    def __init__(self, name, fn, min_args, max_args, returns=None, doc="", signature="") -> None:
        self.name = name
        self.key = canonical(name)
        self.fn = fn
        self.min_args = min_args
        self.max_args = max_args  # None = quantidade variável
        self.returns = returns    # tupla de nomes de tipo ou None (desconhecido)
        self.doc = doc or ""
        self.signature = signature or f"{name}(...)"


_BOOL_TAG = "\x00booleano"


class GaloMapa:
    """Mapa (dicionário) da GALO.

    Internamente as chaves são normalizadas para que `verdadeiro` e `1` sejam
    chaves diferentes (em Python, True == 1). A ordem de inserção é mantida.
    """

    __slots__ = ("_d",)

    def __init__(self) -> None:
        self._d: dict = {}

    @staticmethod
    def norm(k):
        t = type(k)
        if t is str or t is int or k is None or t is float:
            return k
        if t is bool:
            return (_BOOL_TAG, k)
        raise GaloRuntimeError(
            "G321", f"{article(type_name(k)).capitalize()} não pode ser usado como chave de mapa.",
            suggestion="Use textos, números, booleanos ou nulo como chaves.",
        )

    def get(self, k, default=MISSING):
        e = self._d.get(self.norm(k))
        return default if e is None else e[1]

    def set(self, k, v) -> None:
        nk = self.norm(k)
        e = self._d.get(nk)
        if e is None:
            self._d[nk] = [k, v]
        else:
            e[1] = v

    def contains(self, k) -> bool:
        try:
            return self.norm(k) in self._d
        except GaloRuntimeError:
            return False

    def delete(self, k):
        e = self._d.pop(self.norm(k), None)
        return MISSING if e is None else e[1]

    def keys(self) -> list:
        return [e[0] for e in self._d.values()]

    def values(self) -> list:
        return [e[1] for e in self._d.values()]

    def items(self) -> list:
        return [(e[0], e[1]) for e in self._d.values()]

    def clear(self) -> None:
        self._d.clear()

    def copy(self) -> "GaloMapa":
        m = GaloMapa()
        for nk, (k, v) in self._d.items():
            m._d[nk] = [k, v]
        return m

    def __len__(self) -> int:
        return len(self._d)

    def find_field(self, name: str):
        """Resolve `mapa.campo`: busca exata; depois, ignorando acentos."""
        if name in self._d:
            return name
        cn = canonical(name)
        for k, _ in self._d.values():
            if type(k) is str and canonical(k) == cn:
                return k
        return MISSING

    @classmethod
    def from_pairs(cls, pairs) -> "GaloMapa":
        m = cls()
        for k, v in pairs:
            m.set(k, v)
        return m


# ---------------------------------------------------------------- tipos


def type_name(v) -> str:
    t = type(v)
    if t is int:
        return "inteiro"
    if t is str:
        return "texto"
    if t is float:
        return "decimal"
    if t is bool:
        return "booleano"
    if t is list:
        return "lista"
    if v is None:
        return "nulo"
    if t is GaloMapa:
        return "mapa"
    if t is Closure or t is NativeFunction or t is MetodoLigado:
        return "função"
    if t is GaloRegistro:
        return v.tipo.name
    if t is GaloTipoRegistro:
        return "tipo"
    if t is GaloModulo:
        return "módulo"
    if t is GaloObjetoNativo:
        return v.tipo
    return "interno"


ARTICLES = {
    "inteiro": "um inteiro",
    "decimal": "um decimal",
    "texto": "um texto",
    "booleano": "um booleano",
    "lista": "uma lista",
    "mapa": "um mapa",
    "nulo": "nulo",
    "função": "uma função",
    "número": "um número",
}


ARTICLES.update({"tipo": "um tipo de registro", "módulo": "um módulo"})


def article(tname: str) -> str:
    return ARTICLES.get(tname, f"um valor do tipo {tname}")


def describe_types(names) -> str:
    """('inteiro', 'decimal', 'texto') -> 'um número ou um texto'."""
    names = list(names)
    if "inteiro" in names and "decimal" in names:
        names = ["número"] + [n for n in names if n not in ("inteiro", "decimal")]
    parts = [article(n) for n in names]
    if len(parts) <= 1:
        return parts[0] if parts else "nada"
    return ", ".join(parts[:-1]) + " ou " + parts[-1]


def describe_spec(names) -> str:
    """('inteiro', 'decimal') -> 'número' (sem artigos, para anotações de tipo)."""
    names = list(names)
    if "inteiro" in names and "decimal" in names:
        names = ["número"] + [n for n in names if n not in ("inteiro", "decimal")]
    return " ou ".join(names)


def coerce(value, spec: tuple):
    """Verifica se `value` pertence aos tipos de `spec`. Inteiros são
    promovidos a decimal quando apenas decimal é aceito. Devolve o valor
    (possivelmente convertido) ou MISSING."""
    tn = type_name(value)
    if tn in spec:
        return value
    if tn == "inteiro" and "decimal" in spec:
        try:
            return float(value)
        except OverflowError:
            return MISSING
    return MISSING


# ---------------------------------------------------------------- exibição


def fmt_decimal(x: float) -> str:
    if x != x:
        return "NaN"
    if x == math.inf:
        return "infinito"
    if x == -math.inf:
        return "-infinito"
    return repr(x)


def quote(s: str) -> str:
    out = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t").replace("{", "\\{")
    return f'"{out}"'


def display(v) -> str:
    """Forma usada por `mostre`, interpolação e texto(x)."""
    if type(v) is str:
        return v
    return repr_value(v)


def repr_value(v, _seen=None) -> str:
    """Forma literal (textos entre aspas), usada dentro de coleções e no REPL."""
    t = type(v)
    if t is bool:
        return "verdadeiro" if v else "falso"
    if t is int:
        return str(v)
    if t is str:
        return quote(v)
    if t is float:
        return fmt_decimal(v)
    if v is None:
        return "nulo"
    if t is list or t is GaloMapa:
        if _seen is None:
            _seen = set()
        if id(v) in _seen:
            return "[...]" if t is list else "{...}"
        _seen.add(id(v))
        try:
            if t is list:
                return "[" + ", ".join(repr_value(x, _seen) for x in v) + "]"
            return "{" + ", ".join(f"{repr_value(k, _seen)}: {repr_value(x, _seen)}" for k, x in v.items()) + "}"
        finally:
            _seen.discard(id(v))
    if t is GaloRegistro:
        if _seen is None:
            _seen = set()
        if id(v) in _seen:
            return f"{v.tipo.name}(...)"
        _seen.add(id(v))
        try:
            campos = ", ".join(f"{n}: {repr_value(x, _seen)}" for n, x in zip(v.tipo.fields, v.valores))
        finally:
            _seen.discard(id(v))
        return f"{v.tipo.name}({campos})"
    if t is Closure:
        return f"<função {v.name}>"
    if t is NativeFunction:
        return f"<função interna {v.name}>"
    if t is MetodoLigado:
        return f"<método {v.funcao.name}>"
    if t is GaloTipoRegistro:
        return f"<registro {v.name}>"
    if t is GaloModulo:
        return f"<módulo {v.name}>"
    if t is GaloObjetoNativo:
        return f"<{v.tipo}>"
    return "<valor interno>"


# ---------------------------------------------------------------- igualdade


def equals(a, b, _seen=None) -> bool:
    ta, tb = type(a), type(b)
    if ta is tb:
        if ta is list:
            if a is b:
                return True
            if len(a) != len(b):
                return False
            if _seen is None:
                _seen = set()
            pair = (id(a), id(b))
            if pair in _seen:
                return True
            _seen.add(pair)
            return all(equals(x, y, _seen) for x, y in zip(a, b))
        if ta is GaloMapa:
            if a is b:
                return True
            if len(a) != len(b):
                return False
            if _seen is None:
                _seen = set()
            pair = (id(a), id(b))
            if pair in _seen:
                return True
            _seen.add(pair)
            for k, v in a.items():
                other = b.get(k)
                if other is MISSING or not equals(v, other, _seen):
                    return False
            return True
        if ta is GaloRegistro:
            if a is b:
                return True
            if a.tipo is not b.tipo:
                return False
            if _seen is None:
                _seen = set()
            pair = (id(a), id(b))
            if pair in _seen:
                return True
            _seen.add(pair)
            return all(equals(x, y, _seen) for x, y in zip(a.valores, b.valores))
        if ta is MetodoLigado:
            return a.receptor is b.receptor and a.funcao is b.funcao
        if ta is str or ta is int or ta is float or ta is bool or a is None:
            return a == b
        return a is b
    if (ta is int or ta is float) and (tb is int or tb is float):
        return a == b
    return False


# ---------------------------------------------------------------- aritmética

_VERBS = {
    "+": "somar",
    "-": "subtrair",
    "*": "multiplicar",
    "/": "dividir",
    "//": "fazer a divisão inteira entre",
    "%": "calcular o resto entre",
    "^": "calcular a potência entre",
}


def binop_message(op: str, ta: str, tb: str) -> tuple[str, str | None]:
    verb = _VERBS.get(op, f"aplicar '{op}' a")
    msg = f"Não é possível {verb} {article(ta)} e {article(tb)} (operador '{op}')."
    suggestion = None
    nums = ("inteiro", "decimal")
    if op == "+" and ((ta == "texto" and tb in nums) or (tb == "texto" and ta in nums)):
        suggestion = 'Para juntar texto e número, use interpolação: "Total: {valor}" ou converta com texto(valor).'
    elif "texto" in (ta, tb) and (ta in nums or tb in nums):
        suggestion = "Se o texto contém um número, converta-o antes: número(texto)."
    elif "nulo" in (ta, tb):
        suggestion = "Um dos valores é nulo. Verifique se a variável recebeu um valor antes desta operação."
    elif "booleano" in (ta, tb):
        suggestion = "Booleanos (verdadeiro/falso) não são números em GALO."
    return msg, suggestion


def _binop_error(op, a, b) -> GaloRuntimeError:
    msg, suggestion = binop_message(op, type_name(a), type_name(b))
    return GaloRuntimeError("G302", msg, suggestion=suggestion)


def _division_by_zero() -> GaloRuntimeError:
    return GaloRuntimeError("G303", "Divisão por zero.",
                            suggestion="Verifique se o divisor é diferente de zero antes de dividir.")


def is_number(v) -> bool:
    t = type(v)
    return t is int or t is float


_INFINITOS = (math.inf, -math.inf)


def _sem_estouro(r, a, b):
    """Resultado infinito a partir de operandos finitos é estouro (G317), como diz a especificação."""
    if type(r) is float and r in _INFINITOS and a not in _INFINITOS and b not in _INFINITOS:
        raise GaloRuntimeError("G317", "Número grande demais para ser representado.",
                               suggestion="Decimais (ponto flutuante) têm limite de aproximadamente 1.8e308.")
    return r


def op_add(a, b):
    ta, tb = type(a), type(b)
    if (ta is int or ta is float) and (tb is int or tb is float):
        return _sem_estouro(a + b, a, b)
    if ta is str and tb is str:
        return a + b
    if ta is list and tb is list:
        return a + b
    raise _binop_error("+", a, b)


def op_sub(a, b):
    if is_number(a) and is_number(b):
        return _sem_estouro(a - b, a, b)
    raise _binop_error("-", a, b)


def op_mul(a, b):
    ta, tb = type(a), type(b)
    if (ta is int or ta is float) and (tb is int or tb is float):
        return _sem_estouro(a * b, a, b)
    if ta is str and tb is int:
        return a * max(0, b)
    if ta is int and tb is str:
        return b * max(0, a)
    raise _binop_error("*", a, b)


def op_div(a, b):
    if is_number(a) and is_number(b):
        if b == 0:
            raise _division_by_zero()
        return _sem_estouro(a / b, a, b)
    raise _binop_error("/", a, b)


def op_idiv(a, b):
    if is_number(a) and is_number(b):
        if b == 0:
            raise _division_by_zero()
        return _sem_estouro(a // b, a, b)
    raise _binop_error("//", a, b)


def op_mod(a, b):
    if is_number(a) and is_number(b):
        if b == 0:
            raise _division_by_zero()
        return a % b
    raise _binop_error("%", a, b)


def _potencia_inteira_exata(a, n: int) -> float:
    """a ^ n (n inteiro; a decimal, ou inteiro com n negativo) calculado de forma exata e
    arredondado uma única vez para o decimal mais próximo.

    Assim o resultado não depende da biblioteca matemática da plataforma, e as duas
    máquinas virtuais (Python e navegador) produzem exatamente o mesmo valor.
    """
    if n == 0:
        return 1.0
    if type(a) is float:
        if a != a or a in (math.inf, -math.inf):
            return a ** n
        if a == 0.0:
            return a ** n
        if n == 1:
            return a
        if n == 2:
            return _sem_estouro(a * a, a, a)  # uma única multiplicação: já é o resultado exato arredondado
        e = math.frexp(a)[1]  # |a| = m * 2^e, com 0.5 <= m < 1
    else:
        e = abs(a).bit_length()
    if n == -1:
        return 1.0 / a if type(a) is float else 1 / a
    # log2 |a^n| está entre (e - 1) * n e e * n
    menor, maior = sorted(((e - 1) * n, e * n))
    if menor > 1025:
        raise OverflowError("resultado grande demais")
    if maior < -1076:
        return -0.0 if a < 0 and n % 2 else 0.0
    return float(Fraction(a) ** n)


def op_pow(a, b):
    if not (is_number(a) and is_number(b)):
        raise _binop_error("^", a, b)
    if type(a) is int and type(b) is int:
        if b >= 0:
            if abs(a) > 1 and b * a.bit_length() > MAX_POW_BITS:
                raise GaloRuntimeError("G317", f"O resultado de {a} ^ {b} seria grande demais para ser calculado.")
            return a ** b
        if a == 0:
            raise GaloRuntimeError("G303", "Zero elevado a um expoente negativo equivale a uma divisão por zero.")
        return _potencia_inteira_exata(a, b)
    if a == 0 and b < 0:
        raise GaloRuntimeError("G303", "Zero elevado a um expoente negativo equivale a uma divisão por zero.")
    if a < 0 and not float(b).is_integer():
        raise GaloRuntimeError("G302", f"{fmt_decimal(float(a))} ^ {fmt_decimal(float(b))} não é um número real.",
                               suggestion="A potência de um número negativo só existe para expoentes inteiros.")
    if float(b).is_integer() and abs(b) <= 1024:
        return _potencia_inteira_exata(float(a), int(b))
    x, y = float(a), float(b)
    if x != x or y != y or x in _INFINITOS or y in _INFINITOS or x == 0.0:
        return x ** y  # casos especiais do IEEE 754 (iguais nas duas VMs)
    from .matematica_exata import potencia

    magnitude = potencia(abs(x), y)
    if magnitude == math.inf:
        raise OverflowError("resultado grande demais")
    if x < 0 and int(y) % 2 == 1:  # aqui y é inteiro (base negativa com expoente fracionário já foi recusada)
        return -magnitude
    return magnitude


def op_neg(a):
    if is_number(a):
        return -a
    raise GaloRuntimeError("G302", f"Não é possível aplicar '-' a {article(type_name(a))}.")


def op_pos(a):
    if is_number(a):
        return a
    raise GaloRuntimeError("G302", f"Não é possível aplicar '+' a {article(type_name(a))}.")


def op_not(a):
    if type(a) is bool:
        return not a
    raise GaloRuntimeError("G310", f"O operador 'não' exige um booleano, mas recebeu {article(type_name(a))}.",
                           suggestion="Use uma comparação, por exemplo: não (x == 0)")


def _cmp_error(op, a, b) -> GaloRuntimeError:
    ta, tb = type_name(a), type_name(b)
    suggestion = None
    if {ta, tb} & {"texto"} and {ta, tb} & {"inteiro", "decimal"}:
        suggestion = "Converta o texto para número antes de comparar: número(texto)."
    return GaloRuntimeError("G302", f"Não é possível comparar {article(ta)} com {article(tb)} usando '{op}'.",
                            suggestion=suggestion)


def _comparable(a, b) -> bool:
    ta, tb = type(a), type(b)
    if (ta is int or ta is float) and (tb is int or tb is float):
        return True
    return ta is str and tb is str


def op_lt(a, b):
    if _comparable(a, b):
        return a < b
    raise _cmp_error("<", a, b)


def op_le(a, b):
    if _comparable(a, b):
        return a <= b
    raise _cmp_error("<=", a, b)


def op_gt(a, b):
    if _comparable(a, b):
        return a > b
    raise _cmp_error(">", a, b)


def op_ge(a, b):
    if _comparable(a, b):
        return a >= b
    raise _cmp_error(">=", a, b)


def op_in(a, b):
    tb = type(b)
    if tb is list:
        return any(equals(a, x) for x in b)
    if tb is str:
        if type(a) is not str:
            raise GaloRuntimeError("G302", f"Para procurar dentro de um texto com 'em', o valor procurado deve ser um texto, "
                                           f"mas é {article(type_name(a))}.")
        return a in b
    if tb is GaloMapa:
        return b.contains(a)
    raise GaloRuntimeError("G302", f"O operador 'em' precisa de uma lista, um texto ou um mapa à direita, "
                                   f"mas recebeu {article(type_name(b))}.")


def require_bool(v, context: str = "A condição"):
    if type(v) is bool:
        return v
    raise GaloRuntimeError(
        "G310", f"{context} precisa ser um booleano (verdadeiro ou falso), mas é {article(type_name(v))}.",
        suggestion="Use uma comparação, por exemplo: se x > 0 então   ou   se tamanho(lista) > 0 então",
    )


# ---------------------------------------------------------------- acesso


_KIND_WORDS = {
    "lista": ("em uma lista", "a lista", "elemento"),
    "texto": ("em um texto", "o texto", "caractere"),
}


def _position(seq, idx, kind: str, writing: bool = False) -> int:
    where, subject, noun = _KIND_WORDS[kind]
    if type(idx) is not int:
        raise GaloRuntimeError("G302", f"A posição {where} deve ser um inteiro, mas é {article(type_name(idx))}.")
    n = len(seq)
    if idx > 0:
        if idx <= n:
            return idx - 1
    elif idx < 0:
        if -idx <= n:
            return n + idx
    else:
        raise GaloRuntimeError("G304", "A posição 0 não existe: em GALO, a primeira posição é 1.",
                               suggestion="Use [1] para o primeiro elemento e [-1] para o último.")
    size = f"{n} {noun}{'s' if n != 1 else ''}"
    if n == 0:
        suggestion = f"{subject.capitalize()} está vazi{subject[0]}."
        if writing:
            suggestion += " Para incluir elementos use adicionar(lista, valor)."
    else:
        suggestion = f"As posições válidas vão de 1 a {n} (ou de -1 a -{n}, contando do fim)."
        if writing and idx == n + 1:
            suggestion += " Para incluir um novo elemento no final, use adicionar(lista, valor)."
    raise GaloRuntimeError("G304", f"A posição {idx} está fora dos limites ({subject} tem {size}).", suggestion=suggestion)


def index_get(obj, idx):
    t = type(obj)
    if t is list:
        return obj[_position(obj, idx, "lista")]
    if t is str:
        return obj[_position(obj, idx, "texto")]
    if t is GaloMapa:
        v = obj.get(idx)
        if v is MISSING:
            raise GaloRuntimeError(
                "G305", f"A chave {repr_value(idx)} não existe no mapa.",
                suggestion="Verifique antes com 'se chave em mapa então' ou use obter(mapa, chave, valor_padrão).",
            )
        return v
    raise GaloRuntimeError("G302", f"Não é possível acessar posições de {article(type_name(obj))}.",
                           suggestion="O acesso com [ ] funciona em listas, textos e mapas.")


def index_set(obj, idx, value) -> None:
    t = type(obj)
    if t is list:
        obj[_position(obj, idx, "lista", writing=True)] = value
        return
    if t is GaloMapa:
        obj.set(idx, value)
        return
    if t is str:
        raise GaloRuntimeError("G302", "Textos não podem ser alterados por posição.",
                               suggestion="Crie um novo texto, por exemplo com substituir(...) ou fatia(...).")
    raise GaloRuntimeError("G302", f"Não é possível alterar posições de {article(type_name(obj))}.")


def _close_names(name: str, options) -> str | None:
    import difflib

    found = difflib.get_close_matches(canonical(name), [canonical(o) for o in options], n=1, cutoff=0.6)
    if not found:
        return None
    for o in options:
        if canonical(o) == found[0]:
            return o
    return None


def _record_field_error(obj, name: str) -> GaloRuntimeError:
    rt = obj.tipo
    options = list(rt.fields) + [m.name.rsplit(".", 1)[-1] for m in rt.methods.values()]
    close = _close_names(name, options)
    suggestion = (f"Você quis dizer '{close}'? " if close else "") + "Campos de " + rt.name + ": " + ", ".join(rt.fields)
    return GaloRuntimeError("G305", f"O registro {rt.name} não possui o campo '{name}'.", suggestion=suggestion)


def _module_get(obj: "GaloModulo", name: str):
    key = canonical(name)
    if key not in obj.exports:
        close = _close_names(name, list(obj.exports.values()))
        raise GaloRuntimeError("G305", f"O módulo '{obj.name}' não exporta '{name}'.",
                               suggestion=f"Você quis dizer '{close}'?" if close else
                               "Nomes que começam com '_' são privados do módulo.")
    v = obj.globals.get(key, MISSING)
    if v is MISSING:
        raise GaloRuntimeError("G301", f"'{name}' ainda não tem valor no módulo '{obj.name}'.",
                               suggestion="Isso acontece em importações circulares ou quando o módulo falhou ao carregar.")
    return v


def field_get(obj, name: str):
    t = type(obj)
    if t is GaloRegistro:
        key = canonical(name)
        i = obj.tipo.index.get(key)
        if i is not None:
            return obj.valores[i]
        m = obj.tipo.methods.get(key)
        if m is not None:
            return MetodoLigado(obj, m)
        raise _record_field_error(obj, name)
    if t is GaloModulo:
        return _module_get(obj, name)
    if t is GaloObjetoNativo:
        key = canonical(name)
        m = obj.metodos.get(key)
        if m is not None:
            return m
        g = obj.props.get(key)
        if g is not None:
            return g()
        opcoes = sorted(n.name.rsplit(".", 1)[-1] for n in obj.metodos.values())
        raise GaloRuntimeError("G305", f"Um {obj.tipo} não possui '{name}'.",
                               suggestion="Disponível: " + ", ".join(opcoes) if opcoes else None)
    if t is not GaloMapa:
        raise GaloRuntimeError(
            "G302", f"O acesso com '.' (campo '{name}') só funciona em mapas e registros, mas o valor é {article(type_name(obj))}.",
            suggestion="Para chamar uma função sobre o valor, use a forma função(valor), como tamanho(lista).",
        )
    k = obj.find_field(name)
    if k is MISSING:
        keys = [repr_value(x) for x in obj.keys()[:8]]
        suggestion = ("Campos existentes: " + ", ".join(keys)) if keys else "O mapa está vazio."
        raise GaloRuntimeError("G305", f"O mapa não possui o campo '{name}'.", suggestion=suggestion)
    return obj.get(k)


def field_set(obj, name: str, value) -> None:
    t = type(obj)
    if t is GaloRegistro:
        key = canonical(name)
        i = obj.tipo.index.get(key)
        if i is None:
            if key in obj.tipo.methods:
                raise GaloRuntimeError("G302", f"'{name}' é um método de {obj.tipo.name} e não pode receber outro valor.")
            raise _record_field_error(obj, name)
        spec = obj.tipo.specs[i]
        if spec is not None:
            v = coerce(value, spec)
            if v is MISSING:
                raise GaloRuntimeError("G315", f"O campo '{obj.tipo.fields[i]}' de {obj.tipo.name} é do tipo "
                                               f"{describe_spec(spec)}, mas recebeu {article(type_name(value))}.")
            value = v
        obj.valores[i] = value
        return
    if t is GaloObjetoNativo:
        setter = obj.setters.get(canonical(name))
        if setter is None:
            raise GaloRuntimeError("G302", f"'{name}' de um {obj.tipo} não pode ser alterado.")
        setter(value)
        return
    if t is GaloModulo:
        raise GaloRuntimeError("G302", f"Não é possível alterar '{name}' do módulo '{obj.name}' de fora dele.",
                               suggestion="Crie uma função no módulo que faça a alteração.")
    if t is not GaloMapa:
        raise GaloRuntimeError(
            "G302", f"O acesso com '.' (campo '{name}') só funciona em mapas e registros, mas o valor é {article(type_name(obj))}."
        )
    k = obj.find_field(name)
    obj.set(name if k is MISSING else k, value)


# ---------------------------------------------------------------- iteração


def make_iter(v, two: bool):
    t = type(v)
    if t is list:
        snapshot = list(v)
        return enumerate(snapshot, 1) if two else iter(snapshot)
    if t is str:
        return enumerate(v, 1) if two else iter(v)
    if t is GaloMapa:
        return iter(v.items()) if two else iter(v.keys())
    suggestion = None
    if t is int:
        suggestion = "Para repetir um número de vezes, use 'repita n vezes' ou 'para i de 1 até n faça'."
    raise GaloRuntimeError("G314", f"Não é possível percorrer {article(type_name(v))} com 'para cada'.",
                           suggestion=suggestion or "O 'para cada' percorre listas, textos e mapas.")


def _float_range(a, b, step):
    k = 0
    tolerance = abs(step) * 1e-9
    while True:
        x = a + k * step
        if (step > 0 and x > b + tolerance) or (step < 0 and x < b - tolerance):
            return
        yield x
        k += 1


def make_range(a, b, step):
    if not is_number(a):
        raise GaloRuntimeError("G302", f"O valor inicial do 'para' deve ser um número, mas é {article(type_name(a))}.")
    if not is_number(b):
        raise GaloRuntimeError("G302", f"O valor final do 'para' deve ser um número, mas é {article(type_name(b))}.")
    if step is None:
        step = 1 if a <= b else -1
    elif not is_number(step):
        raise GaloRuntimeError("G302", f"O passo do 'para' deve ser um número, mas é {article(type_name(step))}.")
    elif step == 0:
        raise GaloRuntimeError("G316", "O passo do 'para' não pode ser zero: o laço nunca terminaria.")
    if type(a) is int and type(b) is int and type(step) is int:
        return iter(range(a, b + (1 if step > 0 else -1), step))
    return _float_range(a, b, step)


def make_repeat(n):
    if type(n) is not int:
        raise GaloRuntimeError("G302", f"A quantidade do 'repita' deve ser um inteiro, mas é {article(type_name(n))}.")
    return iter(range(max(0, n)))
