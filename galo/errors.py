"""Diagnósticos da GALO: erros e avisos com código, posição e sugestão.

Faixas de códigos:
    G0xx  erros léxicos      (caracteres, textos, números)
    G1xx  erros sintáticos   (estrutura das instruções)
    G2xx  erros semânticos   (nomes, escopos, tipos verificáveis antes da execução)
    G3xx  erros de execução  (detectados pela máquina virtual)
    G4xx  erros lançados pelo próprio programa (instrução `lance`)
    G5xx  erros de arquivo e de bytecode (.galoc)
    A2xx  avisos (não impedem a execução)
"""

from __future__ import annotations

import os
import sys


class GaloError(Exception):
    """Base de todos os diagnósticos da linguagem."""

    kind = "erro"
    title = "Erro GALO"
    is_warning = False

    def __init__(
        self,
        code: str,
        message: str,
        line: int | None = None,
        col: int | None = None,
        length: int = 1,
        suggestion: str | None = None,
        file: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.line = line
        self.col = col
        self.length = max(1, length or 1)
        self.suggestion = suggestion
        self.file = file
        # Rastro de chamadas (somente erros de execução): lista de (função, linha).
        self.trace: list[tuple[str, int | None]] = []
        # Verdadeiro quando o erro decorre de código que terminou cedo demais
        # (útil para o REPL pedir mais linhas em vez de acusar erro).
        self.incomplete = False

    def __str__(self) -> str:  # pragma: no cover - conveniência de depuração
        return format_diagnostic(self)

    def to_dict(self) -> dict:
        return {
            "codigo": self.code,
            "tipo": self.kind,
            "gravidade": "aviso" if self.is_warning else "erro",
            "mensagem": self.message,
            "sugestao": self.suggestion,
            "arquivo": self.file,
            "linha": self.line,
            "coluna": self.col,
            "comprimento": self.length,
        }


class GaloLexError(GaloError):
    kind = "erro léxico"


class GaloSyntaxError(GaloError):
    kind = "erro sintático"


class GaloSemanticError(GaloError):
    kind = "erro semântico"


class GaloRuntimeError(GaloError):
    kind = "erro de execução"

    def __init__(self, code: str, message: str, *args, value=None, **kwargs) -> None:
        super().__init__(code, message, *args, **kwargs)
        # Valor GALO associado (por exemplo, o mapa passado para `lance`).
        self.value = value


class GaloBytecodeError(GaloError):
    kind = "erro de bytecode"


class GaloFileError(GaloError):
    kind = "erro de arquivo"


class GaloWarning(GaloError):
    kind = "aviso"
    title = "Aviso GALO"
    is_warning = True


class GaloInternalError(Exception):
    """Falha da própria implementação (nunca deveria acontecer)."""


class CompilationError(Exception):
    """Agrupa os erros encontrados durante a compilação."""

    def __init__(self, errors, warnings=()) -> None:
        self.errors = list(errors)
        self.warnings = list(warnings)
        super().__init__(self.errors[0].message if self.errors else "erro de compilação")


class GaloExit(Exception):
    """Lançada pela função interna `sair(código)` para encerrar o programa."""

    def __init__(self, code: int = 0) -> None:
        super().__init__(code)
        self.code = code


# ---------------------------------------------------------------------------
# Formatação
# ---------------------------------------------------------------------------


class _Style:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def _wrap(self, codes: str, text: str) -> str:
        return f"\x1b[{codes}m{text}\x1b[0m" if self.enabled else text

    def error(self, text: str) -> str:
        return self._wrap("1;31", text)

    def warning(self, text: str) -> str:
        return self._wrap("1;33", text)

    def bold(self, text: str) -> str:
        return self._wrap("1", text)

    def dim(self, text: str) -> str:
        return self._wrap("2", text)

    def caret(self, text: str) -> str:
        return self._wrap("1;35", text)


def use_color(stream) -> bool:
    """Decide se a saída deve usar cores ANSI."""
    if os.environ.get("NO_COLOR") or os.environ.get("GALO_SEM_COR"):
        return False
    try:
        return stream.isatty()
    except Exception:
        return False


def _excerpt(source_lines, line: int, col: int | None, length: int, style: _Style) -> list[str]:
    if not source_lines or line is None or line < 1 or line > len(source_lines):
        return []
    text = source_lines[line - 1].rstrip("\n")
    number = str(line)
    gutter = " " * len(number)
    out = [style.dim(f"  {number} | ") + text]
    if col is not None and col >= 1:
        # Preserva tabulações para que o marcador fique alinhado.
        prefix = "".join("\t" if ch == "\t" else " " for ch in text[: col - 1])
        available = max(1, len(text) - (col - 1))
        marks = "^" * max(1, min(length, available if col - 1 < len(text) else 1))
        out.append(style.dim(f"  {gutter} | ") + prefix + style.caret(marks))
    return out


def format_trace(trace: list[tuple[str, int | None]], limit_head: int = 6, limit_tail: int = 10) -> list[str]:
    lines = ["Rastro de chamadas (a mais recente por último):"]

    def fmt(entry):
        name, line = entry
        where = "programa principal" if name == "<programa>" else f"função {name}"
        return f"  {where}, linha {line}" if line else f"  {where}"

    if len(trace) > limit_head + limit_tail:
        lines += [fmt(e) for e in trace[:limit_head]]
        omitted = len(trace) - limit_head - limit_tail
        lines.append(f"  ... {omitted} chamadas omitidas ...")
        lines += [fmt(e) for e in trace[-limit_tail:]]
    else:
        lines += [fmt(e) for e in trace]
    return lines


def format_diagnostic(err: GaloError, source: str | None = None, color: bool = False) -> str:
    """Formata um diagnóstico no padrão oficial da GALO."""
    style = _Style(color)
    head = f"{err.title} [{err.code}] — {err.kind}"
    out = [style.warning(head) if err.is_warning else style.error(head)]
    if err.file:
        out.append(f"Arquivo: {err.file}")
    if err.line is not None:
        out.append(f"Linha: {err.line}, coluna: {err.col if err.col is not None else 1}")
        lines = source.splitlines() if source is not None else None
        excerpt = _excerpt(lines, err.line, err.col, err.length, style)
        if excerpt:
            out.append("")
            out.extend(excerpt)
    out.append("")
    out.append(err.message)
    if err.suggestion:
        out.append("")
        out.append(style.bold("Sugestão:"))
        out.append(err.suggestion)
    if err.trace and len(err.trace) > 1:
        out.append("")
        out.extend(format_trace(err.trace))
    return "\n".join(out)


def format_short(err: GaloError) -> str:
    """Formato de uma linha (arquivo:linha:coluna: erro [código]: mensagem), para editores."""
    where = f"{err.file or '<entrada>'}:{err.line or 1}:{err.col or 1}"
    severity = "aviso" if err.is_warning else "erro"
    return f"{where}: {severity} [{err.code}]: {err.message}"


def print_diagnostic(err: GaloError, source: str | None = None, stream=None) -> None:
    stream = stream or sys.stderr
    if os.environ.get("GALO_FORMATO") == "curto":
        stream.write(format_short(err) + "\n")
    else:
        stream.write(format_diagnostic(err, source, use_color(stream)) + "\n\n")
    stream.flush()
