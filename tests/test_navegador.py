"""VM da GALO para o navegador (galo/web/galo.js), testada com o gjs.

O mesmo .galoc é executado nas duas máquinas virtuais (Python e JavaScript) e as
saídas precisam ser idênticas. As funções de página são testadas com um DOM simulado.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from auxiliar import ESPERADO, EXEMPLOS, RAIZ, galo_cli
from galo.compiler.bytecode import Op
from galo.stdlib import BUILTINS, CONSTANTS

GJS = shutil.which("gjs")
GALO_JS = os.path.join(RAIZ, "galo", "web", "galo.js")
JS = os.path.join(RAIZ, "tests", "js")
CONFORMIDADE = os.path.join(RAIZ, "tests", "conformidade")
DETERMINISTICOS = ["ola_mundo", "fatorial", "fibonacci", "listas", "mapas", "maquina_turing", "brainfuck",
                   "erros", "primos", "ordenacao", "closures", "hanoi"]


def ler(caminho):
    with open(caminho, encoding="utf-8") as f:
        return f.read()


@unittest.skipUnless(GJS, "gjs não está instalado (necessário para executar JavaScript fora do navegador)")
class TestVMNavegador(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.pasta = cls._tmp.name

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def compilar(self, fonte_galo):
        saida = os.path.join(self.pasta, os.path.basename(fonte_galo) + "c")
        r = galo_cli("compilar", fonte_galo, "-o", saida)
        self.assertEqual(r.returncode, 0, r.stderr)
        return saida

    def rodar_js(self, executor, galoc, *entradas):
        saida = galoc + ".saida"
        r = subprocess.run([GJS, os.path.join(JS, executor), GALO_JS, galoc, saida, *entradas],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return ler(saida)

    def test_mesmos_codigos_de_instrucao(self):
        bloco = re.search(r"const OP = \{(.*?)\};", ler(GALO_JS), re.S).group(1)
        js = {nome: int(n) for nome, n in re.findall(r"(\w+): (\d+)", bloco)}
        self.assertEqual(js, {op.name: int(op) for op in Op})

    def test_toda_funcao_interna_existe_ou_e_so_do_servidor(self):
        roteiro = os.path.join(self.pasta, "listar.js")
        with open(roteiro, "w", encoding="utf-8") as f:
            f.write("const GLib = imports.gi.GLib;\n"
                    f"(0, eval)(new TextDecoder().decode(GLib.file_get_contents({json.dumps(GALO_JS)})[1]));\n"
                    "const i = globalThis.Galo._internos;\n"
                    "print(JSON.stringify({b: [...i.BUILTINS.keys()], s: [...i.SOMENTE_SERVIDOR]}));\n")
        dados = json.loads(subprocess.run([GJS, roteiro], capture_output=True, text=True, timeout=30).stdout)
        python = set(BUILTINS) | set(CONSTANTS)
        self.assertEqual(python - set(dados["b"]) - set(dados["s"]), set(), "funções sem versão no navegador")
        self.assertEqual(set(dados["b"]) - python, set(), "funções do navegador desconhecidas pelo compilador")

    def test_exemplos_tem_a_mesma_saida(self):
        for nome in DETERMINISTICOS + ["calculadora"]:
            with self.subTest(exemplo=nome):
                galoc = self.compilar(os.path.join(EXEMPLOS, nome + ".galo"))
                entrada = os.path.join(ESPERADO, nome + ".entrada")
                linhas = ler(entrada).splitlines() if os.path.exists(entrada) else []
                self.assertEqual(self.rodar_js("rodar_galoc.js", galoc, *linhas), ler(os.path.join(ESPERADO, nome + ".saida")))

    def test_programas_de_conformidade(self):
        for nome in ("linguagem", "biblioteca", "matematica", "site"):
            with self.subTest(programa=nome):
                fonte = os.path.join(CONFORMIDADE, nome + ".galo")
                python = galo_cli("executar", fonte)
                self.assertEqual(python.returncode, 0, python.stderr)
                self.assertEqual(self.rodar_js("rodar_galoc.js", self.compilar(fonte)), python.stdout)

    def test_erro_de_execucao_no_navegador(self):
        fonte = os.path.join(self.pasta, "falha.galo")
        with open(fonte, "w", encoding="utf-8") as f:
            f.write("função f(l)\n    retorne l[3]\nfim\nmostre \"antes\"\nmostre f([1])\n")
        saida = self.rodar_js("rodar_galoc.js", self.compilar(fonte))
        self.assertTrue(saida.startswith("antes\nErro GALO [G304] — erro de execução\nArquivo: falha.galo\nLinha: 2, coluna: 14"), saida)
        self.assertIn("função f, linha 2", saida)

    def test_bytecode_corrompido_e_recusado(self):
        galoc = self.compilar(os.path.join(EXEMPLOS, "ola_mundo.galo"))
        with open(galoc, "rb") as f:
            dados = bytearray(f.read())
        dados[30] ^= 0xFF
        ruim = os.path.join(self.pasta, "ruim.galoc")
        with open(ruim, "wb") as f:
            f.write(dados)
        self.assertIn("[G502]", self.rodar_js("rodar_galoc.js", ruim))

    def test_funcoes_de_pagina(self):
        galoc = self.compilar(os.path.join(CONFORMIDADE, "pagina.galo"))
        self.assertEqual(self.rodar_js("dom_falso.js", galoc), ler(os.path.join(ESPERADO, "navegador", "pagina.saida")))

    def test_frontend_do_aplicativo_de_tarefas(self):
        galoc = self.compilar(os.path.join(EXEMPLOS, "tarefas", "cliente.galo"))
        self.assertEqual(self.rodar_js("cliente_tarefas.js", galoc), ler(os.path.join(ESPERADO, "navegador", "tarefas.saida")))


if __name__ == "__main__":
    unittest.main()
