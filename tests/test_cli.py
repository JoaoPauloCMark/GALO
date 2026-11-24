import json
import os
import tempfile
import unittest

from auxiliar import EXEMPLOS, galo_cli


def escrever(pasta, nome, conteudo):
    caminho = os.path.join(pasta, nome)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(conteudo)
    return caminho


class TestCLI(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.pasta = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_versao_e_ajuda(self):
        r = galo_cli("--versao")
        self.assertEqual(r.returncode, 0)
        self.assertTrue(r.stdout.startswith("GALO "))
        r = galo_cli("ajuda")
        self.assertIn("galo executar", r.stdout)
        self.assertIn("galo compilar", r.stdout)

    def test_executar(self):
        r = galo_cli("executar", os.path.join(EXEMPLOS, "ola_mundo.galo"))
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.splitlines()[0], "Olá, João!")

    def test_atalho_arquivo_direto(self):
        r = galo_cli(os.path.join(EXEMPLOS, "ola_mundo.galo"))
        self.assertEqual(r.returncode, 0)

    def test_argumentos_do_programa(self):
        p = escrever(self.pasta, "args.galo", "mostre argumentos()\n")
        r = galo_cli("executar", p, "um", "--dois")
        self.assertEqual(r.stdout, '["um", "--dois"]\n')

    def test_compilar_e_rodar(self):
        p = escrever(self.pasta, "p.galo", 'programa "P"\nmostre "compilado"\n')
        saida = os.path.join(self.pasta, "saida.galoc")
        r = galo_cli("compilar", p, "-o", saida)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.exists(saida))
        r = galo_cli("rodar", saida)
        self.assertEqual((r.returncode, r.stdout), (0, "compilado\n"))
        r = galo_cli(saida)
        self.assertEqual(r.stdout, "compilado\n")

    def test_compilar_nome_padrao(self):
        p = escrever(self.pasta, "x.galo", "mostre 1\n")
        self.assertEqual(galo_cli("compilar", p).returncode, 0)
        self.assertTrue(os.path.exists(os.path.join(self.pasta, "x.galoc")))

    def test_codigos_de_saida(self):
        erro_comp = escrever(self.pasta, "c.galo", "mostre indefinida\n")
        erro_exec = escrever(self.pasta, "e.galo", "mostre 1 / 0\n")
        sair = escrever(self.pasta, "s.galo", "mostre 1\nsair(5)\nmostre 2\n")
        self.assertEqual(galo_cli("executar", erro_comp).returncode, 1)
        r = galo_cli("executar", erro_exec)
        self.assertEqual(r.returncode, 2)
        self.assertIn("Erro GALO [G303]", r.stderr)
        r = galo_cli("executar", sair)
        self.assertEqual((r.returncode, r.stdout), (5, "1\n"))
        self.assertEqual(galo_cli("executar", os.path.join(self.pasta, "nao_existe.galo")).returncode, 3)
        self.assertEqual(galo_cli("comando_inexistente").returncode, 64)
        self.assertEqual(galo_cli("rodar", erro_comp + "c").returncode, 3)

    def test_formato_do_erro(self):
        p = escrever(self.pasta, "exemplo.galo", "# linha de comentário\n" * 7 + "    mostre pontuacao\n")
        r = galo_cli("executar", p)
        linhas = r.stderr.splitlines()
        self.assertEqual(linhas[0], "Erro GALO [G201] — erro semântico")
        self.assertIn("Linha: 8, coluna: 12", r.stderr)
        self.assertIn('A variável "pontuacao" não foi definida.', r.stderr)
        self.assertIn("Sugestão:\nDeclare a variável antes de utilizá-la:\ndefina pontuacao como 0", r.stderr)

    def test_verificar(self):
        ok = escrever(self.pasta, "ok.galo", "mostre 1\n")
        ruim = escrever(self.pasta, "ruim.galo", "mostre x\nse 1 então\nfim\n")
        r = galo_cli("verificar", ok)
        self.assertEqual(r.returncode, 0)
        self.assertIn("nenhum erro", r.stdout)
        r = galo_cli("verificar", ruim)
        self.assertEqual(r.returncode, 1)
        self.assertIn("[G201]", r.stderr)
        self.assertIn("[G215]", r.stderr)
        r = galo_cli("verificar", ruim, "--json")
        dados = json.loads(r.stdout)
        self.assertEqual([d["codigo"] for d in dados], ["G201", "G215"])
        self.assertEqual(dados[0]["linha"], 1)

    def test_verificar_nao_executa(self):
        p = escrever(self.pasta, "v.galo", 'escrever_arquivo("nao_deveria_existir.txt", "x")\n')
        self.assertEqual(galo_cli("verificar", p, cwd=self.pasta).returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.pasta, "nao_deveria_existir.txt")))

    def test_desmontar(self):
        r = galo_cli("desmontar", os.path.join(EXEMPLOS, "fatorial.galo"))
        self.assertEqual(r.returncode, 0)
        self.assertIn("== função fatorial ==", r.stdout)
        self.assertIn("CALL", r.stdout)

    def test_tokens_e_ast(self):
        p = escrever(self.pasta, "t.galo", "defina x como 1\n")
        self.assertIn("defina", galo_cli("tokens", p).stdout)
        self.assertIn("Defina(name='x'", galo_cli("ast", p).stdout)

    def test_limite_de_pilha(self):
        p = escrever(self.pasta, "r.galo", "função f(n)\n    se n == 0 então retorne 0 fim\n    retorne 1 + f(n - 1)\nfim\nmostre f(3000)\n")
        self.assertEqual(galo_cli("executar", p).stdout, "3000\n")
        r = galo_cli("executar", "--limite-pilha", "100", p)
        self.assertEqual(r.returncode, 2)
        self.assertIn("G311", r.stderr)

    def test_leitura_da_entrada(self):
        p = escrever(self.pasta, "l.galo", 'defina n como leia("Nome? ")\nmostre "Oi, {n}!"\n')
        r = galo_cli("executar", p, entrada="Maria\n")
        self.assertEqual(r.stdout, "Nome? Oi, Maria!\n")


