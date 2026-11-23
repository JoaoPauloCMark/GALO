"""API de alto nível: executar código GALO e manter uma sessão interativa (REPL)."""

from __future__ import annotations

import os

from .compiler import compile_source
from .runtime.vm import VM


class Session:
    """Estado persistente entre execuções: variáveis, constantes e funções globais.

    Cada entrada é compilada separadamente (com o conhecimento dos nomes
    definidos antes) e executada na mesma máquina virtual.
    """

    def __init__(self, out=None, input_fn=None, args=(), filename: str = "<repl>") -> None:
        self.vm = VM(out=out, input_fn=input_fn, args=args)
        self.symbols: dict = {}
        self.filename = filename
        self.base_dir = os.getcwd()

    def execute(self, source: str):
        result = compile_source(source, self.filename, repl=True, session_symbols=dict(self.symbols),
                                base_dir=self.base_dir)
        try:
            return self.vm.run(result.module)
        finally:
            # Só são mantidos os nomes que realmente receberam valor (uma
            # definição pode ter falhado no meio da execução).
            for key, sym in result.new_globals.items():
                if key in self.vm.globals:
                    self.symbols[key] = sym

    def names(self) -> list[tuple[str, str]]:
        from .runtime.values import repr_value

        out = []
        for key, sym in sorted(self.symbols.items()):
            if key in self.vm.globals:
                out.append((sym.name, sym.kind, repr_value(self.vm.globals[key])))
        return out


def run_source(source: str, filename: str = "<entrada>", out=None, input_fn=None, args=()):
    """Compila e executa um programa completo. Devolve a VM usada."""
    result = compile_source(source, filename)
    vm = VM(out=out, input_fn=input_fn, args=args)
    vm.run(result.module)
    return vm
