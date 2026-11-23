"""Comando de linha `galo`."""

from __future__ import annotations

import json
import os
import sys

from .. import BYTECODE_VERSION, __version__
from ..compiler import check_source, compile_source
from ..compiler.bytecode import disassemble_module, dump_module, load_module
from ..compiler.lexer import tokenize
from ..errors import (
    CompilationError, GaloBytecodeError, GaloError, GaloExit, GaloFileError, GaloInternalError,
    GaloRuntimeError, print_diagnostic,
)
from ..runtime.vm import DEFAULT_MAX_FRAMES, VM

EXIT_OK = 0
EXIT_COMPILE_ERROR = 1
EXIT_RUNTIME_ERROR = 2
EXIT_FILE_ERROR = 3
EXIT_INTERNAL_ERROR = 70
EXIT_USAGE = 64
EXIT_INTERRUPTED = 130

USAGE = f"""GALO {__version__} — linguagem de programação em português

Uso:
  galo executar <arquivo.galo> [argumentos...]   Compila e executa um programa
  galo compilar <arquivo.galo> [-o saída.galoc]  Gera o bytecode (.galoc)
  galo rodar <arquivo.galoc> [argumentos...]     Executa um programa compilado
  galo verificar <arquivo.galo> [--json]         Procura erros sem executar
  galo repl                                      Modo interativo
  galo desmontar <arquivo.galo|arquivo.galoc>    Mostra o bytecode gerado
  galo tokens <arquivo.galo>                     Mostra os tokens (depuração)
  galo ast <arquivo.galo>                        Mostra a árvore sintática (depuração)
  galo lsp                                       Servidor de linguagem para editores
  galo --versao                                  Mostra a versão
  galo ajuda                                     Mostra esta ajuda

Atalhos:
  galo programa.galo     é o mesmo que  galo executar programa.galo
  galo programa.galoc    é o mesmo que  galo rodar programa.galoc

Opções:
  --limite-pilha N   Máximo de chamadas de função aninhadas (padrão: {DEFAULT_MAX_FRAMES})
  --sem-cor          Não usa cores nas mensagens de erro
  --formato-curto    Erros em uma linha (arquivo:linha:coluna: erro [código]: mensagem)

Códigos de saída: 0 sucesso, 1 erro de compilação, 2 erro de execução,
3 erro de arquivo/bytecode, 64 uso incorreto, 130 interrompido.
"""

VERSION_ALIASES = {"--versao", "--versão", "-v", "versao", "versão", "--version"}
HELP_ALIASES = {"ajuda", "--ajuda", "-h", "--help", "help", "-a"}


def _usage_error(message: str) -> int:
    sys.stderr.write(f"galo: {message}\nUse 'galo ajuda' para ver os comandos disponíveis.\n")
    return EXIT_USAGE


