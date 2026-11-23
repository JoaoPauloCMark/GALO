"""Leitura e escrita de arquivos de texto (UTF-8).

Caminhos relativos partem da pasta do programa principal (não da pasta atual do terminal).
"""

from __future__ import annotations

import os

from ..runtime.values import display
from ._util import erro, exige_texto
from .registry import nativa


def _io_error(acao: str, caminho: str, exc: OSError):
    if isinstance(exc, FileNotFoundError):
        return erro("G313", f'O arquivo "{caminho}" não foi encontrado.',
                    "Verifique o nome e a pasta do arquivo. Caminhos relativos partem da pasta do programa principal.")
    if isinstance(exc, IsADirectoryError):
        return erro("G313", f'"{caminho}" é uma pasta, não um arquivo.')
    if isinstance(exc, PermissionError):
        return erro("G313", f'Sem permissão para {acao} "{caminho}".')
    return erro("G313", f'Não foi possível {acao} "{caminho}": {exc.strerror or exc}.')


@nativa("ler_arquivo", retorna="texto")
def ler_arquivo(vm, caminho):
    """Conteúdo completo de um arquivo de texto."""
    exige_texto("ler_arquivo", 1, caminho)
    try:
        with open(vm.resolve_path(caminho), encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        raise erro("G313", f'O arquivo "{caminho}" não é um arquivo de texto UTF-8.')
    except OSError as exc:
        raise _io_error("ler", caminho, exc)


@nativa("ler_linhas", retorna="lista")
def ler_linhas(vm, caminho):
    """Lista com as linhas de um arquivo de texto (sem as quebras de linha)."""
    return ler_arquivo(vm, caminho).splitlines()


@nativa("escrever_arquivo", retorna="nulo")
def escrever_arquivo(vm, caminho, conteudo):
    """Grava o conteúdo no arquivo, substituindo o que havia antes."""
    exige_texto("escrever_arquivo", 1, caminho)
    try:
        with open(vm.resolve_path(caminho), "w", encoding="utf-8") as f:
            f.write(display(conteudo))
    except OSError as exc:
        raise _io_error("escrever em", caminho, exc)
    return None


@nativa("anexar_arquivo", retorna="nulo")
def anexar_arquivo(vm, caminho, conteudo):
    """Acrescenta o conteúdo ao final do arquivo (criando-o se não existir)."""
    exige_texto("anexar_arquivo", 1, caminho)
    try:
        with open(vm.resolve_path(caminho), "a", encoding="utf-8") as f:
            f.write(display(conteudo))
    except OSError as exc:
        raise _io_error("escrever em", caminho, exc)
    return None


@nativa("arquivo_existe", retorna="booleano")
def arquivo_existe(vm, caminho):
    """Verdadeiro se existir um arquivo nesse caminho."""
    return os.path.isfile(vm.resolve_path(exige_texto("arquivo_existe", 1, caminho)))


@nativa("apagar_arquivo", retorna="nulo")
def apagar_arquivo(vm, caminho):
    """Apaga o arquivo."""
    exige_texto("apagar_arquivo", 1, caminho)
    try:
        os.remove(vm.resolve_path(caminho))
    except OSError as exc:
        raise _io_error("apagar", caminho, exc)
    return None


@nativa("listar_arquivos", retorna="lista", assinatura="listar_arquivos([pasta])")
def listar_arquivos(vm, pasta="."):
    """Lista em ordem alfabética com os nomes dos itens de uma pasta."""
    exige_texto("listar_arquivos", 1, pasta)
    try:
        return sorted(os.listdir(vm.resolve_path(pasta)))
    except OSError as exc:
        raise _io_error("listar", pasta, exc)
