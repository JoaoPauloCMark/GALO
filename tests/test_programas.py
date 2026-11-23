"""Executa os programas completos de examples/ e compara com as saídas esperadas."""

import os
import unittest

from auxiliar import ESPERADO, EXEMPLOS, galo_cli


def ler(caminho):
    with open(caminho, encoding="utf-8") as f:
        return f.read()


class TestProgramasCompletos(unittest.TestCase):
    def test_saidas_esperadas(self):
        nomes = sorted(n[:-6] for n in os.listdir(ESPERADO) if n.endswith(".saida"))
        self.assertGreaterEqual(len(nomes), 12)
        for nome in nomes:
            with self.subTest(programa=nome):
                entrada_path = os.path.join(ESPERADO, nome + ".entrada")
                entrada = ler(entrada_path) if os.path.exists(entrada_path) else ""
                r = galo_cli("executar", os.path.join(EXEMPLOS, nome + ".galo"), entrada=entrada)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(r.stderr, "")
                self.assertEqual(r.stdout, ler(os.path.join(ESPERADO, nome + ".saida")))

    def test_mesma_saida_via_bytecode(self):
        import tempfile

        with tempfile.TemporaryDirectory() as pasta:
            for nome in ("maquina_turing", "brainfuck", "closures"):
                with self.subTest(programa=nome):
                    saida = os.path.join(pasta, nome + ".galoc")
                    self.assertEqual(galo_cli("compilar", os.path.join(EXEMPLOS, nome + ".galo"), "-o", saida).returncode, 0)
                    r = galo_cli("rodar", saida)
                    self.assertEqual(r.stdout, ler(os.path.join(ESPERADO, nome + ".saida")))

    def test_programas_nao_deterministicos(self):
        r = galo_cli("executar", os.path.join(EXEMPLOS, "jogo_adivinhacao.galo"), "7",
                     entrada="\n".join(str(n) for n in range(1, 101)) + "\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Acertou em", r.stdout)
        with __import__("tempfile").TemporaryDirectory() as pasta:
            r = galo_cli("executar", os.path.join(EXEMPLOS, "arquivos_e_datas.galo"), cwd=pasta)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("2: SEGUNDA LINHA", r.stdout)
            self.assertIn("Soma de 1 a 10000 = 50005000", r.stdout)

    def test_todos_os_exemplos_passam_na_verificacao(self):
        exemplos = sorted(n for n in os.listdir(EXEMPLOS) if n.endswith(".galo"))
        r = galo_cli("verificar", *[os.path.join(EXEMPLOS, n) for n in exemplos])
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
