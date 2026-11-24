"""Monta os instaladores da GALO para Windows, macOS e Linux.

Uso, na raiz do repositório:

    python3 instalador/construir.py linux-x64 windows-x64     # no Linux (o .exe usa o makensis)
    python3 instalador/construir.py macos-arm64 macos-x64     # no macOS (usa o pkgbuild)

Os pacotes vão para dist/instaladores/. Cada um leva:
  * um Python 3.13 portátil (python-build-standalone), sem o que a GALO não usa;
  * só o pacote `galo` (nada do site, dos testes nem da documentação);
  * a extensão para VS Code, Cursor e VSCodium (galo.vsix) e os ícones dos arquivos .galo.

Resultado:
  GALO-Instalador-Windows.exe               instalador gráfico, por usuário (sem administrador)
  GALO-Instalador-macOS-AppleSilicon.pkg     Macs com chip M1, M2, M3...
  GALO-Instalador-macOS-Intel.pkg            Macs com processador Intel
  galo-linux-amd64.deb                      Debian, Ubuntu, Mint...
  galo-linux-x64.tar.gz                     qualquer Linux, sem root (sh instalar.sh)
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)

PYTHON = "3.13.18"
PYTHON_CURTO = "3.13"
PBS_DATA = "20261124"   # versão do python-build-standalone (github.com/astral-sh/python-build-standalone)
PBS_URL = f"https://github.com/astral-sh/python-build-standalone/releases/download/{PBS_DATA}"

ALVOS = {
    "linux-x64": {"triplo": "x86_64-unknown-linux-gnu", "sistema": "linux"},
    "windows-x64": {"triplo": "x86_64-pc-windows-msvc", "sistema": "windows"},
    "macos-arm64": {"triplo": "aarch64-apple-darwin", "sistema": "macos", "nome": "AppleSilicon", "arquiteturas": "arm64"},
    "macos-x64": {"triplo": "x86_64-apple-darwin", "sistema": "macos", "nome": "Intel", "arquiteturas": "x86_64,arm64"},
}

# Partes do Python que a GALO não usa (interface Tk, IDLE, testes do próprio Python, pip...).
PODAR_UNIX = [
    "bin/idle3*", "bin/pydoc3*", "bin/pip*", "bin/2to3*", "bin/python*-config", "include", "share", "lib/pkgconfig",
    "lib/libtcl*", "lib/libtk*", "lib/tcl*", "lib/tk*", "lib/itcl*", "lib/thread*", "lib/tdbc*",
    f"lib/python{PYTHON_CURTO}/test", f"lib/python{PYTHON_CURTO}/idlelib", f"lib/python{PYTHON_CURTO}/tkinter",
    f"lib/python{PYTHON_CURTO}/turtledemo", f"lib/python{PYTHON_CURTO}/turtle.py", f"lib/python{PYTHON_CURTO}/ensurepip",
    f"lib/python{PYTHON_CURTO}/config-{PYTHON_CURTO}*", f"lib/python{PYTHON_CURTO}/site-packages/pip*",
    f"lib/python{PYTHON_CURTO}/lib-dynload/_tkinter*", f"lib/python{PYTHON_CURTO}/lib-dynload/_test*",
    f"lib/python{PYTHON_CURTO}/lib-dynload/xxlimited*", f"lib/python{PYTHON_CURTO}/lib-dynload/_xxtestfuzz*",
]
PODAR_WINDOWS = [
    "Lib/test", "Lib/idlelib", "Lib/tkinter", "Lib/turtledemo", "Lib/turtle.py", "Lib/ensurepip",
    "Lib/site-packages/pip*", "tcl", "DLLs/_tkinter*", "DLLs/tcl*", "DLLs/tk*", "DLLs/_test*",
    "DLLs/xxlimited*", "DLLs/_xxtestfuzz*", "include", "libs", "Scripts", "Tools",
]


def versao_galo() -> str:
    with open(os.path.join(RAIZ, "galo", "__init__.py"), encoding="utf-8") as f:
        return re.search(r'__version__ = "([^"]+)"', f.read()).group(1)


def baixar(url: str, destino: str) -> None:
    with urllib.request.urlopen(url, timeout=300) as r, open(destino + ".parcial", "wb") as f:
        shutil.copyfileobj(r, f)
    os.replace(destino + ".parcial", destino)


def sha256(caminho: str) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def runtime_python(triplo: str, cache: str) -> str:
    """Baixa (uma vez) o Python portátil do alvo e confere o SHA-256 publicado."""
    nome = f"cpython-{PYTHON}+{PBS_DATA}-{triplo}-install_only_stripped.tar.gz"
    os.makedirs(cache, exist_ok=True)
    somas = os.path.join(cache, f"SHA256SUMS-{PBS_DATA}")
    if not os.path.exists(somas):
        baixar(f"{PBS_URL}/SHA256SUMS", somas)
    with open(somas, encoding="utf-8") as f:
        esperado = next((linha.split()[0] for linha in f if linha.strip().endswith(nome)), None)
    if esperado is None:
        sys.exit(f"{nome} não está na lista de somas do python-build-standalone {PBS_DATA}")
    arquivo = os.path.join(cache, nome)
    if not os.path.exists(arquivo) or sha256(arquivo) != esperado:
        print(f"  baixando {nome}...")
        baixar(f"{PBS_URL}/{nome.replace('+', '%2B')}", arquivo)
        if sha256(arquivo) != esperado:
            sys.exit(f"SHA-256 de {nome} não confere")
    return arquivo


def podar(pasta: str, padroes: list[str]) -> None:
    for padrao in padroes:
        for caminho in glob.glob(os.path.join(pasta, padrao)):
            if os.path.isdir(caminho) and not os.path.islink(caminho):
                shutil.rmtree(caminho)
            else:
                os.remove(caminho)


def copiar_pacote_galo(destino: str) -> None:
    """Só o pacote galo (código Python e a VM do navegador), sem caches."""
    shutil.copytree(os.path.join(RAIZ, "galo"), destino,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def gerar_vsix(destino: str) -> None:
    r = subprocess.run([sys.executable, os.path.join(RAIZ, "vscode-extension", "empacotar.py")],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("não foi possível empacotar a extensão:\n" + r.stdout + r.stderr)
    gerados = sorted(glob.glob(os.path.join(RAIZ, "vscode-extension", "*.vsix")), key=os.path.getmtime)
    shutil.copy(gerados[-1], destino)


def montar(alvo: str, trabalho: str, cache: str) -> str:
    """Pasta com runtime/ (Python + galo), galo.vsix, ícones e licença."""
    info = ALVOS[alvo]
    base = os.path.join(trabalho, alvo)
    shutil.rmtree(base, ignore_errors=True)
    os.makedirs(base)
    with tarfile.open(runtime_python(info["triplo"], cache)) as tar:
        tar.extractall(base, filter="data")
    os.rename(os.path.join(base, "python"), os.path.join(base, "runtime"))
    runtime = os.path.join(base, "runtime")
    if info["sistema"] == "windows":
        podar(runtime, PODAR_WINDOWS)
        site_packages = os.path.join(runtime, "Lib", "site-packages")
    else:
        podar(runtime, PODAR_UNIX)
        site_packages = os.path.join(runtime, "lib", f"python{PYTHON_CURTO}", "site-packages")
    os.makedirs(site_packages, exist_ok=True)
    copiar_pacote_galo(os.path.join(site_packages, "galo"))
    gerar_vsix(os.path.join(base, "galo.vsix"))
    shutil.copy(os.path.join(RAIZ, "LICENSE"), os.path.join(base, "LICENSE"))
    return base


def tamanho_kb(pasta: str) -> int:
    total = 0
    for raiz, _, arquivos in os.walk(pasta):
        for a in arquivos:
            caminho = os.path.join(raiz, a)
            if not os.path.islink(caminho):
                total += os.path.getsize(caminho)
    return total // 1024 + 1


def escrever(caminho: str, texto: str, executavel: bool = False) -> None:
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8", newline="\n") as f:
        f.write(texto)
    os.chmod(caminho, 0o755 if executavel else 0o644)


def adicionar_ao_tar(tar: tarfile.TarFile, origem: str, nome: str) -> None:
    def normalizar(info: tarfile.TarInfo) -> tarfile.TarInfo:
        info.uid = info.gid = 0
        info.uname = info.gname = "root"
        return info
    tar.add(origem, nome, filter=normalizar)


# ------------------------------------------------------------------ Linux

WRAPPER_UNIX = """#!/bin/sh
# Comando galo: usa o Python embutido da GALO, isolado de outros Pythons da máquina.
exec {python} -I -X utf8 -m galo "$@"
"""


def pacote_tar_linux(base: str, saida: str) -> str:
    pasta = "galo-linux-x64"
    destino = os.path.join(saida, f"{pasta}.tar.gz")
    with tarfile.open(destino, "w:gz") as tar:
        adicionar_ao_tar(tar, os.path.join(base, "runtime"), f"{pasta}/runtime")
        for nome in ("galo.vsix", "LICENSE"):
            adicionar_ao_tar(tar, os.path.join(base, nome), f"{pasta}/{nome}")
        adicionar_ao_tar(tar, os.path.join(AQUI, "linux", "instalar.sh"), f"{pasta}/instalar.sh")
        for nome in ("galo.xml", "galo.desktop"):
            adicionar_ao_tar(tar, os.path.join(AQUI, "linux", nome), f"{pasta}/linux/{nome}")
        adicionar_ao_tar(tar, os.path.join(AQUI, "icones", "galo.svg"), f"{pasta}/icones/galo.svg")
    return destino


def pacote_deb(base: str, saida: str, versao: str) -> str:
    raiz = os.path.join(os.path.dirname(base), "deb")
    shutil.rmtree(raiz, ignore_errors=True)
    shutil.copytree(os.path.join(base, "runtime"), os.path.join(raiz, "opt/galo/runtime"), symlinks=True)
    shutil.copy(os.path.join(base, "galo.vsix"), os.path.join(raiz, "opt/galo/galo.vsix"))
    escrever(os.path.join(raiz, "usr/bin/galo"), WRAPPER_UNIX.format(python="/opt/galo/runtime/bin/python3"), True)
    os.makedirs(os.path.join(raiz, "usr/share/mime/packages"))
    shutil.copy(os.path.join(AQUI, "linux/galo.xml"), os.path.join(raiz, "usr/share/mime/packages/galo.xml"))
    for pasta, nome in (("apps", "galo.svg"), ("mimetypes", "text-x-galo.svg"), ("mimetypes", "application-x-galo-bytecode.svg")):
        destino = os.path.join(raiz, "usr/share/icons/hicolor/scalable", pasta, nome)
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        shutil.copy(os.path.join(AQUI, "icones/galo.svg"), destino)
    with open(os.path.join(AQUI, "linux/galo.desktop"), encoding="utf-8") as f:
        escrever(os.path.join(raiz, "usr/share/applications/galo.desktop"), f.read().replace("@GALO@", "/usr/bin/galo"))
    with open(os.path.join(RAIZ, "LICENSE"), encoding="utf-8") as f:
        licenca = f.read()
    escrever(os.path.join(raiz, "usr/share/doc/galo/copyright"),
             "GALO — linguagem de programação em português\nhttps://github.com/JoaoPauloCMark/GALO\n\n" + licenca)
    escrever(os.path.join(raiz, "DEBIAN/control"), f"""Package: galo
