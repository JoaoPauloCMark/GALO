"""Funções auxiliares compartilhadas pelos testes."""

from __future__ import annotations

import io
import os
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from galo.compiler import compile_source  # noqa: E402
from galo.errors import CompilationError, GaloRuntimeError  # noqa: E402
from galo.runtime.vm import VM  # noqa: E402

EXEMPLOS = os.path.join(RAIZ, "examples")
ESPERADO = os.path.join(RAIZ, "tests", "esperado")


def executar(fonte: str, entradas=None, args=(), max_frames: int | None = None) -> str:
    """Compila e executa `fonte`, devolvendo tudo o que foi mostrado."""
    out = io.StringIO()
    linhas = list(entradas or [])

    def ler(prompt=""):
        out.write(prompt)
        if not linhas:
            raise EOFError
        return linhas.pop(0)

    resultado = compile_source(fonte, "teste.galo")
    kwargs = {} if max_frames is None else {"max_frames": max_frames}
    VM(out=out, input_fn=ler, args=args, **kwargs).run(resultado.module)
    return out.getvalue()


def erros_de_compilacao(fonte: str) -> list:
    try:
        compile_source(fonte, "teste.galo")
    except CompilationError as exc:
        return exc.errors
    return []


def codigos(fonte: str) -> list[str]:
    return [e.code for e in erros_de_compilacao(fonte)]


def avisos(fonte: str) -> list[str]:
    try:
        return [w.code for w in compile_source(fonte, "teste.galo").warnings]
    except CompilationError as exc:
        return [w.code for w in exc.warnings]


def erro_de_execucao(fonte: str, **kw) -> GaloRuntimeError:
    try:
        executar(fonte, **kw)
    except GaloRuntimeError as exc:
        return exc
    raise AssertionError("era esperado um erro de execução")


def galo_cli(*args, entrada: str | None = None, cwd: str | None = None, timeout: int = 60):
    """Executa `python -m galo ...` em um processo separado."""
    env = dict(os.environ)
    env["PYTHONPATH"] = RAIZ + os.pathsep + env.get("PYTHONPATH", "")
    env["GALO_SEM_COR"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "galo", *args],
        input=entrada, capture_output=True, text=True, encoding="utf-8",
        cwd=cwd or RAIZ, env=env, timeout=timeout,
    )


def ler_exemplo(nome: str) -> str:
    with open(os.path.join(EXEMPLOS, nome), encoding="utf-8") as f:
        return f.read()
