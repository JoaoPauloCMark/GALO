"""Testes de robustez (fuzzing) com sementes fixas, para serem reproduzíveis.

* O compilador nunca pode falhar com um erro interno do Python: diante de qualquer texto,
  ele compila ou devolve diagnósticos GALO.
* O leitor de bytecode recusa arquivos corrompidos com erros GALO (G502/G503).
* As duas máquinas virtuais (Python e JavaScript) dão o mesmo resultado para centenas de
  expressões aritméticas aleatórias, inclusive erros.
"""

import io
import os
import random
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib

from auxiliar import EXEMPLOS, RAIZ, galo_cli
from galo import BYTECODE_VERSION
from galo.compiler import compile_source
from galo.compiler.bytecode import MAGIC, dump_module, load_module
from galo.compiler.tokens import KEYWORDS
from galo.errors import CompilationError, GaloBytecodeError
from galo.runtime.vm import VM

GJS = shutil.which("gjs")


def fontes_de_exemplo():
    caminhos = []
    for raiz, _, arquivos in os.walk(EXEMPLOS):
        caminhos += [os.path.join(raiz, a) for a in arquivos if a.endswith(".galo")]
    conformidade = os.path.join(RAIZ, "tests", "conformidade")
    caminhos += [os.path.join(conformidade, a) for a in os.listdir(conformidade) if a.endswith(".galo")]
    textos = []
    for c in sorted(caminhos):
        with open(c, encoding="utf-8") as f:
            textos.append(f.read())
    return textos


PEDACOS = list(KEYWORDS) + ["cada", "de", "até", "passo", "vezes", "do tipo", "x", "lista", "f", "Ponto", "eu.x",
                            "1", "2.5", "1e3", '"texto"', '"a {x} b"', "'cru'", '"""\nmulti\n"""', "[", "]", "(", ")",
                            "{", "}", ",", ":", ".", ";", "+", "-", "*", "/", "//", "%", "^", "==", "!=", "<", "<=",
                            ">", ">=", "=", "+=", "\n", "\n", "\n", "#c\n", "#[ b ]#", "<id:inteiro>", "\\", "ç", "🐓"]


def compila_sem_falha_interna(fonte: str) -> None:
    try:
        compile_source(fonte, "fuzz.galo")
    except CompilationError:
        pass


class TestCompiladorNaoQuebra(unittest.TestCase):
    def verificar(self, fonte, descricao):
        try:
            compila_sem_falha_interna(fonte)
        except RecursionError:
            pass  # aninhamento absurdo: aceito como limite do analisador recursivo
        except Exception as exc:  # noqa: BLE001 - é exatamente o que queremos detectar
            self.fail(f"falha interna do compilador ({descricao}): {exc!r}\n--- fonte ---\n{fonte[:600]}")

    def test_programas_mutilados(self):
        rnd = random.Random(2026)
        fontes = fontes_de_exemplo()
        for i in range(2500):
            fonte = rnd.choice(fontes)
            mutacao = rnd.randrange(6)
            p = rnd.randrange(len(fonte) + 1)
            if mutacao == 0:
                fonte = fonte[:p] + fonte[p + rnd.randint(1, 8):]
            elif mutacao == 1:
                fonte = fonte[:p] + rnd.choice(PEDACOS) + fonte[p:]
            elif mutacao == 2:
                fonte = fonte[:p]
            elif mutacao == 3:
                linhas = fonte.split("\n")
                j = rnd.randrange(len(linhas))
                linhas.insert(j, linhas[rnd.randrange(len(linhas))])
                fonte = "\n".join(linhas)
            elif mutacao == 4:
                linhas = fonte.split("\n")
                rnd.shuffle(linhas)
                fonte = "\n".join(linhas[: rnd.randint(1, len(linhas))])
            else:
                fonte = fonte.replace(rnd.choice(["fim", "então", "faça", "(", ")", "\"", ",", "como"]), "", 1)
            self.verificar(fonte, f"mutação {mutacao}, caso {i}")

    def test_sequencias_aleatorias_de_pedacos(self):
        rnd = random.Random(7)
        for i in range(2500):
            fonte = " ".join(rnd.choice(PEDACOS) for _ in range(rnd.randint(1, 40)))
            self.verificar(fonte, f"sequência {i}")

    def test_bytes_aleatorios(self):
        rnd = random.Random(11)
        for i in range(500):
            dados = bytes(rnd.randrange(256) for _ in range(rnd.randint(1, 200)))
            self.verificar(dados.decode("utf-8", "replace"), f"bytes {i}")