Version: {versao}
Section: devel
Priority: optional
Architecture: amd64
Depends: libc6 (>= 2.17)
Installed-Size: {tamanho_kb(raiz)}
Maintainer: Projeto GALO <https://github.com/JoaoPauloCMark/GALO>
Homepage: https://joaopaulocmark.github.io/GALO/
Description: GALO, linguagem de programação em português
 Linguagem de programação completa com sintaxe em português brasileiro: o comando
 galo (executar, compilar, repl, verificar), o servidor de linguagem para editores
 e o reconhecimento dos arquivos .galo. Traz um Python próprio em /opt/galo.
""")
    escrever(os.path.join(raiz, "DEBIAN/postinst"), f"""#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    /opt/galo/runtime/bin/python3 -I -m compileall -q /opt/galo/runtime/lib/python{PYTHON_CURTO}/site-packages/galo >/dev/null 2>&1 || true
    if command -v update-mime-database >/dev/null 2>&1; then update-mime-database /usr/share/mime || true; fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then gtk-update-icon-cache -q -f /usr/share/icons/hicolor || true; fi
    if command -v update-desktop-database >/dev/null 2>&1; then update-desktop-database -q /usr/share/applications || true; fi
    # extensão para editores: instala para quem chamou o sudo, se for o caso
    if [ -n "${{SUDO_USER:-}}" ] && [ "$SUDO_USER" != "root" ] && command -v sudo >/dev/null 2>&1; then
        sudo -u "$SUDO_USER" -H /usr/bin/galo extensao >/dev/null 2>&1 || true
    fi
