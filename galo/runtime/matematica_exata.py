"""Funções matemáticas com arredondamento correto e resultado idêntico em qualquer plataforma.

seno, cosseno, tangente, logaritmo e potência com expoente não inteiro são calculados com
inteiros de precisão arbitrária (ponto fixo binário). Cada cálculo produz um intervalo que
contém o valor exato; se as duas pontas do intervalo arredondam para o mesmo decimal
(IEEE 754 de 64 bits), esse é o resultado — o decimal mais próximo do valor exato. Se não,
o cálculo é refeito com o dobro da precisão (estratégia de Ziv).

O resultado não depende da biblioteca matemática do sistema: a VM do navegador
(galo/web/galo.js) implementa exatamente os mesmos passos e chega aos mesmos bits.
Todas as divisões e deslocamentos operam sobre inteiros não negativos, para que Python
e JavaScript (BigInt) se comportem da mesma forma.
"""

from __future__ import annotations

import math
from fractions import Fraction

PRECISOES = (96, 192, 384, 768, 1536, 3072, 6144)

_cache_pi: dict[int, int] = {}
_cache_ln2: dict[int, int] = {}


# ---------------------------------------------------------------- constantes


def _atan_inverso(n: int, p: int) -> int:
    """atan(1/n) · 2^p (erro menor que o número de termos)."""
    x = (1 << p) // n
    n2 = n * n
    total = 0
    k = 1
    positivo = True
    while x:
        total = total + x // k if positivo else total - x // k
        x //= n2
        k += 2
        positivo = not positivo
    return total


def _atanh_inverso(n: int, p: int) -> int:
    """atanh(1/n) · 2^p."""
    x = (1 << p) // n
    n2 = n * n
    total = 0
    k = 1
    while x:
        total += x // k
        x //= n2
        k += 2
    return total


def pi_fixo(p: int) -> int:
    """π · 2^p (erro menor que 2 unidades)."""
    v = _cache_pi.get(p)
    if v is None:
        g = p + 24
        v = (16 * _atan_inverso(5, g) - 4 * _atan_inverso(239, g)) >> 24
        _cache_pi[p] = v
    return v


def ln2_fixo(p: int) -> int:
    """ln 2 · 2^p (erro menor que 2 unidades)."""
    v = _cache_ln2.get(p)
    if v is None:
        g = p + 24
        v = (2 * _atanh_inverso(3, g)) >> 24
        _cache_ln2[p] = v
    return v


# ---------------------------------------------------------------- arredondamento


def _racional(num: int, den: int) -> float:
    """num / den (den > 0) arredondado corretamente; ±infinito se for grande demais."""
    if num == 0:
        return 0.0
    try:
        if num < 0:
            return -((-num) / den)
        return num / den
    except OverflowError:
        return -math.inf if num < 0 else math.inf


def _unico(candidatos) -> float | None:
    """Se todos os extremos do intervalo arredondam para o mesmo decimal, devolve-o."""
    valores = {_racional(n, d) for n, d in candidatos}
    return valores.pop() if len(valores) == 1 else None


def _decompor(x: float) -> tuple[int, int]:
    """|x| = m / 2^d, com m e d inteiros não negativos."""
    m, d = abs(x).as_integer_ratio()
    return m, d.bit_length() - 1


# ---------------------------------------------------------------- seno, cosseno, tangente


def _seno_cosseno_reduzidos(r: int, p: int) -> tuple[int, int, int]:
    """Para 0 <= r/2^p <= π/4: (sen·2^p, cos·2^p, número de termos)."""
    r2 = (r * r) >> p
    termos = 0
    s, termo, n, positivo = 0, r, 1, True
    while termo:
        s = s + termo if positivo else s - termo
        termo = ((termo * r2) >> p) // ((n + 1) * (n + 2))
        n += 2
        positivo = not positivo
        termos += 1
    c, termo, n, positivo = 0, 1 << p, 0, True
    while termo:
        c = c + termo if positivo else c - termo
        termo = ((termo * r2) >> p) // ((n + 1) * (n + 2))
        n += 2
        positivo = not positivo
        termos += 1
    return s, c, termos