def _read_source(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        raise GaloFileError("G501", f'O arquivo "{path}" não foi encontrado.',
                            suggestion="Verifique o nome do arquivo e a pasta atual do terminal.")
    except IsADirectoryError:
        raise GaloFileError("G501", f'"{path}" é uma pasta, não um arquivo.')
    except UnicodeDecodeError:
        raise GaloFileError("G501", f'O arquivo "{path}" não está em UTF-8.',
                            suggestion="Salve o arquivo com a codificação UTF-8 no seu editor.")
    except OSError as exc:
        raise GaloFileError("G501", f'Não foi possível ler "{path}": {exc.strerror or exc}.')


def _read_bytes(path: str) -> bytes:
    try:
        with open(path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        raise GaloFileError("G501", f'O arquivo "{path}" não foi encontrado.',
                            suggestion="Para gerar o bytecode, use: galo compilar programa.galo")
    except IsADirectoryError:
        raise GaloFileError("G501", f'"{path}" é uma pasta, não um arquivo.')
    except OSError as exc:
        raise GaloFileError("G501", f'Não foi possível ler "{path}": {exc.strerror or exc}.')


def _source_for(err, sources: dict | None, default: str | None) -> str | None:
    if sources and err.file in sources:
        return sources[err.file]
    return default


def _print_compilation_error(exc: CompilationError, source: str) -> None:
    sources = getattr(exc, "sources", None)
    for err in exc.errors:
        print_diagnostic(err, _source_for(err, sources, source))
    for w in exc.warnings:
        print_diagnostic(w, _source_for(w, sources, source))
    n = len(exc.errors)
    sys.stderr.write(f"{n} erro{'s' if n != 1 else ''} encontrado{'s' if n != 1 else ''}. O programa não foi executado.\n")


PASSTHROUGH_COMMANDS = {"executar", "rodar"}


def _parse_options(args: list[str], passthrough: bool) -> tuple[list[str], dict]:
    """Separa as opções (--limite-pilha, -o, --json) dos argumentos posicionais.

    Em `executar` e `rodar` (passthrough), tudo o que vem depois do arquivo do
    programa pertence ao programa GALO e é acessível com argumentos().
    """
    opts: dict = {}
    rest: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if passthrough and rest:
            rest.append(a)
        elif a in ("--limite-pilha",):
            if i + 1 >= len(args) or not args[i + 1].isdigit():
                raise ValueError("--limite-pilha precisa de um número inteiro positivo")
            opts["max_frames"] = max(10, int(args[i + 1]))
            i += 1
        elif a.startswith("--limite-pilha="):
            value = a.split("=", 1)[1]
            if not value.isdigit():
                raise ValueError("--limite-pilha precisa de um número inteiro positivo")
            opts["max_frames"] = max(10, int(value))
        elif a in ("-o", "--saida", "--saída"):
            if i + 1 >= len(args):
                raise ValueError(f"{a} precisa do nome do arquivo de saída")
            opts["output"] = args[i + 1]
            i += 1
        elif a == "--json":
            opts["json"] = True
        elif a.startswith("-") and a != "-":
            raise ValueError(f"opção desconhecida: {a}")
        else:
            rest.append(a)
        i += 1
    return rest, opts


def _run_module(module, source: str | None, args, max_frames: int, sources: dict | None = None,
                base_dir: str | None = None) -> int:
    vm = VM(args=args, max_frames=max_frames)
    if base_dir:
        vm.base_dir = base_dir
    try:
        vm.run(module)
    except GaloRuntimeError as err:
        sys.stdout.flush()
        print_diagnostic(err, _source_for(err, sources, source if err.file == module.source_name else None))
        return EXIT_RUNTIME_ERROR
    except GaloExit as ex:
        sys.stdout.flush()
        return ex.code
    except KeyboardInterrupt:
        sys.stdout.flush()
        sys.stderr.write("\nExecução interrompida.\n")
        return EXIT_INTERRUPTED
    return EXIT_OK


# ---------------------------------------------------------------- comandos


def cmd_executar(args: list[str], opts: dict) -> int:
    if not args:
        return _usage_error("informe o arquivo a executar: galo executar programa.galo")
    path, program_args = args[0], args[1:]
    if path.endswith(".galoc"):
        return cmd_rodar(args, opts)
    source = _read_source(path)
    try:
        result = compile_source(source, path)
    except CompilationError as exc:
        _print_compilation_error(exc, source)
        return EXIT_COMPILE_ERROR
    return _run_module(result.module, source, program_args, opts.get("max_frames", DEFAULT_MAX_FRAMES), result.sources,
                       os.path.dirname(os.path.abspath(path)))


def cmd_compilar(args: list[str], opts: dict) -> int:
    if not args:
        return _usage_error("informe o arquivo a compilar: galo compilar programa.galo")
    if len(args) > 1:
        return _usage_error("o comando compilar recebe apenas um arquivo")
    path = args[0]
    source = _read_source(path)
    try:
        result = compile_source(source, os.path.basename(path), base_dir=os.path.dirname(os.path.abspath(path)))
    except CompilationError as exc:
        _print_compilation_error(exc, source)
        return EXIT_COMPILE_ERROR
    for w in result.warnings:
        print_diagnostic(w, source)
    output = opts.get("output") or (os.path.splitext(path)[0] + ".galoc")
    data = dump_module(result.module)
    try:
        with open(output, "wb") as f:
            f.write(data)
    except OSError as exc:
        raise GaloFileError("G501", f'Não foi possível gravar "{output}": {exc.strerror or exc}.')
    print(f"Compilado: {path} -> {output} ({len(data)} bytes, formato v{BYTECODE_VERSION})")
    return EXIT_OK


def _source_near(galoc_path: str, source_name: str) -> str | None:
    """Tenta achar o código-fonte (apenas para mostrar trechos nos erros)."""
    if not source_name:
        return None
    for candidate in (os.path.join(os.path.dirname(os.path.abspath(galoc_path)), source_name), source_name):
        try:
            with open(candidate, encoding="utf-8") as f:
                return f.read()
        except (OSError, UnicodeDecodeError):
            continue
    return None


def cmd_rodar(args: list[str], opts: dict) -> int:
    if not args:
        return _usage_error("informe o arquivo compilado: galo rodar programa.galoc")
    path, program_args = args[0], args[1:]
    if path.endswith(".galo"):
        sys.stderr.write(f"galo: '{path}' é código-fonte; executando com 'galo executar'.\n")
        return cmd_executar(args, opts)
    module = load_module(_read_bytes(path), path)
    names = [module.source_name] + [m.name for m in module.modules]
    sources = {n: src for n in names if (src := _source_near(path, n)) is not None}
    return _run_module(module, sources.get(module.source_name), program_args,
                       opts.get("max_frames", DEFAULT_MAX_FRAMES), sources, os.path.dirname(os.path.abspath(path)))


def cmd_verificar(args: list[str], opts: dict) -> int:
    if not args:
        return _usage_error("informe o arquivo a verificar: galo verificar programa.galo")
    status = EXIT_OK
    report = []
    for path in args:
        source = _read_source(path)
        diags = check_source(source, path, base_dir=os.path.dirname(os.path.abspath(path)))
        errors = [d for d in diags if not d.is_warning]
        warnings = [d for d in diags if d.is_warning]
        if errors:
            status = EXIT_COMPILE_ERROR
        if opts.get("json"):
            report.extend(d.to_dict() for d in diags)
            continue
        sources = {}
        for d in diags:
            if d.file and d.file != path and d.file not in sources:
                try:
                    sources[d.file] = _read_source(os.path.join(os.path.dirname(os.path.abspath(path)), d.file))
                except GaloFileError:
                    sources[d.file] = None
            print_diagnostic(d, source if d.file in (path, None) else sources.get(d.file))
        if errors:
            sys.stderr.write(f"{path}: {len(errors)} erro(s), {len(warnings)} aviso(s).\n")
        else:
            extra = f" ({len(warnings)} aviso(s))" if warnings else ""
            print(f"{path}: nenhum erro encontrado{extra}.")
    if opts.get("json"):
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return status


def cmd_desmontar(args: list[str], opts: dict) -> int:
    if not args:
        return _usage_error("informe o arquivo: galo desmontar programa.galo")
    path = args[0]
    if path.endswith(".galoc"):
        module = load_module(_read_bytes(path), path)
    else:
        source = _read_source(path)
        try:
            module = compile_source(source, path).module
        except CompilationError as exc:
            _print_compilation_error(exc, source)
            return EXIT_COMPILE_ERROR
    if module.program_name:
        print(f'programa "{module.program_name}"  (origem: {module.source_name}, GALO {module.galo_version})\n')
    print("\n".join(disassemble_module(module)))
    return EXIT_OK


def cmd_tokens(args: list[str], opts: dict) -> int:
    if not args:
        return _usage_error("informe o arquivo: galo tokens programa.galo")
    source = _read_source(args[0])
    try:
        toks = tokenize(source, args[0])
    except GaloError as err:
        print_diagnostic(err, source)
        return EXIT_COMPILE_ERROR
    for t in toks:
        value = "" if t.kind in ("NL", "EOF") else (t.text or str(t.value))
        print(f"{t.line:>4}:{t.col:<4} {t.kind:<12} {value}")
    return EXIT_OK


def cmd_ast(args: list[str], opts: dict) -> int:
    from ..compiler import parse_source
    from ..compiler.ast import dump

    if not args:
        return _usage_error("informe o arquivo: galo ast programa.galo")
    source = _read_source(args[0])
    try:
        program = parse_source(source, args[0])
    except GaloError as err:
        print_diagnostic(err, source)
        return EXIT_COMPILE_ERROR
    print(dump(program))
    return EXIT_OK


def cmd_repl(args: list[str], opts: dict) -> int:
    from .repl import run_repl

    return run_repl()


def cmd_lsp(args: list[str], opts: dict) -> int:
    from ..lsp.server import serve

    return serve()


COMMANDS = {
    "executar": cmd_executar,
    "compilar": cmd_compilar,
    "rodar": cmd_rodar,
    "verificar": cmd_verificar,
    "desmontar": cmd_desmontar,
    "tokens": cmd_tokens,
    "ast": cmd_ast,
    "repl": cmd_repl,
    "lsp": cmd_lsp,
}


def _configure_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        enc = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
        if enc != "utf8" and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="backslashreplace")
            except Exception:
                pass


def main(argv: list[str] | None = None) -> int:
    _configure_streams()
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--sem-cor" in argv:
        argv.remove("--sem-cor")
        os.environ["GALO_SEM_COR"] = "1"
    if "--formato-curto" in argv:
        argv.remove("--formato-curto")
        os.environ["GALO_FORMATO"] = "curto"
    if not argv:
        print(USAGE)
        return EXIT_OK
    cmd = argv[0]
    if cmd in VERSION_ALIASES:
        print(f"GALO {__version__} (bytecode v{BYTECODE_VERSION}, Python {sys.version.split()[0]})")
        return EXIT_OK
    if cmd in HELP_ALIASES:
        print(USAGE)
        return EXIT_OK
    if cmd.endswith(".galo") or cmd.endswith(".galoc"):
        argv = ["executar" if cmd.endswith(".galo") else "rodar"] + argv
        cmd = argv[0]
    handler = COMMANDS.get(cmd)
    if handler is None:
        import difflib

        close = difflib.get_close_matches(cmd, list(COMMANDS), n=1)
        hint = f" Você quis dizer '{close[0]}'?" if close else ""
        return _usage_error(f"comando desconhecido '{cmd}'.{hint}")
    try:
        args, opts = _parse_options(argv[1:], cmd in PASSTHROUGH_COMMANDS)
    except ValueError as exc:
        return _usage_error(str(exc))
    try:
        return handler(args, opts)
    except (GaloFileError, GaloBytecodeError) as err:
        print_diagnostic(err)
        return EXIT_FILE_ERROR
    except GaloInternalError as err:
        sys.stderr.write(f"Erro interno da GALO: {err}\n"
                         "Isto é uma falha da implementação, não do seu programa. "
                         "Execute com GALO_DEPURAR=1 para ver detalhes.\n")
        if os.environ.get("GALO_DEPURAR"):
            raise
        return EXIT_INTERNAL_ERROR


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
