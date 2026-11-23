"""Baixa o Microsoft Edge (Linux, amd64) para uma pasta, sem instalar nada no sistema.

Uso:  python3 tests/navegador_real/baixar_edge.py <pasta>
Depois: GALO_EDGE=<pasta>/opt/microsoft/msedge/msedge python3 -m unittest test_navegador_real

Passos: baixa o índice assinado do repositório oficial (packages.microsoft.com), confere a
assinatura com a chave pública da Microsoft (gpg, num chaveiro temporário), confere o
SHA-256 da lista de pacotes e do .deb, e extrai o pacote com dpkg-deb.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import tempfile
import urllib.request

REPOSITORIO = "https://packages.microsoft.com/repos/edge"
CHAVE = "https://packages.microsoft.com/keys/microsoft.asc"
IMPRESSAO_DIGITAL = "BC528686B50D79E339D3721CEB3E94ADBE1229CF"  # Microsoft (Release signing)


def baixar(url: str, destino: str) -> None:
    with urllib.request.urlopen(url, timeout=120) as r, open(destino, "wb") as f:
        while bloco := r.read(1 << 20):
            f.write(bloco)


def sha256(caminho: str) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        while bloco := f.read(1 << 20):
            h.update(bloco)
    return h.hexdigest()


def versao(texto: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", texto.split("-")[0]))


def main(pasta: str) -> str:
    os.makedirs(pasta, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        chaveiro = os.path.join(tmp, "gnupg")
        os.mkdir(chaveiro, 0o700)
        baixar(CHAVE, os.path.join(tmp, "microsoft.asc"))
        baixar(f"{REPOSITORIO}/dists/stable/InRelease", os.path.join(tmp, "InRelease"))
        subprocess.run(["gpg", "--homedir", chaveiro, "--quiet", "--import", os.path.join(tmp, "microsoft.asc")],
                       check=True, capture_output=True)
        verificacao = subprocess.run(["gpg", "--homedir", chaveiro, "--status-fd", "1", "--verify",
                                      os.path.join(tmp, "InRelease")], capture_output=True, text=True)
        if f"VALIDSIG {IMPRESSAO_DIGITAL}" not in verificacao.stdout:
            sys.exit("assinatura do índice do repositório inválida")
        with open(os.path.join(tmp, "InRelease"), encoding="utf-8") as f:
            indice = f.read()
        hash_lista = re.search(r"^ ([0-9a-f]{64}) +\d+ main/binary-amd64/Packages$", indice, re.M).group(1)

        lista = os.path.join(tmp, "Packages")
        baixar(f"{REPOSITORIO}/dists/stable/main/binary-amd64/Packages", lista)
        if sha256(lista) != hash_lista:
            sys.exit("SHA-256 da lista de pacotes não confere")
        with open(lista, encoding="utf-8") as f:
            pacotes = [dict(re.findall(r"^(\w[\w-]*): (.*)$", bloco, re.M)) for bloco in f.read().split("\n\n")]
        estavel = max((p for p in pacotes if p.get("Package") == "microsoft-edge-stable"), key=lambda p: versao(p["Version"]))

        deb = os.path.join(tmp, "edge.deb")
        print(f"baixando Microsoft Edge {estavel['Version']} ({int(estavel['Size']) // 2**20} MiB)...")
        baixar(f"{REPOSITORIO}/{estavel['Filename']}", deb)
        if sha256(deb) != estavel["SHA256"]:
            sys.exit("SHA-256 do pacote não confere")
        subprocess.run(["dpkg-deb", "-x", deb, pasta], check=True)
    executavel = os.path.join(pasta, "opt", "microsoft", "msedge", "msedge")
    print(f"pronto: GALO_EDGE={executavel}")
    return executavel


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