def _trigonometricas(x: float, p: int):
    """(sen|x|·2^p, cos|x|·2^p, erro em unidades de 2^-p) para x finito e diferente de zero."""
    m, d = _decompor(x)
    q = p + max(0, m.bit_length() - d) + 16
    xq = (m << q) >> d if q >= d else m >> (d - q)
    meio_pi = pi_fixo(q) >> 1
    k = (2 * xq + meio_pi) // (2 * meio_pi)
    resto = xq - k * meio_pi
    negativo = resto < 0
    r = abs(resto) >> (q - p)
    erro_r = ((3 * k + 4) >> (q - p)) + 2
    s, c, termos = _seno_cosseno_reduzidos(r, p)
    if negativo:
        s = -s
    quadrante = k % 4
    seno = (s, c, -s, -c)[quadrante]
    cosseno = (c, -s, -c, s)[quadrante]
    return seno, cosseno, erro_r + 3 * termos + 8


def seno(x: float) -> float:
    if x == 0.0:
        return x
    for p in PRECISOES:
        s, _, e = _trigonometricas(x, p)
        if x < 0:
            s = -s
        v = _unico([(s - e, 1 << p), (s + e, 1 << p)])
        if v is not None:
            return v
    return _racional(s, 1 << p)


def cosseno(x: float) -> float:
    if x == 0.0:
        return 1.0
    for p in PRECISOES:
        _, c, e = _trigonometricas(x, p)
        v = _unico([(c - e, 1 << p), (c + e, 1 << p)])
        if v is not None:
            return v
    return _racional(c, 1 << p)


def tangente(x: float) -> float:
    if x == 0.0:
        return x
    for p in PRECISOES:
        s, c, e = _trigonometricas(x, p)
        if x < 0:
            s = -s
        if abs(c) <= e:
            continue
        cand = []
        for sn in (s - e, s + e):
            for cd in (c - e, c + e):
                cand.append((-sn, -cd) if cd < 0 else (sn, cd))
        v = _unico(cand)
        if v is not None:
            return v
    return _racional(s, c) if c > 0 else _racional(-s, -c)


# ---------------------------------------------------------------- logaritmo


def ln_fixo(x: float, p: int) -> tuple[int, int]:
    """(ln x · 2^p, erro) para x > 0 finito."""
    m, d = _decompor(x)
    k = m.bit_length() - 1 - d          # x = 2^k · f, com f em [1, 2)
    num, den = m, 1 << d
    if k >= 0:
        den <<= k
    else:
        num <<= -k
    if num * num >= 2 * den * den:      # f >= √2: usa f/2, em [√2/2, 1)
        k += 1
        den <<= 1
    negativo = num < den
    t = ((abs(num - den)) << p) // (num + den)
    t2 = (t * t) >> p
    soma, termo, j, termos = 0, t, 1, 0
    while termo:
        soma += termo // j
        termo = (termo * t2) >> p
        j += 2
        termos += 1
    ln_f = -2 * soma if negativo else 2 * soma
    ln2 = ln2_fixo(p)
    valor = k * ln2 + ln_f if k >= 0 else ln_f - (-k) * ln2
    return valor, 2 * termos + 2 * abs(k) + 8


def logaritmo(x: float) -> float:
    if x == 1.0:
        return 0.0
    for p in PRECISOES:
        v, e = ln_fixo(x, p)
        r = _unico([(v - e, 1 << p), (v + e, 1 << p)])
        if r is not None:
            return r
    return _racional(v, 1 << p)


def _exato(candidato: float, verificar) -> bool:
    try:
        return verificar(candidato)
    except (OverflowError, ZeroDivisionError, MemoryError):
        return False


def _diadico(v: float, limite_q: int = 8):
    """v = p / 2^q com q pequeno? Devolve (p, q) ou None."""
    n, d = Fraction(v).numerator, Fraction(v).denominator
    q = d.bit_length() - 1
    return (n, q) if q <= limite_q and abs(n) < 4096 else None


def logaritmo_base(x: float, b: float) -> float:
    """ln(x) / ln(b) arredondado corretamente (log de 1000 na base 10 é exatamente 3.0)."""
    if x == 1.0:
        return 0.0
    for p in PRECISOES:
        vx, ex = ln_fixo(x, p)
        vb, eb = ln_fixo(b, p)
        if abs(vb) <= eb:
            continue
        cand = []
        for a in (vx - ex, vx + ex):
            for c in (vb - eb, vb + eb):
                cand.append((-a, -c) if c < 0 else (a, c))
        r = _unico(cand)
        if r is not None:
            return r
        if p >= 192:
            fx, fb = Fraction(x), Fraction(b)
            for v in sorted({_racional(n, d) for n, d in cand}):
                dd = _diadico(v)
                if dd is None:
                    continue
                pp, qq = dd  # b^(pp/2^qq) == x  <=>  b^pp == x^(2^qq)
                if _exato(v, lambda _v: fb ** pp == fx ** (1 << qq)):
                    return v
    return _racional(vx, vb) if vb > 0 else _racional(-vx, -vb)