if __name__ == "__main__":
    unittest.main()


class TestExtensaoEAbrir(unittest.TestCase):
    """`galo extensao` instala a extensão nos editores; `galo abrir` é o duplo clique num .galo.

    O PATH é isolado: nenhum editor de verdade desta máquina é tocado.
    """

    def galo(self, *args, path, entrada=None):
        import subprocess
        import sys
        from auxiliar import RAIZ

        env = {"PATH": path, "PYTHONPATH": RAIZ, "GALO_SEM_COR": "1", "PYTHONIOENCODING": "utf-8",
               "HOME": os.environ.get("HOME", "/tmp")}
        return subprocess.run([sys.executable, "-m", "galo", *args], env=env, input=entrada,
                              capture_output=True, text=True, encoding="utf-8", timeout=120)

    def test_extensao_com_editor(self):
        with tempfile.TemporaryDirectory() as pasta:
            registro = os.path.join(pasta, "chamada.txt")
            editor = os.path.join(pasta, "code")
            with open(editor, "w") as f:
                f.write(f'#!/bin/sh\nprintf "%s\\n" "$@" > "{registro}"\n')
            os.chmod(editor, 0o755)
            r = self.galo("extensao", path=pasta)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("✔ Extensão da GALO instalada no VS Code.", r.stdout)
            with open(registro) as f:
                chamada = f.read().splitlines()
            self.assertEqual(chamada[0], "--install-extension")
            self.assertTrue(chamada[1].endswith(".vsix"))
            self.assertEqual(chamada[2], "--force")
            r = self.galo("extensão", "--editor", editor, path=pasta)   # com acento e editor escolhido
            self.assertIn("instalada no code", r.stdout)

    def test_extensao_sem_editor_e_editor_com_falha(self):
        with tempfile.TemporaryDirectory() as pasta:
            r = self.galo("extensao", path=pasta)
            self.assertEqual(r.returncode, 0)
            self.assertIn("Nenhum editor compatível encontrado", r.stdout)
            quebrado = os.path.join(pasta, "cursor")
            with open(quebrado, "w") as f:
                f.write('#!/bin/sh\necho "sem permissão" >&2\nexit 1\n')
            os.chmod(quebrado, 0o755)
            r = self.galo("extensao", path=pasta)
            self.assertEqual(r.returncode, 1)
            self.assertIn("✘ Não foi possível instalar no Cursor: sem permissão", r.stdout)
            self.assertEqual(self.galo("extensao", "--outra", path=pasta).returncode, 64)

    def test_abrir(self):
        with tempfile.TemporaryDirectory() as pasta:
            programa = os.path.join(pasta, "ola.galo")
            with open(programa, "w", encoding="utf-8") as f:
                f.write('defina n como leia("Nome? ")\nmostre "Oi, {n}!"\n')
            r = self.galo("abrir", programa, path=pasta, entrada="Ana\n")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("Oi, Ana!", r.stdout)
            r = self.galo("abrir", os.path.join(pasta, "nao_existe.galo"), path=pasta, entrada="")
            self.assertNotEqual(r.returncode, 0)
