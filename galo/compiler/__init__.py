"""Frontend e gerador de bytecode da GALO.

Pipeline:  código-fonte -> Lexer -> tokens -> Parser -> AST
           -> Analyzer (AST anotada) -> CodeGen -> Module (bytecode)

Módulos importados com `importe` são compilados recursivamente pelo
ModuleLoader e incluídos no mesmo Module: o .galoc resultante é autossuficiente.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from ..errors import CompilationError, GaloError, GaloLexError, GaloSemanticError, GaloSyntaxError
from .bytecode import Module, ModuleEntry
from .codegen import CodeGen
from .lexer import Lexer
from .parser import Parser
from .semantic import Analyzer


@dataclass
class CompileResult:
    module: Module
    warnings: list = field(default_factory=list)
    program: object = None
    new_globals: dict = field(default_factory=dict)
    sources: dict = field(default_factory=dict)


class ModuleInfo:
    """Módulo já compilado: índice no programa, nome exibido e símbolos exportados."""

    __slots__ = ("index", "name", "path", "exports", "code")

    def __init__(self, index: int, name: str, path: str, exports: dict, code) -> None:
        self.index = index
        self.name = name
        self.path = path
        self.exports = exports  # chave canônica -> Symbol
        self.code = code


class ModuleLoader:
    def __init__(self, base_dir: str) -> None:
        self.base_dir = os.path.abspath(base_dir)
        self.entries: list[ModuleInfo] = []
        self.by_path: dict[str, ModuleInfo] = {}
        self.stack: list[str] = []
        self.sources: dict[str, str] = {}
        self.warnings: list = []

    def display(self, abs_path: str) -> str:
        return os.path.relpath(abs_path, self.base_dir).replace(os.sep, "/")

    def load(self, path_text: str, importer_dir: str | None, node, importer_file: str | None) -> ModuleInfo:
        target = path_text if path_text.endswith(".galo") else path_text + ".galo"
        abs_path = os.path.normpath(os.path.join(importer_dir or self.base_dir, target))

        def fail(message: str, suggestion: str | None = None) -> CompilationError:
            return CompilationError([GaloSemanticError("G220", message, node.line, node.col, 7, suggestion, importer_file)])

        if abs_path in self.by_path:
            return self.by_path[abs_path]
        if abs_path in self.stack:
            cycle = self.stack[self.stack.index(abs_path):] + [abs_path]
            raise fail("Importação circular: " + " → ".join(self.display(p) for p in cycle) + ".",
                       "Mova o código usado pelos dois módulos para um terceiro módulo, importado por ambos.")
        try:
            with open(abs_path, encoding="utf-8") as f:
                source = f.read()
        except FileNotFoundError:
            raise fail(f'O módulo "{path_text}" não foi encontrado (procurado em {self.display(abs_path)}).',
                       "O caminho é relativo à pasta do arquivo que faz a importação.")
        except (OSError, UnicodeDecodeError) as exc:
            raise fail(f'Não foi possível ler o módulo "{path_text}": {exc}.')
        name = self.display(abs_path)
        self.sources[name] = source
        self.stack.append(abs_path)
        try:
            try:
                program = parse_source(source, name)
            except (GaloLexError, GaloSyntaxError) as err:
                raise CompilationError([err]) from None
            analyzer = Analyzer(name, loader=self, module_dir=os.path.dirname(abs_path))
            self.warnings.extend(analyzer.analyze(program))
            code = CodeGen(name).compile_program(program).code
        finally:
            self.stack.pop()
        code.name = f"<módulo {name}>"
        exports = {k: sym for k, sym in analyzer.new_globals.items()
                   if not sym.imported and not sym.name.startswith("_")}
        info = ModuleInfo(len(self.entries), name, abs_path, exports, code)
        self.entries.append(info)
        self.by_path[abs_path] = info
        return info

    def module_entries(self) -> list[ModuleEntry]:
        return [ModuleEntry(i.name, i.code, [sym.name for sym in i.exports.values()]) for i in self.entries]


def default_base_dir(filename: str) -> str:
    if filename and os.path.isfile(filename):
        return os.path.dirname(os.path.abspath(filename))
    return os.getcwd()


def parse_source(source: str, filename: str = "<entrada>", repl: bool = False):
    tokens = Lexer(source, filename).tokenize()
    return Parser(tokens, filename, repl=repl).parse_program()


def compile_source(source: str, filename: str = "<entrada>", *, repl: bool = False,
                   session_symbols: dict | None = None, base_dir: str | None = None,
                   loader: ModuleLoader | None = None) -> CompileResult:
    """Compila código-fonte GALO (e os módulos que ele importa) em um Module.

    Lança CompilationError com todos os erros encontrados.
    """
    if base_dir is None:
        base_dir = loader.base_dir if loader is not None else default_base_dir(filename)
    loader = loader or ModuleLoader(base_dir)
    loader.sources.setdefault(filename, source)
    try:
        try:
            program = parse_source(source, filename, repl)
        except (GaloLexError, GaloSyntaxError) as err:
            raise CompilationError([err]) from None
        analyzer = Analyzer(filename, repl=repl, session_symbols=session_symbols, loader=loader, module_dir=base_dir)
        entry_path = os.path.abspath(filename) if filename and os.path.isfile(filename) else None
        if entry_path:
            loader.stack.append(entry_path)
        try:
            warnings = analyzer.analyze(program)
        finally:
            if entry_path:
                loader.stack.pop()
    except CompilationError as exc:
        exc.warnings = list(loader.warnings) + list(exc.warnings)
        exc.sources = loader.sources
        raise
    module = CodeGen(filename, repl=repl).compile_program(program)
    module.modules = loader.module_entries()
    return CompileResult(module, list(loader.warnings) + list(warnings), program, analyzer.new_globals, loader.sources)


def check_source(source: str, filename: str = "<entrada>", base_dir: str | None = None) -> list[GaloError]:
    """Devolve todos os diagnósticos (erros e avisos) sem lançar exceções."""
    try:
        result = compile_source(source, filename, base_dir=base_dir)
    except CompilationError as exc:
        return list(exc.errors) + list(exc.warnings)
    return list(result.warnings)


__all__ = ["CompileResult", "ModuleLoader", "compile_source", "check_source", "parse_source", "Module"]