# ---------------------------------------------------------------- potência


def _exp_fixo(z: int, ez: int, p: int):
    """exp(z / 2^p) como intervalo: devolve (s, es, n), valor = s · 2^n / 2^p ± es · 2^n / 2^p."""
    ln2 = ln2_fixo(p)
    if z >= 0:
        n = (2 * z + ln2) // (2 * ln2)
    else:
        n = -((2 * (-z) + ln2) // (2 * ln2))
    r = z - n * ln2 if n >= 0 else z + (-n) * ln2
    er = ez + 2 * abs(n) + 2
    negativo = r < 0
    ra = abs(r)
    s, termo, i, termos = 0, 1 << p, 0, 0
    positivo = True
    while termo:
        s = s + termo if positivo or not negativo else s - termo
        i += 1
        termo = ((termo * ra) >> p) // i
        if negativo:
            positivo = not positivo
        termos += 1
    return s, 2 * er + 2 * termos + 4, n


def potencia(x: float, y: float) -> float:
    """x ^ y para x > 0 finito e y finito, arredondado corretamente."""
    if x == 1.0 or y == 0.0:
        return 1.0
    fy = Fraction(y)
    py, qy = abs(fy.numerator), fy.denominator
    for p in PRECISOES:
        lx, ex = ln_fixo(x, p)
        produto = abs(lx) * py
        z = produto // qy
        if (lx < 0) != (fy < 0):
            z = -z
        ez = (ex * py) // qy + 2
        if z > 1100 << p:
            raise OverflowError("resultado grande demais")
        if z < -1200 << p:
            return 0.0
        s, es, n = _exp_fixo(z, ez, p)
        if n >= 0:
            cand = [((s - es) << n, 1 << p), ((s + es) << n, 1 << p)]
        else:
            cand = [(s - es, 1 << (p - n)), (s + es, 1 << (p - n))]
        r = _unico(cand)
        if r is not None:
            return r
        if p >= 192:
            dd = _diadico(y)
            if dd is not None:
                yp, yq = dd  # candidato v exato se v^(2^yq) == x^yp
                fx = Fraction(x)
                for v in sorted({_racional(a, b) for a, b in cand}):
                    if v > 0 and _exato(v, lambda vv: Fraction(vv) ** (1 << yq) == fx ** yp):
                        return v
    return _racional(cand[0][0], cand[0][1])


# ---------------------------------------------------------------- números aleatórios

_M32 = 0xFFFFFFFF


def _rotl(x: int, k: int) -> int:
    return ((x << k) | (x >> (32 - k))) & _M32


def _splitmix32(z: int) -> tuple[int, int]:
    z = (z + 0x9E3779B9) & _M32
    r = z
    r = ((r ^ (r >> 16)) * 0x85EBCA6B) & _M32
    r = ((r ^ (r >> 13)) * 0xC2B2AE35) & _M32
    return z, r ^ (r >> 16)


class Aleatorio:
    """Gerador xoshiro128** com semente via splitmix32.

    É o mesmo algoritmo da VM do navegador: com a mesma semente, as duas VMs geram a
    mesma sequência de números.
    """

    def __init__(self, semente: int | None = None) -> None:
        if semente is None:
            import os

            semente = int.from_bytes(os.urandom(8), "little")
        self.seed(semente)

    def seed(self, semente: int) -> None:
        v = semente % (1 << 64)
        baixo, alto = v & _M32, v >> 32
        z = baixo
        estado = []
        for i in range(4):
            z, r = _splitmix32(z)
            estado.append(r ^ alto if i % 2 else r)
        if not any(estado):
            estado[0] = 1
        self.s = estado

    def proximo(self) -> int:
        s = self.s
        resultado = (_rotl((s[1] * 5) & _M32, 7) * 9) & _M32
        t = (s[1] << 9) & _M32
        s[2] ^= s[0]
        s[3] ^= s[1]
        s[1] ^= s[2]
        s[0] ^= s[3]
        s[2] ^= t
        s[3] = _rotl(s[3], 11)
        return resultado

    def random(self) -> float:
        a = self.proximo() >> 5
        b = self.proximo() >> 6
        return (a * 67108864 + b) / 9007199254740992

    def randint(self, a: int, b: int) -> int:
        n = b - a + 1
        bits = (n - 1).bit_length()
        if bits == 0:
            return a
        palavras = (bits + 31) // 32
        while True:
            r = 0
            for _ in range(palavras):
                r = (r << 32) | self.proximo()
            r >>= 32 * palavras - bits
            if r < n:
                return a + r
