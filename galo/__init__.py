"""GALO — uma linguagem de programação de propósito geral em português.

Pacotes:
    galo.compiler  -> lexer, parser, AST, análise semântica, geração de bytecode
    galo.runtime   -> valores, máquina virtual e funções internas
    galo.stdlib    -> biblioteca padrão (texto, matemática, coleções, arquivos...)
    galo.cli       -> comando `galo` e REPL
    galo.lsp       -> servidor Language Server Protocol para editores
"""

__version__ = "0.2.0"

# Versão do formato binário .galoc. Incrementada sempre que o formato muda
# de forma incompatível.
BYTECODE_VERSION = 2
