"""A extensão GALO dentro de um editor de verdade (VS Code ou Cursor).

O editor é aberto com perfil e pasta de extensões temporários, carregando a extensão de
vscode-extension/ em modo de desenvolvimento e executando tests/editor/teste_extensao.js
pela API oficial de testes de extensões. Uma janela do editor aparece durante o teste.
O teste é pulado se não houver editor instalado ou tela disponível.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest

from auxiliar import RAIZ

EXTENSAO = os.path.join(RAIZ, "vscode-extension")
TESTES_JS = os.path.join(RAIZ, "tests", "editor", "teste_extensao.js")


def encontrar_editor():
    """Devolve (executável do aplicativo Electron, comando de linha) do VS Code ou do Cursor."""
    for cli in ("code", "cursor", "codium"):
        caminho = shutil.which(cli)
        if not caminho:
            continue
        real = os.path.realpath(caminho)
        pasta = os.path.dirname(os.path.dirname(real))  # .../bin/code -> pasta do aplicativo
        for app in ("code", "cursor", "codium"):
            binario = os.path.join(pasta, app)
            if os.path.isfile(binario) and os.access(binario, os.X_OK):
                return binario, caminho
    return None, None


APP, CLI = encontrar_editor()
TELA = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))

ARQUIVOS = {
    "certo.galo": "defina quantidade como 3\nfunção dobro(n) retorne n * 2 fim\nmostre tamanho([quantidade])\n\n",
    "com_erro.galo": "defina x como 1\nmostre pontuacao\n",
    "nao_aberto.galo": 'defina texto como "aviso"\nse 1 então\nfim\n',
    "modulo.galo": "função _privada()\nfim\nfunção publica()\nfim\n",
    "usa_modulo.galo": 'importe _privada de "modulo.galo"\n',
    "indentar.galo": ("função f(x)\nse x então\nmostre 1\nsenão\nmostre 2\nfim\nfim\nregistro R\na\nfunção m()\n"
                      "retorne eu.a\nfim\nfim\nenquanto falso faça\nrepita 2 vezes\nmostre 3\nfim\nfim\ntente\nmostre 4\n"
                      "capture erro\nmostre erro\nfim\n"),
    "realce.galo": ("# comentário\nregistro Ponto(x, y)\nfunção dobro(n) retorne n * 2 fim\n"
                    "se verdadeiro então mostre \"oi {nome}\", '{literal}', tamanho([42]) fim\n"
                    "registro Q\n    a\n    função m() retorne eu.a fim\nfim\n"),
}


@unittest.skipUnless(APP and TELA, "VS Code/Cursor ou uma tela gráfica não estão disponíveis")
class TestExtensaoNoEditor(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = self._tmp.name
        self.usuario = os.path.join(self.base, "usuario")
        self.extensoes = os.path.join(self.base, "extensoes")
        self.projeto = os.path.join(self.base, "projeto")
        for p in (self.usuario, self.extensoes, self.projeto, os.path.join(self.usuario, "User")):
            os.makedirs(p, exist_ok=True)
        for nome, conteudo in ARQUIVOS.items():
            with open(os.path.join(self.projeto, nome), "w", encoding="utf-8") as f:
                f.write(conteudo)
        os.makedirs(os.path.join(self.projeto, ".vscode"))
        with open(os.path.join(self.projeto, ".vscode", "tasks.json"), "w") as f:
            json.dump({"version": "2.0.0", "tasks": [{"type": "galo", "comando": "verificar", "arquivo": "nao_aberto.galo",
                                                      "label": "GALO: verificar arquivo fechado"}]}, f)
        self.lancador = os.path.join(self.base, "galo")
        with open(self.lancador, "w") as f:
            f.write(f'#!/bin/sh\nPYTHONPATH="{RAIZ}" exec python3 -m galo "$@"\n')
        os.chmod(self.lancador, 0o755)
        configuracao = {
            "galo.caminhoExecutavel": self.lancador,
            "security.workspace.trust.enabled": False,
            "workbench.startupEditor": "none",
            "editor.detectIndentation": False, "editor.tabSize": 4, "editor.insertSpaces": True,
            "update.mode": "none", "extensions.autoUpdate": False, "telemetry.telemetryLevel": "off",
            "window.restoreWindows": "none", "files.hotExit": "off",
        }
        with open(os.path.join(self.usuario, "User", "settings.json"), "w") as f:
            json.dump(configuracao, f)

    def tearDown(self):
        self._tmp.cleanup()

    def test_extensao_completa(self):
        resultado = os.path.join(self.base, "resultado.json")
        env = dict(os.environ, GALO_RESULTADO_EXTENSAO=resultado)
        env.pop("ELECTRON_RUN_AS_NODE", None)
        proc = subprocess.run(
            [APP, "--user-data-dir", self.usuario, "--extensions-dir", self.extensoes, "--disable-gpu",
             "--skip-welcome", "--skip-release-notes", "--disable-workspace-trust", "--new-window",
             f"--extensionDevelopmentPath={EXTENSAO}", f"--extensionTestsPath={TESTES_JS}", self.projeto],
            env=env, capture_output=True, text=True, timeout=300)
        self.assertTrue(os.path.exists(resultado), "o editor não executou os testes:\n" + proc.stdout[-3000:] + proc.stderr[-3000:])
        with open(resultado, encoding="utf-8") as f:
            resultados = json.load(f)
        editor = next(r["info"] for r in resultados if r["nome"] == "__editor")
        print(f"\n    editor: {editor}")
        for r in resultados:
            if r["nome"] == "__editor":
                continue
            with self.subTest(teste=r["nome"]):
                self.assertTrue(r["ok"], r.get("erro"))

    def test_pacote_vsix_instala_no_editor(self):
        vsix = [n for n in os.listdir(EXTENSAO) if n.endswith(".vsix")]
        if not vsix:
            subprocess.run(["python3", os.path.join(EXTENSAO, "empacotar.py")], check=True, capture_output=True)
            vsix = [n for n in os.listdir(EXTENSAO) if n.endswith(".vsix")]
        caminho = os.path.join(EXTENSAO, sorted(vsix)[-1])
        args = [CLI, "--user-data-dir", self.usuario, "--extensions-dir", self.extensoes]
        r = subprocess.run(args + ["--install-extension", caminho], capture_output=True, text=True, timeout=180)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        lista = subprocess.run(args + ["--list-extensions", "--show-versions"], capture_output=True, text=True, timeout=60)
        with open(os.path.join(EXTENSAO, "package.json"), encoding="utf-8") as f:
            versao = json.load(f)["version"]
        self.assertIn(f"galo.galo-linguagem@{versao}", lista.stdout)


if __name__ == "__main__":
    unittest.main()