class TestBytecodeCorrompido(unittest.TestCase):
    def test_corrupcoes_com_crc_recalculado(self):
        """Corrompe o conteúdo e recalcula o CRC: o verificador precisa barrar ou aceitar sem quebrar."""
        rnd = random.Random(5)
        modulos = []
        for nome in ("fatorial", "closures", "erros", "brainfuck"):
            with open(os.path.join(EXEMPLOS, nome + ".galo"), encoding="utf-8") as f:
                modulos.append(dump_module(compile_source(f.read(), nome + ".galo").module))
        aceitos = recusados = 0
        for i in range(1500):
            dados = bytearray(rnd.choice(modulos))
            conteudo = dados[len(MAGIC) + 2:-4]
            for _ in range(rnd.randint(1, 4)):
                if rnd.random() < 0.8:
                    conteudo[rnd.randrange(len(conteudo))] = rnd.randrange(256)
                else:
                    corte = rnd.randrange(len(conteudo))
                    del conteudo[corte:corte + rnd.randint(1, 10)]
            arquivo = MAGIC + struct.pack("<H", BYTECODE_VERSION) + bytes(conteudo) + struct.pack("<I", zlib.crc32(bytes(conteudo)))
            try:
                load_module(arquivo)
                aceitos += 1
            except GaloBytecodeError:
                recusados += 1
            except Exception as exc:  # noqa: BLE001
                self.fail(f"falha interna ao ler bytecode corrompido (caso {i}): {exc!r}")
        self.assertGreater(recusados, 1000)


def expressoes_aleatorias(rnd: random.Random, n: int) -> list[str]:
    def numero():
        escolha = rnd.randrange(6)
        if escolha == 0:
            return str(rnd.randint(0, 10))
        if escolha == 1:
            return str(rnd.randint(-10 ** 25, 10 ** 25))
        if escolha == 2:
            return f"{rnd.randint(0, 999)}.{rnd.randint(0, 999):03d}"
        if escolha == 3:
            return rnd.choice(["0", "0.0", "1", "-1", "2", "0.1", "1e300", "1e-300", "7"])
        if escolha == 4:
            return f"{rnd.randint(1, 9)}e{rnd.randint(-20, 20)}"
        return str(rnd.randint(-1000, 1000))

    def expr(prof):
        if prof == 0 or rnd.random() < 0.3:
            return numero()
        op = rnd.choice(["+", "-", "*", "/", "//", "%", "^", "u-", "()"])
        if op == "u-":
            return f"-({expr(prof - 1)})"
        if op == "()":
            return f"({expr(prof - 1)})"
        if op == "^":
            return f"({expr(prof - 1)}) ^ {rnd.choice(['0', '1', '2', '3', '-1', '-2', '0.5', '10'])}"
        return f"({expr(prof - 1)}) {op} ({expr(prof - 1)})"

    return [expr(rnd.randint(1, 4)) for _ in range(n)]


