"""Instalação da GALO como um usuário faria, em pastas temporárias (nada é instalado no sistema).

* pip: ambiente virtual novo, `pip install <pasta do código>`, o comando `galo` do ambiente,
  galo.js dentro do pacote (servido pelo servidor web), pacote wheel, instalação editável e
  desinstalação. Se o Python não tiver pip, o pip é baixado do PyPI (o SHA-256 publicado é
  conferido); o setuptools vem do PyPI pelo próprio pip, como numa instalação normal.
  Sem acesso ao PyPI (ou com GALO_SEM_REDE=1), esses testes são pulados.
* instalar.sh: instalação em um PREFIXO temporário, o arquivo único galo.pyz e a desinstalação.

Tudo roda sobre uma cópia do código: a construção do pacote cria build/ e *.egg-info, e o
--pyz cria dist/, que não devem aparecer no repositório.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.request
import zipfile

from auxiliar import ESPERADO, EXEMPLOS, RAIZ
from test_web import ServidorGalo

ARQUIVOS_DO_PACOTE = ("galo", "pyproject.toml", "README.md", "LICENSE", "instalar.sh")


def copiar_codigo(destino: str) -> str:
    os.makedirs(destino)
    for nome in ARQUIVOS_DO_PACOTE:
        origem = os.path.join(RAIZ, nome)
        if os.path.isdir(origem):
            shutil.copytree(origem, os.path.join(destino, nome), ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(origem, destino)
    return destino


def baixar_roda(pacote: str, pasta: str) -> str:
    """Baixa o wheel mais recente do PyPI e confere o SHA-256 publicado."""
    with urllib.request.urlopen(f"https://pypi.org/pypi/{pacote}/json", timeout=20) as r:
        info = json.load(r)
    roda = next(u for u in info["urls"] if u["packagetype"] == "bdist_wheel")
    with urllib.request.urlopen(roda["url"], timeout=120) as r:
        dados = r.read()
    if hashlib.sha256(dados).hexdigest() != roda["digests"]["sha256"]:
        raise RuntimeError(f"SHA-256 do {roda['filename']} não confere")
    caminho = os.path.join(pasta, roda["filename"])
    with open(caminho, "wb") as f:
        f.write(dados)
    return caminho


def rodar(*cmd, cwd=None, env=None, entrada=None):
    ambiente = dict(os.environ, GALO_SEM_COR="1", **(env or {}))
    ambiente.pop("PYTHONPATH", None)  # nada do repositório pode vazar para o ambiente instalado
    return subprocess.run([str(c) for c in cmd], cwd=cwd, env=ambiente, input=entrada, capture_output=True,
                          text=True, timeout=300)


def ler(caminho):
    with open(caminho, encoding="utf-8") as f:
        return f.read()


class _ComPip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("GALO_SEM_REDE"):
            raise unittest.SkipTest("GALO_SEM_REDE definido")
        cls._tmp = tempfile.TemporaryDirectory(prefix="galo-pip-")
        cls.pasta = cls._tmp.name
        cls.rodas = os.path.join(cls.pasta, "rodas")
        os.makedirs(cls.rodas)
        try:
            cls.roda_pip = baixar_roda("pip", cls.rodas)
            baixar_roda("setuptools", cls.rodas)  # para construir sem rede nos testes seguintes
        except OSError as exc:
            cls._tmp.cleanup()
            raise unittest.SkipTest(f"sem acesso ao PyPI: {exc}")
        cls.fonte = copiar_codigo(os.path.join(cls.pasta, "fonte"))
        cls.neutra = os.path.join(cls.pasta, "neutra")  # pasta de trabalho sem nada da GALO
        os.makedirs(cls.neutra)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def criar_ambiente(self, nome):
        """Ambiente virtual novo, com pip (o do Python, se houver; senão o wheel baixado)."""
        venv = os.path.join(self.pasta, nome)
        r = rodar(sys.executable, "-m", "venv", "--without-pip", venv)
        self.assertEqual(r.returncode, 0, r.stderr)
        python = os.path.join(venv, "bin", "python")
        r = rodar(python, os.path.join(self.roda_pip, "pip"), "install", "--no-cache-dir", "--quiet", self.roda_pip)
        self.assertEqual(r.returncode, 0, r.stderr)
        return venv

    def conferir_galo_instalada(self, venv, local_esperado):
        galo = os.path.join(venv, "bin", "galo")
        python = os.path.join(venv, "bin", "python")
        r = rodar(galo, "--versao", cwd=self.neutra)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("GALO 0.2.0", r.stdout)

        r = rodar(python, "-c", "import galo, galo.web; print(galo.__file__); print(len(galo.web.runtime_js()))", cwd=self.neutra)
        self.assertEqual(r.returncode, 0, r.stderr)
        arquivo, tamanho = r.stdout.split()
        self.assertTrue(arquivo.startswith(local_esperado), arquivo)
        self.assertEqual(int(tamanho), os.path.getsize(os.path.join(RAIZ, "galo", "web", "galo.js")))

        # executar, compilar, rodar o bytecode e verificar
        programa = os.path.join(EXEMPLOS, "fatorial.galo")
        r = rodar(galo, "executar", programa, cwd=self.neutra)
        self.assertEqual((r.returncode, r.stdout), (0, ler(os.path.join(ESPERADO, "fatorial.saida"))), r.stderr)
        galoc = os.path.join(self.neutra, f"fatorial-{os.path.basename(venv)}.galoc")
        self.assertEqual(rodar(galo, "compilar", programa, "-o", galoc, cwd=self.neutra).returncode, 0)
        r = rodar(galo, "rodar", galoc, cwd=self.neutra)
        self.assertEqual(r.stdout, ler(os.path.join(ESPERADO, "fatorial.saida")))
        errado = os.path.join(self.neutra, "errado.galo")
        with open(errado, "w", encoding="utf-8") as f:
            f.write("mostre nao_existe\n")
        r = rodar(galo, "verificar", errado, cwd=self.neutra)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("G201", r.stdout + r.stderr)
        r = rodar(galo, "repl", cwd=self.neutra, entrada="mostre 6 * 7\n:sair\n")
        self.assertIn("42", r.stdout)

        # o servidor web do pacote instalado entrega a VM do navegador (galo.js)
        servidor = ServidorGalo(os.path.join(EXEMPLOS, "tarefas", "servidor.galo"),
                                {"BANCO": os.path.join(self.neutra, f"t-{os.path.basename(venv)}.db")}, comando=[galo])
        try:
            status, _, corpo = servidor.pedir("GET", "/_galo/galo.js")
            self.assertEqual(status, 200)
            with open(os.path.join(RAIZ, "galo", "web", "galo.js"), "rb") as f:
                self.assertEqual(corpo, f.read())
            status, _, pagina = servidor.pedir("GET", "/")
            self.assertEqual(status, 200)
            self.assertIn(b"/_galo/galo.js", pagina)
        finally:
            servidor.parar()


class TestInstalacaoComPip(_ComPip):
    def test_pip_install_da_pasta_do_codigo(self):
        venv = self.criar_ambiente("ambiente")
        python = os.path.join(venv, "bin", "python")
        r = rodar(python, "-m", "pip", "install", "--no-cache-dir", self.fonte, cwd=self.neutra)  # usa o PyPI de verdade
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Successfully installed galo-linguagem-0.2.0", r.stdout)
        self.conferir_galo_instalada(venv, os.path.join(venv, "lib"))

        r = rodar(python, "-m", "pip", "show", "galo-linguagem")
        self.assertIn("Version: 0.2.0", r.stdout)
        r = rodar(python, "-m", "pip", "uninstall", "-y", "galo-linguagem")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(os.path.join(venv, "bin", "galo")))
        self.assertNotEqual(rodar(python, "-c", "import galo", cwd=self.neutra).returncode, 0)

    def test_pacote_wheel(self):
        venv = self.criar_ambiente("construcao")
        python = os.path.join(venv, "bin", "python")
        dist = os.path.join(self.pasta, "dist")
        r = rodar(python, "-m", "pip", "wheel", "--no-deps", "--no-index", "--find-links", self.rodas,
                  "-w", dist, self.fonte, cwd=self.neutra)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rodas = [a for a in os.listdir(dist) if a.endswith(".whl")]
        self.assertEqual(len(rodas), 1)
        self.assertTrue(rodas[0].startswith("galo_linguagem-0.2.0-py3-none-any"), rodas[0])
        with zipfile.ZipFile(os.path.join(dist, rodas[0])) as z:
            nomes = z.namelist()
            info = next(n for n in nomes if n.endswith(".dist-info/entry_points.txt"))
            self.assertIn("galo = galo.cli.main:main", z.read(info).decode())
            metadados = z.read(next(n for n in nomes if n.endswith(".dist-info/METADATA"))).decode()
        for esperado in ("galo/web/galo.js", "galo/lsp/server.py", "galo/stdlib/web.py", "galo/runtime/vm.py",
                         "galo/runtime/matematica_exata.py", "galo/compiler/parser.py", "galo/cli/main.py"):
            self.assertIn(esperado, nomes)
        self.assertFalse([n for n in nomes if n.startswith(("tests/", "examples/", "docs/")) or "__pycache__" in n])
        self.assertIn("Name: galo-linguagem", metadados)
        self.assertIn("Requires-Python: >=3.10", metadados)

        # instalar o wheel num ambiente novo, sem rede
        destino = self.criar_ambiente("do_wheel")
        r = rodar(os.path.join(destino, "bin", "python"), "-m", "pip", "install", "--no-index",
                  os.path.join(dist, rodas[0]), cwd=self.neutra)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.conferir_galo_instalada(destino, os.path.join(destino, "lib"))

    def test_instalacao_editavel(self):
        fonte = copiar_codigo(os.path.join(self.pasta, "fonte_editavel"))
        venv = self.criar_ambiente("editavel")
        r = rodar(os.path.join(venv, "bin", "python"), "-m", "pip", "install", "--no-index", "--find-links", self.rodas,
                  "-e", fonte, cwd=self.neutra)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.conferir_galo_instalada(venv, os.path.join(fonte, "galo"))
        # mudança no código aparece sem reinstalar
        with open(os.path.join(fonte, "galo", "__init__.py"), encoding="utf-8") as f:
            texto = f.read()
        with open(os.path.join(fonte, "galo", "__init__.py"), "w", encoding="utf-8") as f:
            f.write(texto + "\nMARCA_EDITAVEL = 1\n")
        r = rodar(os.path.join(venv, "bin", "python"), "-c", "import galo; print(galo.MARCA_EDITAVEL)", cwd=self.neutra)
        self.assertEqual(r.stdout.strip(), "1", r.stderr)


@unittest.skipUnless(shutil.which("sh"), "sem shell POSIX")
class TestInstalador(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="galo-instalador-")
        self.pasta = self._tmp.name
        self.fonte = copiar_codigo(os.path.join(self.pasta, "fonte"))
        self.prefixo = os.path.join(self.pasta, "prefixo")

    def tearDown(self):
        self._tmp.cleanup()

    def instalador(self, *args):
        return rodar("sh", os.path.join(self.fonte, "instalar.sh"), *args, cwd=self.pasta, env={"PREFIXO": self.prefixo})

    def test_instalar_usar_e_desinstalar(self):
        r = self.instalador()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        galo = os.path.join(self.prefixo, "bin", "galo")
        self.assertTrue(os.access(galo, os.X_OK))
        self.assertTrue(os.path.exists(os.path.join(self.prefixo, "lib", "galo", "galo", "web", "galo.js")))
        r = rodar(galo, "--versao", cwd=self.pasta)
        self.assertIn("GALO 0.2.0", r.stdout)
        r = rodar(galo, "executar", os.path.join(EXEMPLOS, "fatorial.galo"), cwd=self.pasta)
        self.assertEqual(r.stdout, ler(os.path.join(ESPERADO, "fatorial.saida")))
        # a instalação não depende do código de origem
        shutil.rmtree(self.fonte + "_movida", ignore_errors=True)
        os.rename(self.fonte, self.fonte + "_movida")
        r = rodar(galo, "executar", os.path.join(EXEMPLOS, "fatorial.galo"), cwd=self.pasta)
        self.assertEqual(r.stdout, ler(os.path.join(ESPERADO, "fatorial.saida")), r.stderr)
        os.rename(self.fonte + "_movida", self.fonte)

        r = self.instalador("--desinstalar")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(galo))
        self.assertFalse(os.path.exists(os.path.join(self.prefixo, "lib", "galo")))

    def test_arquivo_unico_pyz(self):
        r = self.instalador("--pyz")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        pyz = os.path.join(self.fonte, "dist", "galo.pyz")
        r = rodar(sys.executable, pyz, "--versao", cwd=self.pasta)
        self.assertIn("GALO 0.2.0", r.stdout)
        r = rodar(sys.executable, pyz, "executar", os.path.join(EXEMPLOS, "fatorial.galo"), cwd=self.pasta)
        self.assertEqual(r.stdout, ler(os.path.join(ESPERADO, "fatorial.saida")), r.stderr)
        with zipfile.ZipFile(pyz) as z:
            self.assertIn("galo/web/galo.js", z.namelist())


if __name__ == "__main__":
    unittest.main()
