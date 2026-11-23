"""Análise semântica da GALO.

Responsabilidades:
  * resolução de nomes e escopos de bloco (estáticos/léxicos);
  * detecção de uso antes da definição, redefinição e ocultação de nomes;
  * identificação de variáveis capturadas por funções internas (closures);
  * verificação de constantes, aridade de chamadas e de `retorne`/`pare`;
  * inferência de tipos conservadora: acusa apenas erros certos.

O resultado é a própria AST anotada:
  Nome.res     -> ("global", chave) | ("local", Símbolo) | ("free", índice)
  Defina.sym, Param.sym, VarDecl.sym, DefFuncao.sym -> Símbolo declarado
  DefFuncao.ctx, FuncaoAnonima.ctx, Programa.ctx -> FuncCtx (slots e capturas)
  Block.scope  -> Scope (símbolos declarados diretamente no bloco)
"""

from __future__ import annotations

import difflib

from ..errors import CompilationError, GaloSemanticError, GaloWarning
from ..runtime.values import binop_message, describe_spec, describe_types
from ..stdlib import BUILTINS, CONSTANTS
from . import ast as A
from . import typesys as T
from .tokens import canonical


class Symbol:
    __slots__ = (
        "name", "key", "kind", "type", "slot", "is_global", "captured", "ctx",
        "line", "col", "params", "param_names", "ret", "value_type", "session", "native",
        "param_keys", "required", "fields", "methods", "imported", "module",
    )

    def __init__(self, name, key, kind, line, col, typ=None) -> None:
        self.name = name
        self.key = key
        self.kind = kind  # "variável" | "constante" | "função" | "parâmetro" | "interna"
        self.type = typ   # tipo declarado (frozenset) ou None
        self.slot = None
        self.is_global = False
        self.captured = False
        self.ctx = None
        self.line = line
        self.col = col
        self.params = None       # tipos dos parâmetros (funções do usuário)
        self.param_names = None
        self.ret = None          # tipo de retorno declarado
        self.value_type = None   # tipo conhecido do valor (constantes)
        self.session = False     # veio de uma entrada anterior do REPL
        self.native = None       # NativeFunction (funções internas)
        self.param_keys = None   # chaves canônicas dos parâmetros (argumentos nomeados)
        self.required = 0        # parâmetros sem valor padrão
        self.fields = None       # registros: lista de (nome, chave, tipo, tem_padrão)
        self.methods = None      # registros: chave -> Símbolo do método
        self.imported = False    # veio de `importe` (não é reexportado)
        self.module = None       # módulos: ModuleInfo do módulo importado

    def static_type(self):
        """Tipo conhecido em tempo de compilação (None = desconhecido)."""
        if self.kind == "função":
            return T.T_FUNC
        if self.kind == "registro":
            return T.T_TIPO
        if self.kind == "módulo":
            return T.T_MODULO
        if self.kind == "interna":
            return self.value_type
        if self.kind == "constante":
            return self.type if self.type is not None else self.value_type
        return self.type  # variável/parâmetro: só o tipo declarado é garantido


class FuncCtx:
    def __init__(self, parent: "FuncCtx | None", name: str, is_module: bool = False) -> None:
        self.parent = parent
        self.name = name
        self.is_module = is_module
        self.nlocals = 0
        self.local_names: list[str] = []
        self.freevars: list[tuple[Symbol, tuple[int, int]]] = []
        self.free_map: dict[Symbol, int] = {}
        self.return_type = None
        self.has_return_type = False
        self.loop_depth = 0

    def new_slot(self, name: str) -> int:
        slot = self.nlocals
        self.nlocals += 1
        self.local_names.append(name)
        return slot


class Scope:
    def __init__(self, parent: "Scope | None", ctx: FuncCtx, kind: str) -> None:
        self.parent = parent
        self.ctx = ctx
        self.kind = kind  # "global" | "função" | "bloco"
        self.symbols: dict[str, Symbol] = {}
        self.later: dict[str, int] = {}
        self.pending: list = []
        self.declared: list[Symbol] = []


def _gender(kind: str) -> str:
    return "a" if kind in ("variável", "constante", "função") else "o"


def always_returns(stmts) -> bool:
    for st in stmts:
        if isinstance(st, (A.Retorne, A.Lance)):
            return True
        if isinstance(st, A.Se) and st.else_block is not None:
            if all(always_returns(b.stmts) for _, b in st.branches) and always_returns(st.else_block.stmts):
                return True
        if isinstance(st, A.Tente):
            if always_returns(st.body.stmts) and always_returns(st.handler.stmts):
                return True
        if isinstance(st, A.Enquanto) and isinstance(st.cond, A.Literal) and st.cond.value is True:
            if not _has_break(st.body.stmts):
                return True
    return False


def _has_break(stmts) -> bool:
    for st in stmts:
        if isinstance(st, A.Pare):
            return True
        if isinstance(st, A.Se):
            if any(_has_break(b.stmts) for _, b in st.branches):
                return True
            if st.else_block and _has_break(st.else_block.stmts):
                return True
        if isinstance(st, A.Tente) and (_has_break(st.body.stmts) or _has_break(st.handler.stmts)):
            return True
    return False