@unittest.skipUnless(GJS, "gjs não está instalado")
class TestAritmeticaIgualNasDuasVMs(unittest.TestCase):
    def test_expressoes_aleatorias(self):
        for semente in (42, 7, 2026):
            with self.subTest(semente=semente):
                self._comparar(random.Random(semente))

    def _comparar(self, rnd):
        linhas = ["função avaliar(f)", "    tente", "        defina v como f()",
                  '        retorne "{tipo(v)} {v} {formatar(v, 3)} {arredondar(v)}"',
                  "    capture erro", '        retorne "erro {erro.código}"', "    fim", "fim"]
        for i, e in enumerate(expressoes_aleatorias(rnd, 600)):
            linhas.append(f"mostre {i}, avaliar(função() retorne {e} fim)")
        linhas.append("mostre 1 / 3 * 3, 2 ^ 0.5 * 2 ^ 0.5, 0.1 * 3, 1e22, 1e21, 123456789.123456789, -1e-7, 5e-324")
        fonte = "\n".join(linhas) + "\n"
        with tempfile.TemporaryDirectory() as pasta:
            programa = os.path.join(pasta, "aritmetica.galo")
            with open(programa, "w", encoding="utf-8") as f:
                f.write(fonte)
            python = galo_cli("executar", programa)
            self.assertEqual(python.returncode, 0, python.stderr)
            galoc = os.path.join(pasta, "aritmetica.galoc")
            self.assertEqual(galo_cli("compilar", programa, "-o", galoc).returncode, 0)
            saida = os.path.join(pasta, "js.txt")
            r = subprocess.run([GJS, os.path.join(RAIZ, "tests", "js", "rodar_galoc.js"),
                                os.path.join(RAIZ, "galo", "web", "galo.js"), galoc, saida],
                               capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(saida, encoding="utf-8") as f:
                js = f.read()
        diferencas = [(p, j) for p, j in zip(python.stdout.splitlines(), js.splitlines()) if p != j]
        self.assertEqual(len(python.stdout.splitlines()), len(js.splitlines()))
        self.assertEqual(diferencas[:10], [], f"{len(diferencas)} linhas diferentes (Python, JavaScript)")
        self.assertIn("erro G303", python.stdout)  # o gerador produz divisões por zero


def chamadas_matematicas_aleatorias(rnd: random.Random, n: int) -> list[str]:
    def numero():
        escolha = rnd.randrange(7)
        if escolha == 0:
            return repr(rnd.uniform(-10, 10))
        if escolha == 1:
            return repr(rnd.uniform(0, 1e-3))
        if escolha == 2:
            return f"{rnd.randint(1, 9)}e{rnd.randint(-300, 300)}"
        if escolha == 3:
            return str(rnd.randint(-1000, 1000))
        if escolha == 4:  # qualquer decimal positivo, de 5e-324 a 1.8e308
            return repr(struct.unpack("<d", struct.pack("<Q", rnd.getrandbits(63)))[0])
        if escolha == 5:
            return repr(rnd.uniform(0, 100))
        return rnd.choice(["0", "0.0", "1", "1.0", "2", "10", "0.5", "pi", "pi / 2", "pi / 4", "3 * pi / 2",
                           "1e22", "1e300", "5e-324", "2.2250738585072014e-308", "1.7976931348623157e308"])

    modelos = ["seno({a})", "cosseno({a})", "tangente({a})", "logaritmo({a})", "logaritmo({a}, {b})", "({a}) ^ ({b})",
               "absoluto({a}) ^ 0.5", "absoluto({a}) ^ (1 / 3)", "raiz({a})", "potência(absoluto({a}), {b})"]
    return [rnd.choice(modelos).format(a=numero(), b=numero()) for _ in range(n)]


@unittest.skipUnless(GJS, "gjs não está instalado")
class TestMatematicaIgualNasDuasVMs(unittest.TestCase):
    """seno, cosseno, tangente, logaritmo, raiz e potências fracionárias: mesmos bits nas duas VMs."""

    def test_chamadas_aleatorias(self):
        for semente in (99, 2027):
            with self.subTest(semente=semente):
                rnd = random.Random(semente)
                linhas = ["função f(g)", "    tente", "        defina v como g()", '        retorne "{v}"',
                          "    capture erro", '        retorne "erro {erro.código}"', "    fim", "fim"]
                for i, chamada in enumerate(chamadas_matematicas_aleatorias(rnd, 1200)):
                    linhas.append(f"mostre {i}, f(função() retorne {chamada} fim)")
                linhas += ["semente_aleatória(" + str(semente) + ")", "defina xs como []",
                           "para i de 1 até 300 faça", "    adicionar(xs, aleatório())",
                           "    adicionar(xs, aleatório_entre(-5, 5))", "    adicionar(xs, aleatório_entre(0, 10 ^ 40))", "fim",
                           "mostre xs"]
                python, js = executar_nas_duas_vms("\n".join(linhas) + "\n")
                self.assertEqual(len(python), len(js))
                diferencas = [(p, j) for p, j in zip(python, js) if p != j]
                self.assertEqual(diferencas[:10], [], f"{len(diferencas)} linhas diferentes (Python, JavaScript)")
                self.assertTrue(any("erro G317" in linha for linha in python))  # há estouros entre os casos


def executar_nas_duas_vms(fonte: str) -> tuple[list[str], list[str]]:
    with tempfile.TemporaryDirectory() as pasta:
        programa = os.path.join(pasta, "programa.galo")
        with open(programa, "w", encoding="utf-8") as f:
            f.write(fonte)
        python = galo_cli("executar", programa)
        assert python.returncode == 0, python.stderr
        galoc = os.path.join(pasta, "programa.galoc")
        assert galo_cli("compilar", programa, "-o", galoc).returncode == 0
        saida = os.path.join(pasta, "js.txt")
        r = subprocess.run([GJS, os.path.join(RAIZ, "tests", "js", "rodar_galoc.js"),
                            os.path.join(RAIZ, "galo", "web", "galo.js"), galoc, saida],
                           capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stderr
        with open(saida, encoding="utf-8") as f:
            return python.stdout.splitlines(), f.read().splitlines()


class TestExecucaoNaoQuebra(unittest.TestCase):
    def test_operacoes_entre_todos_os_tipos(self):
        """Cada operador aplicado a cada par de tipos: resultado ou erro GALO, nunca falha interna."""
        valores = ['0', '1', '2.5', '"a"', 'verdadeiro', 'nulo', '[1]', '{"k": 1}', 'tamanho', 'função() fim', 'R(1)']
        ops = ["+", "-", "*", "/", "//", "%", "^", "==", "!=", "<", "<=", ">", ">=", "em", "e", "ou"]
        linhas = ['registro R(a)']
        linhas += ["defina vals como [" + ", ".join(valores) + "]", "defina total como 0", "defina erros como {}"]
        for op in ops:
            linhas += [
                "para cada a em vals faça", "    para cada b em vals faça", "        tente",
                f"            defina r como a {op} b", "            total += 1", "        capture erro",
                "            erros[erro.código] = obter(erros, erro.código, 0) + 1", "        fim", "    fim", "fim"]
        for un in ("-", "não "):
            linhas += ["para cada a em vals faça", "    tente", f"        defina r como {un}a", "    capture erro",
                       "        erros[erro.código] = obter(erros, erro.código, 0) + 1", "    fim", "fim"]
        linhas += ["para cada a em vals faça", "    para cada b em vals faça", "        tente",
                   "            mostre a[b]", "        capture erro", "            total += 0", "        fim", "    fim", "fim"]
        linhas.append("mostre total, chaves(erros)")
        out = io.StringIO()
        resultado = compile_source("\n".join(linhas) + "\n", "tipos.galo")
        VM(out=out).run(resultado.module)
        ultima = out.getvalue().strip().splitlines()[-1]
        self.assertTrue(ultima.split()[0].isdigit(), ultima)
        for codigo in ("G302", "G303", "G310"):
            self.assertIn(codigo, ultima)


if __name__ == "__main__":
    unittest.main()
