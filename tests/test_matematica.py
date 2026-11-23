"""Funções matemáticas: arredondamento correto, casos exatos, erros e gerador aleatório.

A referência é independente da implementação: o módulo `decimal` do Python com 60 dígitos
ou mais (π calculado à parte, séries de Taylor próprias). Um resultado está correto quando
é o decimal (IEEE 754) mais próximo do valor exato — ou seja, igual à referência arredondada.
"""

import math
import random
import struct
import unittest
from decimal import Decimal, localcontext

from auxiliar import erro_de_execucao, executar
from galo.runtime import matematica_exata as exata
from galo.runtime.matematica_exata import Aleatorio
from galo.stdlib import matematica as stdlib_matematica
from galo.errors import GaloRuntimeError

DIGITOS = 60


def _pi(prec):
    """Receita da documentação do módulo decimal (convergência linear, suficiente aqui)."""
    with localcontext() as c:
        c.prec = prec + 5
        three = Decimal(3)
        lasts, t, s, n, na, d, da = 0, three, 3, 1, 0, 0, 24
        while s != lasts:
            lasts = s
            n, na = n + na, na + 8
            d, da = d + da, da + 32
            t = (t * n) / d
            s += t
        return +s


def _reduzir(x):
    """x reduzido para [-π, π] com folga de dígitos proporcional ao tamanho de x."""
    d = Decimal(x)
    prec = DIGITOS + max(0, d.adjusted()) + 10
    pi = _pi(prec)
    with localcontext() as c:
        c.prec = prec
        r = d % (2 * pi)
        if r > pi:
            r -= 2 * pi
        elif r < -pi:
            r += 2 * pi
    return r


def _taylor(r, inicio):
    with localcontext() as c:
        c.prec = DIGITOS + 10
        termo = Decimal(1) if inicio == 0 else +r
        total, n = Decimal(0), inicio
        r2 = r * r
        while True:
            novo = total + termo
            if novo == total:
                return novo
            total = novo
            termo = -termo * r2 / ((n + 1) * (n + 2))
            n += 2


def ref_seno(x):
    return float(_taylor(_reduzir(x), 1))


def ref_cosseno(x):
    return float(_taylor(_reduzir(x), 0))


def ref_tangente(x):
    r = _reduzir(x)
    with localcontext() as c:
        c.prec = DIGITOS + 10
        return float(_taylor(r, 1) / _taylor(r, 0))


def ref_ln(x):
    with localcontext() as c:
        c.prec = DIGITOS
        return float(Decimal(x).ln())


def ref_log_base(x, b):
    with localcontext() as c:
        c.prec = DIGITOS
        return float(Decimal(x).ln() / Decimal(b).ln())


def ref_potencia(x, y):
    with localcontext() as c:
        c.prec = DIGITOS
        v = (Decimal(y) * Decimal(x).ln()).exp()
    try:
        return float(v)
    except OverflowError:
        return math.inf


def decimal_qualquer(rnd):
    """Um decimal positivo finito qualquer (todos os expoentes com a mesma chance)."""
    while True:
        v = struct.unpack("<d", struct.pack("<Q", rnd.getrandbits(63)))[0]
        if math.isfinite(v) and v > 0:
            return v


def amostras(rnd, n):
    vals = []
    for i in range(n):
        escolha = i % 4
        if escolha == 0:
            vals.append(rnd.uniform(-10, 10))
        elif escolha == 1:
            vals.append(rnd.uniform(-1e6, 1e6))
        elif escolha == 2:
            vals.append(rnd.choice([-1, 1]) * rnd.uniform(0, 1) * 10 ** rnd.randint(-30, 30))
        else:
            vals.append(rnd.choice([-1, 1]) * decimal_qualquer(rnd))
    return vals


