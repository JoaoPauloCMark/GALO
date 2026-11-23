"""REPL (modo interativo) da GALO."""

from __future__ import annotations

import os
import sys

from .. import __version__
from ..errors import CompilationError, GaloExit, GaloRuntimeError, format_diagnostic, use_color
from ..session import Session

BANNER = f"GALO {__version__} — modo interativo. Digite :ajuda para ver os comandos ou :sair para sair."

HELP = """Comandos do modo interativo:
  :ajuda              mostra esta mensagem
  :sair               encerra o modo interativo (o mesmo que Ctrl+D)
  :variaveis          lista as variáveis, constantes e funções definidas
  :carregar ARQUIVO   executa um arquivo .galo dentro da sessão atual
  :limpar             apaga todas as definições e recomeça a sessão

Dicas:
  * Variáveis e funções continuam disponíveis entre uma entrada e outra.
  * Expressões soltas mostram seu valor: digite 2 + 3 e pressione Enter.
  * Blocos (se, enquanto, função...) continuam na linha seguinte até o 'fim'.
    Uma linha em branco força a avaliação do que já foi digitado.
"""


def _setup_history() -> None:
    try:
        import atexit
        import readline
    except ImportError:  # pragma: no cover - Windows sem readline
        return
    path = os.path.join(os.path.expanduser("~"), ".galo_historico")
    try:
        readline.read_history_file(path)
    except OSError:
        pass
    readline.set_history_length(1000)

    def save():
        try:
            readline.write_history_file(path)
        except OSError:
            pass

    atexit.register(save)


def run_repl(input_fn=None, out=None, err=None, banner: bool = True) -> int:
    interactive = input_fn is None
    if interactive:
        _setup_history()
    input_fn = input_fn or input
    out = out or sys.stdout
    err = err or sys.stderr
    color = use_color(err)
    session = Session(out=out, input_fn=input_fn)
    if banner:
        out.write(BANNER + "\n")
    buffer: list[str] = []

    def report(e, source):
        err.write(format_diagnostic(e, source, color) + "\n\n")
        err.flush()

    while True:
        prompt = "galo> " if not buffer else "  ... "
        try:
            line = input_fn(prompt)
        except EOFError:
            out.write("\n")
            return 0
        except KeyboardInterrupt:
            out.write("\n(entrada cancelada)\n")
            buffer = []
            continue

        stripped = line.strip()
        if len(stripped) > 1 and stripped[0] == ":" and stripped[1].isalpha():
            if buffer:
                out.write("(entrada incompleta descartada)\n")
                buffer = []
            command, _, rest = stripped.partition(" ")
            command = command.lower()
            if command in (":sair", ":s", ":q"):
                return 0
            if command in (":ajuda", ":a", ":h"):
                out.write(HELP)
            elif command in (":variaveis", ":variáveis", ":v"):
                names = session.names()
                if not names:
                    out.write("(nenhuma definição ainda)\n")
                for name, kind, value in names:
                    out.write(f"  {name:<20} {kind:<10} {value}\n")
            elif command == ":limpar":
                session = Session(out=out, input_fn=input_fn)
                out.write("Sessão reiniciada.\n")
            elif command == ":carregar":
                path = rest.strip()
                try:
                    with open(path, encoding="utf-8") as f:
                        source = f.read()
                except OSError as exc:
                    err.write(f"Não foi possível abrir '{path}': {exc.strerror or exc}\n")
                    continue
                try:
                    session.execute(source)
                except CompilationError as exc:
                    for e in exc.errors:
                        report(e, source)
                except GaloRuntimeError as e:
                    report(e, source)
                except GaloExit as ex:
                    return ex.code
            else:
                err.write(f"Comando desconhecido: {command}. Digite :ajuda para ver os comandos.\n")
            continue

        buffer.append(line)
        source = "\n".join(buffer)
        if not source.strip():
            buffer = []
            continue
        try:
            session.execute(source)
        except CompilationError as exc:
            if line.strip() and any(e.incomplete for e in exc.errors):
                continue  # bloco ainda aberto: pede a próxima linha
            for e in exc.errors:
                report(e, source)
        except GaloRuntimeError as e:
            out.flush()
            report(e, source)
        except GaloExit as ex:
            return ex.code
        except KeyboardInterrupt:
            out.write("\nExecução interrompida.\n")
        buffer = []
