"""Biblioteca padrão da GALO.

Importar este pacote registra todas as funções internas em BUILTINS e as
constantes em CONSTANTS.
"""

from . import (  # noqa: F401
    arquivos, banco, colecoes, conversao, dados_json, entrada_saida, matematica, modelos, navegador,
    programas, seguranca, sistema, tempo, texto, web,
)
from .registry import BUILTINS, CONSTANTS

__all__ = ["BUILTINS", "CONSTANTS"]