class TestArredondamentoCorreto(unittest.TestCase):
    def comparar(self, nome, funcao, referencia, entradas):
        errados = []
        for args in entradas:
            obtido, esperado = funcao(*args), referencia(*args)
            if obtido != esperado and not (math.isnan(obtido) and math.isnan(esperado)):
                errados.append((args, obtido, esperado))
        self.assertEqual(errados[:5], [], f"{nome}: {len(errados)} de {len(entradas)} resultados não são o decimal mais próximo")

    def test_seno_cosseno_tangente(self):
        rnd = random.Random(31)
        xs = [(x,) for x in amostras(rnd, 400) if x != 0]
        xs += [(1e22,), (1e300,), (5e-324,), (math.pi,), (math.pi / 2,), (1.7976931348623157e308,), (-1e22,), (355.0,)]
        self.comparar("seno", exata.seno, ref_seno, xs)
        self.comparar("cosseno", exata.cosseno, ref_cosseno, xs)
        self.comparar("tangente", exata.tangente, ref_tangente, xs)

    def test_logaritmo(self):
        rnd = random.Random(32)
        xs = [(abs(x),) for x in amostras(rnd, 600) if x != 0]
        xs += [(5e-324,), (1.7976931348623157e308,), (1.0000000000000002,), (0.9999999999999999,), (2.0,), (math.e,)]
        self.comparar("logaritmo", exata.logaritmo, ref_ln, xs)

    def test_logaritmo_com_base(self):
        rnd = random.Random(33)
        pares = []
        for _ in range(300):
            x = abs(rnd.choice(amostras(rnd, 4))) or 1.5
            b = rnd.choice([2.0, 10.0, 0.5, math.e, rnd.uniform(0.01, 100), decimal_qualquer(rnd)])
            if b != 1.0:
                pares.append((x, b))
        self.comparar("logaritmo com base", exata.logaritmo_base, ref_log_base, pares)

    def test_potencia_fracionaria(self):
        rnd = random.Random(34)
        pares = []
        while len(pares) < 500:
            x = abs(rnd.choice(amostras(rnd, 4)))
            y = rnd.choice([rnd.uniform(-5, 5), rnd.uniform(-300, 300), 0.5, 1 / 3, -0.25, rnd.uniform(-1, 1) * 10 ** rnd.randint(-10, 3)])
            if x == 0 or x == 1 or y == 0:
                continue
            if abs(y * math.log(x)) > 700:  # estouro ou resultado subnormal extremo: testado à parte
                continue
            pares.append((x, y))
        self.comparar("potência", exata.potencia, ref_potencia, pares)

    def test_onde_a_plataforma_erra_a_galo_acerta(self):
        """Na faixa usual (0 a 1000), a biblioteca do sistema (glibc) erra o último dígito de
        seno, cosseno, tangente e potência algumas vezes em cada mil; a GALO não pode errar nenhuma."""
        rnd = random.Random(35)
        erros_plataforma, erros_galo = 0, []
        for _ in range(1500):
            x, y = rnd.uniform(0, 1000), rnd.uniform(-3, 3)
            for nome, galo, plataforma, ref in (("seno", exata.seno, math.sin, ref_seno),
                                                ("cosseno", exata.cosseno, math.cos, ref_cosseno),
                                                ("tangente", exata.tangente, math.tan, ref_tangente),
                                                ("logaritmo", exata.logaritmo, math.log, ref_ln)):
                esperado = ref(x)
                erros_plataforma += plataforma(x) != esperado
                if galo(x) != esperado:
                    erros_galo.append((nome, x))
            esperado = ref_potencia(x, y)
            erros_plataforma += x ** y != esperado
            if exata.potencia(x, y) != esperado:
                erros_galo.append(("potência", x, y))
        self.assertEqual(erros_galo, [])


class TestResultadosExatos(unittest.TestCase):
    def test_logaritmos_exatos(self):
        casos = {(1000, 10): 3.0, (0.125, 2): -3.0, (2, 4): 0.5, (1e-300, 10): -300.0, (3 ** 20, 3): 20.0,
                 (10, 0.1): -1.0, (8, 2): 3.0, (1024, 2): 10.0, (1, 7): 0.0, (9, 27): 2 / 3}
        for (x, b), esperado in casos.items():
            with self.subTest(x=x, b=b):
                self.assertEqual(exata.logaritmo_base(float(x), float(b)), esperado)

    def test_potencias_exatas(self):
        casos = {(2.25, 0.5): 1.5, (8.0, 1 / 3): 2.0, (16.0, 0.25): 2.0, (1e22, 0.5): 1e11, (4.0, -0.5): 0.5,
                 (1.0, 1e300): 1.0, (0.25, 1.5): 0.125, (1024.0, 0.1): 2.0}
        for (x, y), esperado in casos.items():
            with self.subTest(x=x, y=y):
                self.assertEqual(exata.potencia(x, y), esperado)

    def test_casos_especiais(self):
        self.assertEqual(math.copysign(1, exata.seno(-0.0)), -1)
        self.assertEqual(exata.cosseno(0.0), 1.0)
        self.assertEqual(exata.logaritmo(1.0), 0.0)
        self.assertEqual(exata.potencia(0.5, 1e300), 0.0)
        self.assertEqual(exata.potencia(2.0, -1074.0), 5e-324)
        self.assertEqual(exata.potencia(10.0, 400.5), math.inf)  # a VM transforma em erro G317

    def test_na_linguagem(self):
        saida = executar("mostre seno(1e22), cosseno(1e22), logaritmo(1000, 10), 8 ^ (1 / 3), 2.25 ^ 0.5, potência(16, 0.25)")
        self.assertEqual(saida.strip(), "-0.8522008497671888 0.523214785395139 3.0 2.0 1.5 2.0")
        self.assertEqual(executar("mostre (-0.5) ^ 1025.0 < 0, (-0.5) ^ 1026.0 > 0").strip(), "verdadeiro verdadeiro")


