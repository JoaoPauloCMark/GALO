import io
import unittest

from auxiliar import galo_cli
from galo.cli.repl import run_repl
from galo.errors import CompilationError, GaloRuntimeError
from galo.session import Session


def sessao():
    out = io.StringIO()
    return Session(out=out), out


def repl(*linhas):
    entradas = list(linhas)
    out, err = io.StringIO(), io.StringIO()

    def ler(prompt=""):
        if not entradas:
            raise EOFError
        return entradas.pop(0)

    codigo = run_repl(input_fn=ler, out=out, err=err, banner=False)
    return codigo, out.getvalue(), err.getvalue()


class TestSessao(unittest.TestCase):
    def test_variaveis_e_funcoes_persistem(self):
        s, out = sessao()
        s.execute("defina x como 10")
        s.execute("função dobro(n)\n    retorne n * 2\nfim")
        s.execute("x = dobro(x)")
        s.execute("mostre x")
        self.assertEqual(out.getvalue(), "20\n")

    def test_expressoes_mostram_o_valor(self):
        s, out = sessao()
        s.execute("defina nome como \"Ana\"")
        s.execute("nome")
        s.execute("1 + 2")
        s.execute("nulo")
        self.assertEqual(out.getvalue(), '"Ana"\n3\n')

    def test_redefinir_no_repl_e_permitido(self):
        s, out = sessao()
        s.execute("defina x como 1")
        s.execute("defina x como \"agora texto\"")
        s.execute("função f()\n    retorne 1\nfim")
        s.execute("função f()\n    retorne 2\nfim")
        s.execute("mostre x, f()")
        self.assertEqual(out.getvalue(), "agora texto 2\n")

    def test_erro_nao_destroi_a_sessao(self):
        s, out = sessao()
        s.execute("defina x como 5")
        with self.assertRaises(CompilationError):
            s.execute("mostre y")
        with self.assertRaises(GaloRuntimeError):
            s.execute("mostre x / 0")
        s.execute("mostre x")
        self.assertEqual(out.getvalue(), "5\n")

    def test_definicao_que_falhou_nao_fica_registrada(self):
        s, out = sessao()
        with self.assertRaises(GaloRuntimeError):
            s.execute("defina z como 1 / 0")
        with self.assertRaises(CompilationError):
            s.execute("mostre z")

    def test_closures_sobrevivem_entre_entradas(self):
        s, out = sessao()
        s.execute("função contador()\n    defina n como 0\n    retorne função()\n        n += 1\n        retorne n\n    fim\nfim")
        s.execute("defina c como contador()")
        s.execute("c()")
        s.execute("c()")
        self.assertEqual(out.getvalue(), "1\n2\n")

    def test_constantes_continuam_protegidas(self):
        s, _ = sessao()
        s.execute("constante LIMITE como 3")
        with self.assertRaises(CompilationError) as ctx:
            s.execute("LIMITE = 4")
        self.assertEqual(ctx.exception.errors[0].code, "G206")


class TestLaçoInterativo(unittest.TestCase):
    def test_blocos_em_varias_linhas(self):
        codigo, out, err = repl("se 2 > 1 então", "    mostre \"sim\"", "fim", ":sair")
        self.assertEqual(codigo, 0)
        self.assertIn("sim", out)
        self.assertEqual(err, "")

    def test_estado_preservado_e_comandos(self):
        codigo, out, err = repl("defina a como 1", "a += 41", "a", ":variaveis", ":ajuda")
        self.assertIn("42\n", out)
        self.assertIn("variável", out)
        self.assertIn(":carregar", out)

    def test_erros_sao_mostrados_e_o_repl_continua(self):
        codigo, out, err = repl("mostre nada", "mostre 7")
        self.assertIn("[G201]", err)
        self.assertIn("7\n", out)

    def test_linha_em_branco_forca_avaliacao(self):
        codigo, out, err = repl("defina x como [1,", "", "mostre 3")
        self.assertIn("[G105]", err)
        self.assertIn("3\n", out)

    def test_sair_com_codigo(self):
        codigo, _, _ = repl("sair(3)")
        self.assertEqual(codigo, 3)

    def test_repl_por_processo(self):
        r = galo_cli("repl", entrada="defina x como 2\nfunção quadrado(n)\n  retorne n * n\nfim\nquadrado(x + 1)\n")
        self.assertEqual(r.returncode, 0)
        self.assertIn("9", r.stdout)


if __name__ == "__main__":
    unittest.main()