fi
exit 0
""", True)
    escrever(os.path.join(raiz, "DEBIAN/postrm"), """#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    rm -rf /opt/galo
    if command -v update-mime-database >/dev/null 2>&1; then update-mime-database /usr/share/mime || true; fi
    if command -v update-desktop-database >/dev/null 2>&1; then update-desktop-database -q /usr/share/applications || true; fi
fi
exit 0
""", True)
    destino = os.path.join(saida, "galo-linux-amd64.deb")
    subprocess.run(["dpkg-deb", "--root-owner-group", "-Zxz", "--build", raiz, destino], check=True,
                   stdout=subprocess.DEVNULL)
    return destino


# ------------------------------------------------------------------ Windows

def pacote_windows(base: str, saida: str, versao: str) -> str:
    makensis = os.environ.get("MAKENSIS") or shutil.which("makensis")
    if not makensis:
        sys.exit("makensis (NSIS) não encontrado: instale o pacote nsis ou indique o caminho em MAKENSIS")
    for nome in ("galo.cmd", "caminho.ps1"):
        shutil.copy(os.path.join(AQUI, "windows", nome), os.path.join(base, nome))
    shutil.copy(os.path.join(AQUI, "icones", "galo.ico"), os.path.join(base, "galo.ico"))
    with open(os.path.join(RAIZ, "LICENSE"), encoding="utf-8") as f:
        licenca = f.read()
    with open(os.path.join(base, "LICENSE.txt"), "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write(licenca)
    os.remove(os.path.join(base, "LICENSE"))
    destino = os.path.join(os.path.abspath(saida), "GALO-Instalador-Windows.exe")
    subprocess.run([makensis, "-V2", "-INPUTCHARSET", "UTF8", f"-DVERSAO={versao}", f"-DORIGEM={os.path.abspath(base)}",
                    f"-DSAIDA={destino}", os.path.join(AQUI, "windows", "galo.nsi")], check=True)
    return destino


# ------------------------------------------------------------------ macOS

def pacote_macos(alvo: str, base: str, saida: str, versao: str) -> str:
    if sys.platform != "darwin":
        sys.exit("os instaladores do macOS só podem ser gerados no macOS (pkgbuild e productbuild)")
    info = ALVOS[alvo]
    trabalho = os.path.dirname(base)
    raiz = os.path.join(trabalho, f"pkg-{alvo}")
    shutil.rmtree(raiz, ignore_errors=True)
    shutil.copytree(os.path.join(base, "runtime"), os.path.join(raiz, "usr/local/galo/runtime"), symlinks=True)
    for nome in ("galo.vsix", "LICENSE"):
        shutil.copy(os.path.join(base, nome), os.path.join(raiz, "usr/local/galo", nome))
    escrever(os.path.join(raiz, "usr/local/bin/galo"), WRAPPER_UNIX.format(python="/usr/local/galo/runtime/bin/python3"), True)
    scripts = os.path.join(trabalho, f"scripts-{alvo}")
    shutil.rmtree(scripts, ignore_errors=True)
    os.makedirs(scripts)
    shutil.copy(os.path.join(AQUI, "macos", "postinstall"), os.path.join(scripts, "postinstall"))
    os.chmod(os.path.join(scripts, "postinstall"), 0o755)
    identificador = "io.github.joaopaulocmark.galo"
    componente = os.path.join(trabalho, f"galo-{alvo}.pkg")
    subprocess.run(["pkgbuild", "--root", raiz, "--identifier", identificador, "--version", versao,
                    "--install-location", "/", "--scripts", scripts, "--ownership", "recommended", componente], check=True)
    recursos = os.path.join(trabalho, f"recursos-{alvo}")
    shutil.rmtree(recursos, ignore_errors=True)
    shutil.copytree(os.path.join(AQUI, "macos", "recursos"), recursos)
    shutil.copy(os.path.join(RAIZ, "LICENSE"), os.path.join(recursos, "LICENSE.txt"))
    distribuicao = os.path.join(trabalho, f"distribution-{alvo}.xml")
    escrever(distribuicao, f"""<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="2">
    <title>GALO {versao}</title>
    <welcome file="bem-vindo.html" mime-type="text/html"/>
    <license file="LICENSE.txt"/>
    <conclusion file="conclusao.html" mime-type="text/html"/>
    <options customize="never" require-scripts="false" hostArchitectures="{info['arquiteturas']}"/>
    <domains enable_localSystem="true"/>
    <choices-outline>
        <line choice="galo"/>
    </choices-outline>
    <choice id="galo" title="GALO" visible="false">
        <pkg-ref id="{identificador}"/>
    </choice>
    <pkg-ref id="{identificador}" version="{versao}" onConclusion="none">{os.path.basename(componente)}</pkg-ref>