class TestErros(unittest.TestCase):
    def test_erros_de_dominio_e_estouro(self):
        self.assertEqual(erro_de_execucao("mostre 10 ^ 400.5").code, "G317")
        self.assertEqual(erro_de_execucao("mostre seno(10 ^ 400)").code, "G317")
        self.assertEqual(erro_de_execucao("mostre (-8) ^ (1 / 3)").code, "G302")
        self.assertEqual(erro_de_execucao("mostre logaritmo(0)").code, "G322")
        self.assertEqual(erro_de_execucao("mostre logaritmo(8, 1)").code, "G322")
        self.assertEqual(erro_de_execucao("mostre raiz(10 ^ 400 + 1)").code, "G317")
        self.assertEqual(executar("mostre raiz(10 ^ 400)").strip(), "1e+200")

    def test_infinito_e_indefinido_sao_recusados(self):
        for funcao in (stdlib_matematica.seno, stdlib_matematica.cosseno, stdlib_matematica.tangente, stdlib_matematica.logaritmo):
            for valor in (math.inf, -math.inf, math.nan):
                with self.subTest(funcao=funcao.__name__, valor=valor):
                    with self.assertRaises(GaloRuntimeError) as ctx:
                        funcao(None, valor)
                    self.assertEqual(ctx.exception.code, "G322")


class TestGeradorAleatorio(unittest.TestCase):
    def test_vetor_conhecido_do_xoshiro128(self):
        """Saídas do algoritmo de referência xoshiro128** para o estado inicial [1, 2, 3, 4]."""
        g = Aleatorio(0)
        g.s = [1, 2, 3, 4]
        self.assertEqual([g.proximo() for _ in range(4)], [11520, 0, 5927040, 70819200])

    def test_sequencia_fixa(self):
        """A sequência de uma semente não pode mudar: a VM do navegador gera exatamente a mesma."""
        g = Aleatorio(42)
        self.assertEqual([g.random() for _ in range(3)], [0.6606157208001621, 0.1117019639532224, 0.0791056456144914])
        self.assertEqual([g.randint(1, 6) for _ in range(8)], [1, 3, 3, 2, 4, 4, 6, 5])
        self.assertEqual(g.randint(0, 10 ** 30), 131553519435923746554472825188)

    def test_mesma_semente_mesma_sequencia(self):
        a, b, c = Aleatorio(7), Aleatorio(7), Aleatorio(8)
        sa = [a.randint(0, 10 ** 20) for _ in range(50)]
        self.assertEqual(sa, [b.randint(0, 10 ** 20) for _ in range(50)])
        self.assertNotEqual(sa, [c.randint(0, 10 ** 20) for _ in range(50)])
        self.assertEqual(Aleatorio(-1).random(), Aleatorio(2 ** 64 - 1).random())  # semente vale módulo 2^64

    def test_intervalos_e_distribuicao(self):
        g = Aleatorio(123)
        valores = [g.random() for _ in range(20000)]
        self.assertTrue(all(0 <= v < 1 for v in valores))
        self.assertAlmostEqual(sum(valores) / len(valores), 0.5, delta=0.01)
        contagem = [0] * 6
        for _ in range(60000):
            contagem[g.randint(1, 6) - 1] += 1
        self.assertTrue(all(9500 < c < 10500 for c in contagem), contagem)
        self.assertEqual({g.randint(5, 5) for _ in range(10)}, {5})
        grandes = [g.randint(0, 2 ** 100) for _ in range(200)]
        self.assertTrue(all(0 <= v <= 2 ** 100 for v in grandes))
        self.assertGreater(max(grandes), 2 ** 98)


if __name__ == "__main__":
    unittest.main()