class Analyzer:
    def __init__(self, filename: str | None = None, repl: bool = False, session_symbols=None,
                 loader=None, module_dir: str | None = None) -> None:
        self.filename = filename
        self.repl = repl
        self.loader = loader          # carrega e compila os módulos importados
        self.module_dir = module_dir  # pasta usada para resolver caminhos relativos
        self.record_syms: dict[str, Symbol] = {}
        self.session_symbols = session_symbols or {}
        self.errors: list[GaloSemanticError] = []
        self.warnings: list[GaloWarning] = []
        self.scope: Scope | None = None
        self.ctx: FuncCtx | None = None
        self.new_globals: dict[str, Symbol] = {}
        self._builtin_symbols: dict[str, Symbol] = {}

    # ------------------------------------------------------------ diagnósticos

    def error(self, code, message, line, col, length=1, suggestion=None) -> None:
        self.errors.append(GaloSemanticError(code, message, line, col, length, suggestion, self.filename))

    def warn(self, code, message, line, col, length=1, suggestion=None) -> None:
        self.warnings.append(GaloWarning(code, message, line, col, length, suggestion, self.filename))

    # ------------------------------------------------------------ entrada

    def analyze(self, prog: A.Programa):
        ctx = FuncCtx(None, "<programa>", is_module=True)
        g = Scope(None, ctx, "global")
        for key, sym in self.session_symbols.items():
            sym.session = True
            g.symbols[key] = sym
            if sym.kind == "registro":
                self.record_syms[sym.name] = sym
        self.scope, self.ctx = g, ctx
        self.visit_block(prog.body, g)
        prog.ctx = ctx
        prog.global_scope = g
        self.errors.sort(key=lambda e: (e.line or 0, e.col or 0))
        self.warnings.sort(key=lambda e: (e.line or 0, e.col or 0))
        if self.errors:
            raise CompilationError(self.errors, self.warnings)
        return self.warnings

    # ------------------------------------------------------------ tipos

    def resolve_type(self, annot: A.TypeAnnot | None):
        if annot is None:
            return None
        result: set[str] = set()
        for name, key in zip(annot.names, annot.keys):
            rec = self._lookup(key)
            if key not in T.TYPE_NAMES and rec is not None and rec.kind == "registro":
                result.add(rec.name)
                continue
            if key not in T.TYPE_NAMES:
                close = difflib.get_close_matches(key, list(T.TYPE_NAMES), n=1, cutoff=0.6)
                hint = f"Você quis dizer '{T.DISPLAY_TYPE_NAMES[list(T.TYPE_NAMES).index(close[0])]}'?\n" if close else ""
                records = sorted(self.record_syms)
                self.error("G211", f"Tipo desconhecido: '{name}'.", annot.line, annot.col, len(name),
                           hint + "Tipos disponíveis: " + ", ".join(T.DISPLAY_TYPE_NAMES + tuple(records)) + ".")
                return None
            spec = T.TYPE_NAMES[key]
            if spec is None:
                return None  # 'qualquer'
            result |= spec
        return frozenset(result)

    def _lookup(self, key: str) -> Symbol | None:
        s = self.scope
        while s is not None:
            sym = s.symbols.get(key)
            if sym is not None:
                return sym
            s = s.parent
        return None

    def single_record(self, t) -> Symbol | None:
        """Se o tipo estático é exatamente um registro conhecido, devolve seu símbolo."""
        if t is not None and len(t) == 1:
            (name,) = t
            return self.record_syms.get(name)
        return None

    # ------------------------------------------------------------ declarações

    def declare(self, name, key, kind, line, col, typ=None) -> Symbol:
        scope = self.scope
        scope.later.pop(key, None)
        existing = scope.symbols.get(key)
        if existing is not None:
            if not (self.repl and scope.kind == "global" and existing.session):
                what = {"função": "A função", "parâmetro": "O parâmetro", "constante": "A constante"}.get(existing.kind, "A variável")
                suggestion = (f"Para alterar o valor, use: {name} = novo_valor\n"
                              f"Para criar outro valor, escolha um nome diferente.")
                if existing.kind in ("função", "constante", "parâmetro") or kind == "função":
                    suggestion = "Escolha um nome diferente."
                self.error("G203", f"{what} '{existing.name}' já foi definid{_gender(existing.kind)} neste escopo "
                                   f"(linha {existing.line}).", line, col, len(name), suggestion)
                return existing
        else:
            s = scope.parent
            while s is not None and s.ctx is scope.ctx:
                other = s.symbols.get(key)
                if other is not None and not (self.repl and other.session):
                    self.error(
                        "G204", f"Já existe '{other.name}' (definid{_gender(other.kind)} na linha {other.line}) visível neste ponto.",
                        line, col, len(name),
                        f"Dentro de uma mesma função, um bloco interno não pode criar outro valor com o mesmo nome.\n"
                        f"Para alterar o valor existente, use: {name} = ...\nPara criar um novo, escolha outro nome.",
                    )
                    return other
                s = s.parent
        sym = Symbol(name, key, kind, line, col, typ)
        sym.ctx = self.ctx
        sym.is_global = scope.kind == "global"
        if not sym.is_global:
            sym.slot = self.ctx.new_slot(name)
        else:
            self.new_globals[key] = sym
            if key in BUILTINS or key in CONSTANTS:
                self.warn("A201", f"O nome '{name}' esconde a função interna de mesmo nome.", line, col, len(name),
                          f"A partir daqui, '{name}' se refere ao seu valor e a função interna deixa de estar acessível. "
                          f"Considere outro nome.")
        scope.symbols[key] = sym
        scope.declared.append(sym)
        return sym

    def _check_param_order(self, params, what: str) -> int:
        """Parâmetros sem valor padrão não podem vir depois de um com padrão. Devolve os obrigatórios."""
        seen_default = None
        required = 0
        for p in params:
            if p.default is not None:
                seen_default = p
            elif seen_default is not None:
                self.error("G223", f"O {what} '{p.name}' não tem valor padrão, mas vem depois de '{seen_default.name}', que tem.",
                           p.line, p.col, len(p.name), f"Coloque os {what}s com valor padrão por último.")
            else:
                required += 1
        return required

    def _fill_signature(self, sym: Symbol, params, specs, ret) -> None:
        sym.params = list(specs)
        sym.param_names = [p.name for p in params]
        sym.param_keys = [p.key for p in params]
        sym.required = sum(1 for p in params if p.default is None)
        sym.ret = ret

    def declare_function(self, node: A.DefFuncao) -> Symbol:
        node.param_specs = [self.resolve_type(p.type) for p in node.params]
        node.ret_spec = self.resolve_type(node.ret)
        self._check_param_order(node.params, "parâmetro")
        sym = self.declare(node.name, node.key, "função", node.name_line, node.name_col)
        if sym.kind == "função":
            self._fill_signature(sym, node.params, node.param_specs, node.ret_spec if node.ret is not None else None)
        self.scope.pending.append((node, self.scope))
        return sym

    def declare_record_name(self, node: A.DefRegistro) -> Symbol:
        if self.scope.kind != "global":
            self.error("G224", "Registros só podem ser definidos no nível principal do arquivo.",
                       node.line, node.col, 8, "Mova o 'registro' para fora de funções e blocos.")
        if node.key in T.TYPE_NAMES or node.key in ("tipo", "modulo"):
            self.error("G226", f"'{node.name}' é o nome de um tipo da linguagem e não pode nomear um registro.",
                       node.name_line, node.name_col, len(node.name), "Escolha outro nome, de preferência com inicial maiúscula.")
        sym = self.declare(node.name, node.key, "registro", node.name_line, node.name_col)
        if sym.kind == "registro":
            self.record_syms[node.name] = sym
        return sym

    def declare_record_members(self, node: A.DefRegistro) -> None:
        sym = node.sym
        if sym is None or sym.kind != "registro":
            return
        seen: dict[str, A.Param] = {}
        for f in node.fields:
            if f.key in seen:
                self.error("G216", f"O campo '{f.name}' aparece mais de uma vez no registro '{node.name}'.",
                           f.line, f.col, len(f.name))
            seen[f.key] = f
            f.spec = self.resolve_type(f.type)
        self._check_param_order(node.fields, "campo")
        sym.fields = [(f.name, f.key, f.spec, f.default is not None) for f in node.fields]
        self._fill_signature(sym, node.fields, [f.spec for f in node.fields], frozenset({node.name}))
        sym.methods = {}
        for m in node.methods:
            if m.key in seen:
                self.error("G216", f"O método '{m.name}' tem o mesmo nome de um campo de '{node.name}'.",
                           m.name_line, m.name_col, len(m.name))
            if m.key in sym.methods:
                self.error("G203", f"O método '{m.name}' já foi definido no registro '{node.name}'.",
                           m.name_line, m.name_col, len(m.name))
            m.params.insert(0, A.Param(m.line, m.col, "eu", "eu", A.TypeAnnot(m.line, m.col, [node.name], [node.key])))
            m.param_specs = [self.resolve_type(p.type) for p in m.params]
            m.ret_spec = self.resolve_type(m.ret)
            self._check_param_order(m.params, "parâmetro")
            msym = Symbol(m.name, m.key, "função", m.name_line, m.name_col)
            self._fill_signature(msym, m.params[1:], m.param_specs[1:], m.ret_spec if m.ret is not None else None)
            sym.methods[m.key] = msym
            self.scope.pending.append((m, self.scope))
        self.scope.pending.append((node, self.scope))  # construtor (valores padrão dos campos)

    def analyze_constructor(self, node: A.DefRegistro, decl_scope: Scope) -> None:
        saved_scope, saved_ctx = self.scope, self.ctx
        ctx = FuncCtx(decl_scope.ctx, node.name)
        fscope = Scope(decl_scope, ctx, "função")
        self.scope, self.ctx = fscope, ctx
        seen: set[str] = set()
        for f in node.fields:
            if f.key in seen:  # já acusado (G216) em declare_record_members
                f.sym = Symbol(f.name, f.key, "parâmetro", f.line, f.col)
                f.sym.slot = ctx.new_slot(f.name)
                continue
            seen.add(f.key)
            if f.default is not None:
                t = self.visit_expr(f.default)
                if f.spec is not None and not T.compatible(t, f.spec):
                    self.error("G213", f"O valor padrão do campo '{f.name}' deve ser {describe_spec(T.spec_tuple(f.spec))}, "
                                       f"mas é {describe_types(T.spec_tuple(t))}.", f.default.line, f.default.col)
            f.sym = self.declare(f.name, f.key, "parâmetro", f.line, f.col, f.spec)
        node.ctor_ctx = ctx
        node.ctor_scope = fscope
        self.scope, self.ctx = saved_scope, saved_ctx

    # ------------------------------------------------------------ importação

    def process_import(self, st: A.Importe) -> None:
        st.processed = True
        declared = [st.alias] if st.alias is not None else list(st.names)
        entry = None
        if self.loader is None:
            self.error("G220", "Importação de módulos não está disponível neste contexto.", st.line, st.col, 7)
        else:
            try:
                entry = self.loader.load(st.path, self.module_dir, st, self.filename)
            except CompilationError as exc:
                self.errors.extend(e for e in exc.errors if e not in self.errors)
        if entry is None:
            for v in declared:
                v.sym = self.declare(v.name, v.key, "constante", v.line, v.col)
                v.sym.imported = True
            st.module_index = -1
            return
        st.module_index = entry.index
        if st.alias is not None:
            sym = self.declare(st.alias.name, st.alias.key, "módulo", st.alias.line, st.alias.col)
            sym.module = entry
            sym.imported = True
            st.alias.sym = sym
            return
        for v in st.names:
            exp = entry.exports.get(v.key)
            if exp is None:
                close = difflib.get_close_matches(v.key, list(entry.exports), n=1, cutoff=0.6)
                hint = f"Você quis dizer '{entry.exports[close[0]].name}'?" if close else (
                    "Nomes exportados: " + (", ".join(sorted(x.name for x in entry.exports.values())) or "nenhum"))
                self.error("G221", f"O módulo '{entry.name}' não exporta '{v.name}'.", v.line, v.col, len(v.name), hint)
                v.sym = self.declare(v.name, v.key, "constante", v.line, v.col)
                v.sym.imported = True
                continue
            kind = exp.kind if exp.kind in ("função", "registro", "módulo") else "constante"
            sym = self.declare(v.name, v.key, kind, v.line, v.col, exp.type)
            for attr in ("params", "param_names", "param_keys", "required", "ret", "value_type", "fields", "methods", "module"):
                setattr(sym, attr, getattr(exp, attr))
            if exp.kind == "variável":
                sym.value_type = exp.type
            sym.imported = True
            if kind == "registro":
                sym.name = exp.name
                self.record_syms[exp.name] = sym
            v.sym = sym

    def stmt_Importe(self, st: A.Importe) -> None:
        if not getattr(st, "processed", False):
            self.error("G224", "'importe' só pode ser usado no nível principal do arquivo (fora de funções e blocos).",
                       st.line, st.col, 7, "Coloque as importações no início do arquivo.")
            st.module_index = -1
            for v in ([st.alias] if st.alias else st.names):
                v.sym = None

    def stmt_DefRegistro(self, st: A.DefRegistro) -> None:
        pass  # declarado no início do bloco


    # ------------------------------------------------------------ resolução

    def builtin_symbol(self, key: str) -> Symbol:
        sym = self._builtin_symbols.get(key)
        if sym is None:
            if key in BUILTINS:
                nf = BUILTINS[key]
                sym = Symbol(nf.name, key, "interna", None, None)
                sym.native = nf
                sym.value_type = T.T_FUNC
            else:
                name, value, _ = CONSTANTS[key]
                sym = Symbol(name, key, "interna", None, None)
                sym.value_type = T.type_of_python_value(value)
            sym.is_global = True
            self._builtin_symbols[key] = sym
        return sym

    def free_index(self, ctx: FuncCtx, sym: Symbol) -> int:
        idx = ctx.free_map.get(sym)
        if idx is not None:
            return idx
        parent = ctx.parent
        if sym.ctx is parent:
            source = (0, sym.slot)
        else:
            source = (1, self.free_index(parent, sym))
        idx = len(ctx.freevars)
        ctx.freevars.append((sym, source))
        ctx.free_map[sym] = idx
        return idx

    def _visible_names(self) -> dict[str, str]:
        names: dict[str, str] = {}
        s = self.scope
        while s is not None:
            for k, sym in s.symbols.items():
                names.setdefault(k, sym.name)
            s = s.parent
        for k, nf in BUILTINS.items():
            names.setdefault(k, nf.name)
        for k, (n, _, _) in CONSTANTS.items():
            names.setdefault(k, n)
        return names

    def resolve(self, e: A.Nome, for_call: bool = False, for_assign: bool = False) -> Symbol | None:
        key = e.key
        s = self.scope
        while s is not None:
            sym = s.symbols.get(key)
            if sym is not None:
                if sym.is_global:
                    e.res = ("global", key)
                elif sym.ctx is self.ctx:
                    e.res = ("local", sym)
                else:
                    sym.captured = True
                    e.res = ("free", self.free_index(self.ctx, sym))
                e.sym = sym
                return sym
            if key in s.later:
                self.error("G202", f"'{e.name}' foi usado antes de ser definido "
                                   f"(a definição está na linha {s.later[key]}).",
                           e.line, e.col, e.length, "Mova a definição para antes deste ponto.")
                e.res = ("erro",)
                e.sym = None
                return None
            s = s.parent
        if key in BUILTINS or key in CONSTANTS:
            sym = self.builtin_symbol(key)
            if for_assign:
                self.error("G207", f"'{e.name}' é uma função interna da GALO e não pode receber outro valor.",
                           e.line, e.col, e.length, f"Para criar sua própria variável, use: defina {e.name}_valor como ...")
                e.res = ("erro",)
                e.sym = None
                return None
            e.res = ("global", key)
            e.sym = sym
            return sym

        if key == "eu":
            self.error("G225", "'eu' só pode ser usado dentro dos métodos de um registro.", e.line, e.col, 2,
                       "Dentro de um método, 'eu' é a instância que recebeu a chamada: eu.campo")
            e.res = ("erro",)
            e.sym = None
            return None
        names = self._visible_names()
        close = difflib.get_close_matches(key, list(names), n=1, cutoff=0.75)
        guess = f"Você quis dizer '{names[close[0]]}'?" if close else None
        if for_assign:
            self.error("G205", f"A variável \"{e.name}\" ainda não foi definida.", e.line, e.col, e.length,
                       (guess + "\n" if guess else "") + f"Para criar a variável, use:\ndefina {e.name} como ...")
        elif for_call:
            self.error("G201", f"A função \"{e.name}\" não foi definida.", e.line, e.col, e.length,
                       guess or f"Defina a função antes de usá-la:\nfunção {e.name}(...)\n    ...\nfim")
        else:
            if guess:
                suggestion = guess + f"\nSe for uma nova variável, declare-a antes de utilizá-la:\ndefina {e.name} como 0"
            elif getattr(e, "is_map_key", False):
                suggestion = f'Para usar o texto como chave do mapa, coloque-o entre aspas: {{"{e.name}": ...}}'
            else:
                suggestion = f"Declare a variável antes de utilizá-la:\ndefina {e.name} como 0"
            self.error("G201", f"A variável \"{e.name}\" não foi definida.", e.line, e.col, e.length, suggestion)
        e.res = ("erro",)
        e.sym = None
        return None

    # ------------------------------------------------------------ blocos

    def visit_block(self, block: A.Block, scope: Scope | None = None, pre=()) -> None:
        if scope is None:
            scope = Scope(self.scope, self.ctx, "bloco")
        saved = self.scope
        self.scope = scope
        block.scope = scope
        for decl, kind, spec in pre:
            if decl is not None:
                decl.sym = self.declare(decl.name, decl.key, kind, decl.line, decl.col, spec)
        for st in block.stmts:
            if isinstance(st, A.Defina) and not self._visible_in_function(scope.parent, st.key):
                # Se o nome já existe em um bloco externo da mesma função, a
                # redefinição será acusada (G204) e as referências continuam
                # apontando para o valor externo.
                scope.later.setdefault(st.key, st.name_line)
        if scope.kind == "global":
            for st in block.stmts:
                if isinstance(st, A.Importe):
                    self.process_import(st)
        records = [st for st in block.stmts if isinstance(st, A.DefRegistro)]
        for st in records:
            st.sym = self.declare_record_name(st)
        for st in records:
            self.declare_record_members(st)
        for st in block.stmts:
            if isinstance(st, A.DefFuncao):
                st.sym = self.declare_function(st)
        terminated = warned = False
        for st in block.stmts:
            if terminated and not warned:
                self.warn("A202", "Este código nunca será executado.", st.line, st.col, 1,
                          "Ele vem depois de um 'retorne', 'pare', 'continue' ou 'lance' no mesmo bloco.")
                warned = True
            self.visit_stmt(st)
            if isinstance(st, (A.Retorne, A.Pare, A.Continue, A.Lance)):
                terminated = True
        while scope.pending:
            node, decl_scope = scope.pending.pop(0)
            if isinstance(node, A.DefRegistro):
                self.analyze_constructor(node, decl_scope)
            else:
                self.analyze_function_body(node, decl_scope)
        self.scope = saved

    def _visible_in_function(self, scope: Scope | None, key: str) -> bool:
        ctx = self.ctx
        while scope is not None and scope.ctx is ctx:
            if key in scope.symbols:
                return True
            scope = scope.parent
        return False

    def analyze_function_body(self, node, decl_scope: Scope) -> None:
        saved_scope, saved_ctx = self.scope, self.ctx
        ctx = FuncCtx(decl_scope.ctx, node.name)
        ctx.return_type = node.ret_spec
        ctx.has_return_type = node.ret is not None
        fscope = Scope(decl_scope, ctx, "função")
        self.scope, self.ctx = fscope, ctx
        seen: set[str] = set()
        for p, spec in zip(node.params, node.param_specs):
            if p.default is not None:
                t = self.visit_expr(p.default)
                if spec is not None and not T.compatible(t, spec):
                    self.error("G213", f"O valor padrão do parâmetro '{p.name}' deve ser {describe_spec(T.spec_tuple(spec))}, "
                                       f"mas é {describe_types(T.spec_tuple(t))}.", p.default.line, p.default.col)
            if p.key in seen:
                self.error("G216", f"O parâmetro '{p.name}' aparece mais de uma vez na função '{node.name}'.",
                           p.line, p.col, len(p.name))
                p.sym = None
                ctx.new_slot(p.name)
                continue
            seen.add(p.key)
            p.sym = self.declare(p.name, p.key, "parâmetro", p.line, p.col, spec)
        self.visit_block(node.body, fscope)
        node.ctx = ctx
        rt = ctx.return_type
        if ctx.has_return_type and rt is not None and "nulo" not in rt and not always_returns(node.body.stmts):
            self.warn("A203", f"A função '{node.name}' declara que retorna {describe_spec(T.spec_tuple(rt))}, "
                              f"mas pode terminar sem executar 'retorne'.", node.line, node.col, 1,
                      "Se isso acontecer durante a execução, ocorrerá um erro de tipo de retorno.")
        self.scope, self.ctx = saved_scope, saved_ctx

    # ------------------------------------------------------------ instruções

    def visit_stmt(self, st) -> None:
        getattr(self, "stmt_" + type(st).__name__)(st)

    def stmt_DefFuncao(self, st: A.DefFuncao) -> None:
        pass  # declarada no início do bloco; corpo analisado ao final do bloco

    def stmt_Defina(self, st: A.Defina) -> None:
        vt = self.visit_expr(st.value)
        spec = self.resolve_type(st.type) if st.type is not None else None
        if st.type is not None and spec is not None and not T.compatible(vt, spec):
            what = "A constante" if st.constant else "A variável"
            self.error("G213", f"{what} '{st.name}' é do tipo {describe_spec(T.spec_tuple(spec))}, mas o valor inicial é "
                               f"{describe_types(T.spec_tuple(vt))}.", st.value.line, st.value.col)
        sym = self.declare(st.name, st.key, "constante" if st.constant else "variável", st.name_line, st.name_col, spec)
        if st.constant and sym.kind == "constante":
            sym.value_type = spec if spec is not None else vt
        st.sym = sym
        st.spec = spec

    def stmt_Atribuicao(self, st: A.Atribuicao) -> None:
        vt = self.visit_expr(st.value)
        st.spec = None
        target = st.target
        if isinstance(target, A.Nome):
            sym = self.resolve(target, for_assign=True)
            if sym is None:
                return
            if sym.kind == "constante":
                self.error("G206", f"'{sym.name}' é uma constante e não pode receber outro valor.",
                           target.line, target.col, target.length,
                           f"Se o valor precisa mudar, declare com 'defina' em vez de 'constante' (linha {sym.line}).")
                return
            if sym.kind == "função":
                self.error("G207", f"'{sym.name}' é uma função e não pode receber outro valor.",
                           target.line, target.col, target.length, "Escolha outro nome para a variável.")
                return
            current = sym.static_type()
            if st.op != "=":
                vt = self.binop_type(st.op[0], current, vt, st)
            if sym.type is not None and not T.compatible(vt, sym.type):
                self.error("G213", f"A variável '{sym.name}' é do tipo {describe_spec(T.spec_tuple(sym.type))}, mas recebeu "
                                   f"{describe_types(T.spec_tuple(vt))}.", st.value.line, st.value.col,
                           suggestion=f"A variável foi declarada com 'do tipo' na linha {sym.line}.")
            st.spec = sym.type
        elif isinstance(target, A.Indice):
            ot = self.visit_expr(target.obj)
            self.visit_expr(target.index)
            if ot is not None:
                if ot == T.T_TEXTO:
                    self.error("G219", "Textos não podem ser alterados por posição.", target.line, target.col,
                               suggestion="Crie um novo texto, por exemplo com substituir(...) ou fatia(...).")
                elif not (ot & {"lista", "mapa"}):
                    self.error("G219", f"Não é possível alterar posições de {describe_types(T.spec_tuple(ot))}.",
                               target.line, target.col)
            if st.op != "=":
                self.binop_type(st.op[0], None, vt, st)
        elif isinstance(target, A.Campo):
            ot = self.visit_expr(target.obj)
            rec = self.single_record(ot)
            if rec is not None and rec.fields is not None:
                key = canonical(target.name)
                field = next((f for f in rec.fields if f[1] == key), None)
                if field is None:
                    if rec.methods and key in rec.methods:
                        self.error("G222", f"'{target.name}' é um método de {rec.name} e não pode receber outro valor.",
                                   target.line, target.col, len(target.name))
                    else:
                        self._unknown_field(rec, target)
                elif field[2] is not None and not T.compatible(vt, field[2]):
                    self.error("G213", f"O campo '{field[0]}' de {rec.name} é do tipo {describe_spec(T.spec_tuple(field[2]))}, "
                                       f"mas recebeu {describe_types(T.spec_tuple(vt))}.", st.value.line, st.value.col)
            elif ot is not None and ot <= T.NO_FIELDS:
                self.error("G219", f"O acesso com '.' só funciona em mapas e registros, mas o valor é {describe_types(T.spec_tuple(ot))}.",
                           target.line, target.col)

    def check_condition(self, t, node, where: str) -> None:
        if t is not None and "booleano" not in t:
            self.error("G215", f"A condição {where} precisa ser um booleano (verdadeiro ou falso), mas é "
                               f"{describe_types(T.spec_tuple(t))}.", node.line, node.col, 1,
                       "Use uma comparação, por exemplo: se x > 0 então")

    def stmt_Se(self, st: A.Se) -> None:
        for cond, block in st.branches:
            self.check_condition(self.visit_expr(cond), cond, "do 'se'")
            self.visit_block(block)
        if st.else_block is not None:
            self.visit_block(st.else_block)

    def stmt_Enquanto(self, st: A.Enquanto) -> None:
        self.check_condition(self.visit_expr(st.cond), st.cond, "do 'enquanto'")
        self.ctx.loop_depth += 1
        self.visit_block(st.body)
        self.ctx.loop_depth -= 1

    def stmt_Repita(self, st: A.Repita) -> None:
        t = self.visit_expr(st.count)
        if t is not None and "inteiro" not in t:
            self.error("G213", f"A quantidade do 'repita' deve ser um inteiro, mas é {describe_types(T.spec_tuple(t))}.",
                       st.count.line, st.count.col)
        self.ctx.loop_depth += 1
        self.visit_block(st.body)
        self.ctx.loop_depth -= 1

    def stmt_ParaCada(self, st: A.ParaCada) -> None:
        t = self.visit_expr(st.iterable)
        if t is not None and not (t & T.T_INDEXABLE):
            hint = ("Para repetir um número de vezes, use 'para i de 1 até n faça'." if t & T.T_NUM
                    else "O 'para cada' percorre listas, textos e mapas.")
            self.error("G212", f"Não é possível percorrer {describe_types(T.spec_tuple(t))} com 'para cada'.",
                       st.iterable.line, st.iterable.col, 1, hint)
        if st.var2 is not None and st.var2.key == st.var1.key:
            self.error("G216", f"As duas variáveis do 'para cada' têm o mesmo nome ('{st.var1.name}').",
                       st.var2.line, st.var2.col, len(st.var2.name))
        self.ctx.loop_depth += 1
        pre = [(st.var1, "variável", None)]
        if st.var2 is not None and st.var2.key != st.var1.key:
            pre.append((st.var2, "variável", None))
        elif st.var2 is not None:
            st.var2.sym = None
        self.visit_block(st.body, pre=pre)
        self.ctx.loop_depth -= 1

    def stmt_ParaIntervalo(self, st: A.ParaIntervalo) -> None:
        for label, node in (("inicial", st.start), ("final", st.end), ("do passo", st.step)):
            if node is None:
                continue
            t = self.visit_expr(node)
            if t is not None and not (t & T.T_NUM):
                self.error("G213", f"O valor {label} do 'para' deve ser um número, mas é {describe_types(T.spec_tuple(t))}.",
                           node.line, node.col)
        if isinstance(st.step, A.Literal) and st.step.value == 0 and type(st.step.value) in (int, float):
            self.error("G213", "O passo do 'para' não pode ser zero: o laço nunca terminaria.", st.step.line, st.step.col)
        self.ctx.loop_depth += 1
        self.visit_block(st.body, pre=[(st.var, "variável", None)])
        self.ctx.loop_depth -= 1

    def stmt_Tente(self, st: A.Tente) -> None:
        self.visit_block(st.body)
        self.visit_block(st.handler, pre=[(st.err_var, "variável", None)])

    def stmt_Mostre(self, st: A.Mostre) -> None:
        for v in st.values:
            self.visit_expr(v)

    def stmt_Retorne(self, st: A.Retorne) -> None:
        vt = self.visit_expr(st.value) if st.value is not None else T.T_NULO
        if self.ctx.is_module:
            self.error("G208", "'retorne' só pode ser usado dentro de uma função.", st.line, st.col, 7,
                       "Para encerrar o programa antes do fim, use sair().")
            return
        rt = self.ctx.return_type
        if self.ctx.has_return_type and rt is not None and not T.compatible(vt, rt):
            where = st.value if st.value is not None else st
            got = "nenhum valor (nulo)" if st.value is None else describe_types(T.spec_tuple(vt))
            self.error("G214", f"A função '{self.ctx.name}' deveria retornar {describe_spec(T.spec_tuple(rt))}, mas aqui retorna {got}.",
                       where.line, where.col)

    def stmt_Pare(self, st: A.Pare) -> None:
        if self.ctx.loop_depth == 0:
            self.error("G209", "'pare' só pode ser usado dentro de um laço (enquanto, para, repita).", st.line, st.col, 4)

    def stmt_Continue(self, st: A.Continue) -> None:
        if self.ctx.loop_depth == 0:
            self.error("G209", "'continue' só pode ser usado dentro de um laço (enquanto, para, repita).", st.line, st.col, 8)

    def stmt_Lance(self, st: A.Lance) -> None:
        self.visit_expr(st.value)

    def stmt_ExprStmt(self, st: A.ExprStmt) -> None:
        self.visit_expr(st.expr)

    # ------------------------------------------------------------ expressões

    def visit_expr(self, e):
        return getattr(self, "expr_" + type(e).__name__)(e)

    def expr_Literal(self, e: A.Literal):
        return T.type_of_python_value(e.value)

    def expr_TextoInterpolado(self, e: A.TextoInterpolado):
        for p in e.parts:
            if not isinstance(p, str):
                self.visit_expr(p)
        return T.T_TEXTO

    def expr_Nome(self, e: A.Nome):
        sym = self.resolve(e)
        return sym.static_type() if sym is not None else None

    def expr_ListaLit(self, e: A.ListaLit):
        for x in e.elements:
            self.visit_expr(x)
        return T.T_LISTA

    def expr_MapaLit(self, e: A.MapaLit):
        seen = {}
        for k, v in e.pairs:
            kt = self.visit_expr(k)
            self.visit_expr(v)
            if kt is not None and not (kt - {"lista", "mapa", "função"}):
                self.error("G212", f"{describe_types(T.spec_tuple(kt)).capitalize()} não pode ser usado como chave de mapa.",
                           k.line, k.col, 1, "Use textos, números, booleanos ou nulo como chaves.")
            if isinstance(k, A.Literal):
                ident = (type(k.value).__name__, k.value)
                if ident in seen:
                    self.warn("A204", "Esta chave aparece mais de uma vez no mesmo mapa; vale o último valor.", k.line, k.col)
                seen[ident] = True
        return T.T_MAPA

    def binop_type(self, op, lt, rt, node):
        rules = T.BINOP_RULES[op]
        if lt is None or rt is None:
            for side in (lt, rt):
                if side is None:
                    continue
                pos_left = side is lt
                ok = any(((a, b) if pos_left else (b, a)) in rules for a in side for b in T.ALL)
                if not ok:
                    a = sorted(side)[0]
                    msg = f"O operador '{op}' não pode ser usado com {describe_types((a,))}."
                    self.error("G212", msg, node.line, node.col)
                    return None
            return T.T_DEC if op == "/" else None
        result: set[str] = set()
        for a in lt:
            for b in rt:
                r = rules.get((a, b))
                if r:
                    result |= r
        if not result:
            a, b = sorted(lt)[0], sorted(rt)[0]
            msg, suggestion = binop_message(op, a, b)
            self.error("G212", msg, node.line, node.col, 1, suggestion)
            return None
        return frozenset(result)

    def expr_Binario(self, e: A.Binario):
        lt = self.visit_expr(e.left)
        rt = self.visit_expr(e.right)
        return self.binop_type(e.op, lt, rt, e)

    def expr_Comparacao(self, e: A.Comparacao):
        types = [self.visit_expr(x) for x in e.operands]
        for i, op in enumerate(e.ops):
            a, b = types[i], types[i + 1]
            line, col = e.op_positions[i]
            if op in ("<", "<=", ">", ">=") and a is not None and b is not None:
                if not any((x, y) in T.ORDER_PAIRS for x in a for y in b):
                    x, y = sorted(a)[0], sorted(b)[0]
                    self.error("G212", f"Não é possível comparar {describe_types((x,))} com {describe_types((y,))} usando '{op}'.",
                               line, col, len(op))
            elif op == "em" and b is not None:
                if not (b & T.T_INDEXABLE):
                    self.error("G212", f"O operador 'em' precisa de uma lista, um texto ou um mapa à direita, mas recebeu "
                                       f"{describe_types(T.spec_tuple(b))}.", line, col, 2)
                elif b == T.T_TEXTO and a is not None and "texto" not in a:
                    self.error("G212", "Para procurar dentro de um texto com 'em', o valor procurado deve ser um texto.",
                               line, col, 2)
        return T.T_BOOL

    def expr_Logico(self, e: A.Logico):
        for side in (e.left, e.right):
            t = self.visit_expr(side)
            if t is not None and "booleano" not in t:
                self.error("G215", f"O operador '{e.op}' exige valores booleanos, mas recebeu {describe_types(T.spec_tuple(t))}.",
                           side.line, side.col, 1, "Combine comparações, por exemplo: x > 0 e x < 10")
        return T.T_BOOL

    def expr_Unario(self, e: A.Unario):
        t = self.visit_expr(e.operand)
        if e.op == "não":
            if t is not None and "booleano" not in t:
                self.error("G215", f"O operador 'não' exige um booleano, mas recebeu {describe_types(T.spec_tuple(t))}.",
                           e.line, e.col, 3)
            return T.T_BOOL
        if t is not None:
            if not (t & T.T_NUM):
                self.error("G212", f"Não é possível aplicar '{e.op}' a {describe_types(T.spec_tuple(t))}.", e.line, e.col)
                return None
            return t & T.T_NUM
        return None

    def check_call(self, sym: Symbol, e: A.Chamada, arg_types, kw_types):
        """Confere quantidade, nomes e tipos dos argumentos de uma chamada a função conhecida."""
        callee = e.callee
        names, keys, specs = sym.param_names, sym.param_keys or [], sym.params
        total = len(names)
        n = len(e.args)
        what = "O registro" if sym.kind == "registro" else "A função"
        line, col = callee.line, callee.col
        length = getattr(callee, "length", 1)
        form = f"Forma correta: {sym.name}({', '.join(names)})"
        if n > total:
            plural = "argumento" if total == 1 else "argumentos"
            limite = "" if sym.required == total else "no máximo "
            self.error("G210", f"{what} '{sym.name}' espera {limite}{total} {plural}, mas recebeu {n}.", line, col, length, form)
            return
        given = set(range(n))
        typed = list(zip(range(n), arg_types, e.args))
        for kw, kt in zip(e.kwargs, kw_types):
            if kw.key not in keys:
                close = difflib.get_close_matches(kw.key, keys, n=1, cutoff=0.6)
                hint = f"Você quis dizer '{names[keys.index(close[0])]}'?" if close else form
                self.error("G223", f"'{sym.name}' não tem o parâmetro '{kw.name}'.", kw.line, kw.col, len(kw.name), hint)
                continue
            idx = keys.index(kw.key)
            if idx in given:
                self.error("G223", f"O parâmetro '{names[idx]}' recebeu valor duas vezes (pela posição e pelo nome).",
                           kw.line, kw.col, len(kw.name))
                continue
            given.add(idx)
            typed.append((idx, kt, kw.value))
        missing = [names[i] for i in range(total) if i not in given and i < sym.required]
        if missing:
            lista = ", ".join(f"'{m}'" for m in missing)
            self.error("G210", f"Na chamada de '{sym.name}', falta{'m' if len(missing) > 1 else ''} o{'s' if len(missing) > 1 else ''} "
                               f"argumento{'s' if len(missing) > 1 else ''} {lista}.", line, col, length, form)
        for idx, at, node in typed:
            pt = specs[idx] if idx < len(specs) else None
            if pt is not None and not T.compatible(at, pt):
                self.error("G213", f"O argumento '{names[idx]}' de '{sym.name}' deve ser {describe_spec(T.spec_tuple(pt))}, "
                                   f"mas é {describe_types(T.spec_tuple(at))}.", node.line, node.col)

    def _callee_symbol(self, callee):
        """Símbolo de quem está sendo chamado, quando conhecido em compilação."""
        if isinstance(callee, A.Nome):
            sym = self.resolve(callee, for_call=True)
            return sym, (sym.static_type() if sym is not None else None)
        if isinstance(callee, A.Campo):
            ct = self.expr_Campo(callee)
            sym = getattr(callee, "member_sym", None)
            if sym is not None:
                return sym, ct
            rec = self.single_record(getattr(callee, "obj_static", None))
            if rec is not None and rec.methods and canonical(callee.name) in rec.methods:
                return rec.methods[canonical(callee.name)], T.T_FUNC
            return None, ct
        return None, self.visit_expr(callee)

    def expr_Chamada(self, e: A.Chamada):
        callee = e.callee
        sym, ct = self._callee_symbol(callee)
        arg_types = [self.visit_expr(a) for a in e.args]
        kw_types = [self.visit_expr(k.value) for k in e.kwargs]
        n = len(e.args)
        if sym is not None:
            if sym.kind in ("função", "registro") and sym.params is not None:
                self.check_call(sym, e, arg_types, kw_types)
                return sym.ret
            if sym.native is not None and e.kwargs:
                self.error("G223", f"A função interna '{sym.native.name}' não aceita argumentos nomeados.",
                           e.kwargs[0].line, e.kwargs[0].col, len(e.kwargs[0].name), f"Forma de uso: {sym.native.signature}")
                return T.from_names(sym.native.returns)
            if sym.native is not None:
                nf = sym.native
                if n < nf.min_args or (nf.max_args is not None and n > nf.max_args):
                    if nf.max_args is None:
                        expected = f"pelo menos {nf.min_args}"
                    elif nf.min_args == nf.max_args:
                        expected = str(nf.min_args)
                    else:
                        expected = f"de {nf.min_args} a {nf.max_args}"
                    self.error("G210", f"A função interna '{nf.name}' espera {expected} argumento(s), mas recebeu {n}.",
                               callee.line, callee.col, callee.length, f"Forma de uso: {nf.signature}")
                return T.from_names(nf.returns)
        if ct is not None and not (ct & {"função", "tipo"}) and ct <= T.ALL:
            self.error("G217", f"Este valor é {describe_types(T.spec_tuple(ct))} e não pode ser chamado como uma função.",
                       callee.line, callee.col, getattr(callee, "length", 1))
        return None

    def expr_Indice(self, e: A.Indice):
        ot = self.visit_expr(e.obj)
        it = self.visit_expr(e.index)
        if ot is not None:
            if not (ot & T.T_INDEXABLE):
                self.error("G219", f"Não é possível acessar posições de {describe_types(T.spec_tuple(ot))}.", e.line, e.col,
                           suggestion="O acesso com [ ] funciona em listas, textos e mapas.")
                return None
            if ot <= {"lista", "texto"} and it is not None and "inteiro" not in it:
                self.error("G219", f"A posição deve ser um inteiro, mas é {describe_types(T.spec_tuple(it))}.",
                           e.index.line, e.index.col)
            if ot == T.T_TEXTO:
                return T.T_TEXTO
        return None

    def _unknown_field(self, rec: Symbol, e) -> None:
        options = [f[0] for f in rec.fields] + [m.name for m in (rec.methods or {}).values()]
        close = difflib.get_close_matches(canonical(e.name), [canonical(o) for o in options], n=1, cutoff=0.6)
        hint = None
        if close:
            hint = f"Você quis dizer '{options[[canonical(o) for o in options].index(close[0])]}'?"
        else:
            hint = f"Campos de {rec.name}: " + ", ".join(f[0] for f in rec.fields)
        self.error("G222", f"O registro {rec.name} não possui o campo '{e.name}'.", e.line, e.col, len(e.name), hint)

    def expr_Campo(self, e: A.Campo):
        if isinstance(e.obj, A.Nome):
            osym = self.resolve(e.obj)
            ot = osym.static_type() if osym is not None else None
            e.obj_static = ot
            if osym is not None and osym.kind == "módulo" and osym.module is not None:
                entry = osym.module
                exp = entry.exports.get(canonical(e.name))
                if exp is None:
                    close = difflib.get_close_matches(canonical(e.name), list(entry.exports), n=1, cutoff=0.6)
                    hint = f"Você quis dizer '{entry.exports[close[0]].name}'?" if close else (
                        "Nomes exportados: " + (", ".join(sorted(x.name for x in entry.exports.values())) or "nenhum"))
                    self.error("G221", f"O módulo '{entry.name}' não exporta '{e.name}'.", e.line, e.col, len(e.name), hint)
                    return None
                e.member_sym = exp
                return exp.static_type()
        else:
            ot = self.visit_expr(e.obj)
            e.obj_static = ot
        e.static = None
        rec = self.single_record(ot)
        if rec is not None and rec.fields is not None:
            key = canonical(e.name)
            for fname, fkey, fspec, _ in rec.fields:
                if fkey == key:
                    e.static = fspec
                    return fspec
            if rec.methods and key in rec.methods:
                e.static = T.T_FUNC
                return T.T_FUNC
            self._unknown_field(rec, e)
            return None
        if ot is not None and ot <= T.NO_FIELDS:
            self.error("G219", f"O acesso com '.' (campo '{e.name}') só funciona em mapas e registros, mas o valor é "
                               f"{describe_types(T.spec_tuple(ot))}.", e.line, e.col, len(e.name),
                       "Para aplicar uma função ao valor, use a forma função(valor), como tamanho(lista).")
        return None

    def expr_SeExpr(self, e: A.SeExpr):
        self.check_condition(self.visit_expr(e.cond), e.cond, "da expressão 'se'")
        a = self.visit_expr(e.then)
        b = self.visit_expr(e.otherwise)
        if a is None or b is None:
            return None
        return a | b

    def expr_FuncaoAnonima(self, e: A.FuncaoAnonima):
        e.param_specs = [self.resolve_type(p.type) for p in e.params]
        e.ret_spec = self.resolve_type(e.ret)
        self._check_param_order(e.params, "parâmetro")
        self.scope.pending.append((e, self.scope))
        return T.T_FUNC