</installer-gui-script>
""")
    destino = os.path.join(saida, f"GALO-Instalador-macOS-{info['nome']}.pkg")
    subprocess.run(["productbuild", "--distribution", distribuicao, "--resources", recursos,
                    "--package-path", trabalho, destino], check=True)
    return destino


def main() -> None:
    parser = argparse.ArgumentParser(description="Monta os instaladores da GALO.")
    parser.add_argument("alvos", nargs="+", choices=sorted(ALVOS))
    parser.add_argument("--saida", default=os.path.join(RAIZ, "dist", "instaladores"))
    parser.add_argument("--cache", default=os.path.join(AQUI, ".cache"))
    args = parser.parse_args()
    versao = versao_galo()
    os.makedirs(args.saida, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="galo-instalador-") as trabalho:
        for alvo in args.alvos:
            print(f"{alvo}:")
            base = montar(alvo, trabalho, args.cache)
            sistema = ALVOS[alvo]["sistema"]
            if sistema == "linux":
                gerados = [pacote_tar_linux(base, args.saida), pacote_deb(base, args.saida, versao)]
            elif sistema == "windows":
                gerados = [pacote_windows(base, args.saida, versao)]
            else:
                gerados = [pacote_macos(alvo, base, args.saida, versao)]
            for g in gerados:
                print(f"  {os.path.relpath(g, RAIZ)}  ({os.path.getsize(g) / 2**20:.1f} MiB)")


if __name__ == "__main__":
    main()
