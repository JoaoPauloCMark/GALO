"""Instala a extensão da GALO nos editores de código desta máquina (comando `galo extensao`).

A extensão (galo.vsix) traz realce de sintaxe, autocompletar, erros enquanto se digita e
comandos para executar programas. Os instaladores da GALO a colocam ao lado do Python
embutido; numa cópia do código-fonte, ela é gerada por vscode-extension/empacotar.py.
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys

# (nome exibido, comando de linha do editor)
EDITORES = [
    ("VS Code", "code"),
    ("VS Code Insiders", "code-insiders"),
    ("Cursor", "cursor"),
    ("VSCodium", "codium"),
    ("Windsurf", "windsurf"),
]

# No macOS os editores nem sempre colocam o comando no PATH: ele fica dentro do aplicativo.
APLICATIVOS_MAC = {
    "code": "Visual Studio Code.app/Contents/Resources/app/bin/code",
    "code-insiders": "Visual Studio Code - Insiders.app/Contents/Resources/app/bin/code",
    "cursor": "Cursor.app/Contents/Resources/app/bin/cursor",
    "codium": "VSCodium.app/Contents/Resources/app/bin/codium",
    "windsurf": "Windsurf.app/Contents/Resources/app/bin/windsurf",
}

PAGINA_DE_DOWNLOAD = "https://github.com/JoaoPauloCMark/GALO/releases/latest"


def encontrar_vsix() -> str | None:
    """Caminho do galo.vsix: ao lado do Python embutido (instaladores) ou gerado do código-fonte."""
    pacote = os.path.dirname(os.path.abspath(__file__))
    for candidato in (
        os.path.join(os.path.dirname(sys.prefix), "galo.vsix"),   # <instalação>/runtime + <instalação>/galo.vsix
        os.path.join(sys.prefix, "galo.vsix"),
        os.path.join(pacote, "galo.vsix"),
    ):
        if os.path.isfile(candidato):
            return candidato
    empacotar = os.path.join(os.path.dirname(pacote), "vscode-extension", "empacotar.py")
    if os.path.isfile(empacotar):
        r = subprocess.run([sys.executable, empacotar], capture_output=True, text=True)
        gerados = sorted(glob.glob(os.path.join(os.path.dirname(empacotar), "*.vsix")), key=os.path.getmtime)
        if r.returncode == 0 and gerados:
            return gerados[-1]
    return None


def encontrar_editores() -> list[tuple[str, str]]:
    """(nome, caminho do comando) de cada editor compatível instalado."""
    achados = []
    pastas_mac = ["/Applications", os.path.expanduser("~/Applications")] if sys.platform == "darwin" else []
    for nome, comando in EDITORES:
        caminho = shutil.which(comando)
        if caminho is None:
            for pasta in pastas_mac:
                dentro = os.path.join(pasta, APLICATIVOS_MAC[comando])
                if os.access(dentro, os.X_OK):
                    caminho = dentro
                    break
        if caminho is not None:
            achados.append((nome, caminho))
    return achados


def instalar_extensao(args: list[str]) -> int:
    """galo extensao [--editor CAMINHO]: instala a extensão em todos os editores encontrados."""
    editores = None
    if args:
        if len(args) == 2 and args[0] == "--editor":
            editores = [(os.path.basename(args[1]), args[1])]
        else:
            sys.stderr.write("Uso: galo extensao [--editor caminho/do/comando/do/editor]\n")
            return 64
    vsix = encontrar_vsix()
    if vsix is None:
        print("Não encontrei a extensão da GALO (galo.vsix) nesta instalação.\n"
              f"Ela vem junto com os instaladores: {PAGINA_DE_DOWNLOAD}")
        return 3
    if editores is None:
        editores = encontrar_editores()
    if not editores:
        print("Nenhum editor compatível encontrado (VS Code, Cursor, VSCodium, Windsurf).\n"
              "Depois de instalar um deles, rode de novo:  galo extensao")
        return 0
    falhas = 0
    for nome, comando in editores:
        try:
            r = subprocess.run([comando, "--install-extension", vsix, "--force"],
                               capture_output=True, text=True, timeout=300)
            ok = r.returncode == 0
            detalhe = (r.stderr or r.stdout).strip().splitlines()[-1:] if not ok else []
        except (OSError, subprocess.TimeoutExpired) as exc:
            ok, detalhe = False, [str(exc)]
        if ok:
            print(f"✔ Extensão da GALO instalada no {nome}.")
        else:
            falhas += 1
            print(f"✘ Não foi possível instalar no {nome}" + (f": {detalhe[0]}" if detalhe else "."))
    if falhas < len(editores):
        print("Abra (ou recarregue) o editor: os arquivos .galo já aparecem com cores e verificação de erros.")
    return 1 if falhas else 0
