"""Arquivos entregues ao navegador (galo.js: a máquina virtual da GALO em JavaScript)."""

from importlib import resources


def runtime_js() -> bytes:
    return resources.files(__name__).joinpath("galo.js").read_bytes()
