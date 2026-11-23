"""Geração de bytecode a partir da AST anotada pelo analisador semântico."""

from __future__ import annotations

from . import ast as A
from .bytecode import CallInfo, CodeObject, Module, Op, RecordInfo, TypeCheck
from .typesys import spec_tuple

BINARY_OPS = {
    "+": Op.ADD, "-": Op.SUB, "*": Op.MUL, "/": Op.DIV, "//": Op.IDIV, "%": Op.MOD, "^": Op.POW,
}
COMPARE_OPS = {
    "==": Op.EQ, "!=": Op.NE, "<": Op.LT, "<=": Op.LE, ">": Op.GT, ">=": Op.GE, "em": Op.IN,
}


class LoopInfo:
    __slots__ = ("continue_target", "try_depth", "breaks")

    def __init__(self, continue_target: int, try_depth: int) -> None:
        self.continue_target = continue_target
        self.try_depth = try_depth
        self.breaks: list[int] = []


class FunctionBuilder:
    def __init__(self, ctx, name: str, filename: str) -> None:
        self.ctx = ctx
        self.co = CodeObject(name, filename)
        self.const_index: dict = {}
        self.name_index: dict[str, int] = {}
        self.loops: list[LoopInfo] = []
        self.try_depth = 0
        self.pos = (1, 1)

    def emit(self, op: Op, arg: int = 0, node=None) -> int:
        at = len(self.co.code)
        self.co.code.append(int(op))
        self.co.code.append(arg)
        self.co.positions.append((node.line, node.col) if node is not None else self.pos)
        return at

    def here(self) -> int:
        return len(self.co.code)

    def patch(self, at: int, target: int | None = None) -> None:
        self.co.code[at + 1] = self.here() if target is None else target

    def const(self, value) -> int:
        t = type(value)
        if t is CodeObject or t is TypeCheck or t is RecordInfo or t is CallInfo:
            key = ("obj", id(value))
        elif t is float:
            key = ("float", repr(value))
        else:
            key = (t.__name__, value)
        idx = self.const_index.get(key)
        if idx is None:
            idx = len(self.co.consts)
            self.co.consts.append(value)
            self.const_index[key] = idx
        return idx

    def name(self, text: str) -> int:
        idx = self.name_index.get(text)
        if idx is None:
            idx = len(self.co.names)
            self.co.names.append(text)
            self.name_index[text] = idx
        return idx

    def temp(self) -> int:
        return self.ctx.new_slot("<temporária>")

    def finish(self) -> CodeObject:
        self.co.nlocals = self.ctx.nlocals
        self.co.local_names = list(self.ctx.local_names)
        return self.co


class CodeGen:
    def __init__(self, filename: str, repl: bool = False) -> None:
        self.filename = filename
        self.repl = repl
        self.fb: FunctionBuilder | None = None

    # ------------------------------------------------------------ entrada

    def compile_program(self, prog: A.Programa) -> Module:
        fb = FunctionBuilder(prog.ctx, "<programa>", self.filename)
        self.fb = fb
        if self.repl:
            for st in prog.body.stmts:
                if isinstance(st, A.ExprStmt):
                    st.repl_print = True
        self.block(prog.body)
        fb.emit(Op.CONST, fb.const(None))
        fb.emit(Op.RETURN, 1)
        return Module(fb.finish(), prog.name, self.filename)

    def compile_function(self, node, name: str) -> CodeObject:
        outer = self.fb
        fb = FunctionBuilder(node.ctx, name, self.filename)
        fb.pos = (node.line, node.col)
        co = fb.co
        co.params = tuple(p.name for p in node.params)
        co.param_types = tuple(spec_tuple(s) for s in node.param_specs)
        co.return_type = spec_tuple(node.ret_spec) if node.ret is not None else None
        co.free_sources = [src for _, src in node.ctx.freevars]
        co.free_names = [sym.name for sym, _ in node.ctx.freevars]
        co.defaults = tuple(p.default is not None for p in node.params)
        self.fb = fb
        self.block(node.body, lambda: self.emit_defaults(node.params, node.param_specs))
        fb.emit(Op.CONST, fb.const(None), node)
        fb.emit(Op.RETURN, 1, node)
        self.fb = outer
        return fb.finish()

    def emit_defaults(self, params, specs) -> None:
        """Preenche os parâmetros não informados com seus valores padrão (avaliados a cada chamada)."""
        fb = self.fb
        for p, spec in zip(params, specs):
            if p.default is None:
                continue
            fb.emit(Op.ARG_MISSING, p.sym.slot, p)
            skip = fb.emit(Op.JUMP_IF_FALSE, 0, p)
            self.expr(p.default)
            if spec is not None:
                check = TypeCheck(spec_tuple(spec), f"o parâmetro '{p.name}'")
                fb.emit(Op.CHECK_TYPE, fb.const(check), p.default)
            self.store_decl(p.sym, p)
            fb.patch(skip)

    def compile_constructor(self, node: A.DefRegistro) -> CodeObject:
        outer = self.fb
        fb = FunctionBuilder(node.ctor_ctx, node.name, self.filename)
        fb.pos = (node.line, node.col)
        co = fb.co
        co.params = tuple(f.name for f in node.fields)
        co.param_types = tuple(spec_tuple(f.spec) for f in node.fields)
        co.defaults = tuple(f.default is not None for f in node.fields)
        co.free_sources = [src for _, src in node.ctor_ctx.freevars]
        co.free_names = [sym.name for sym, _ in node.ctor_ctx.freevars]
        self.fb = fb
        for sym in node.ctor_scope.declared:
            if sym.captured:
                fb.emit(Op.BOX_LOCAL, sym.slot, node)
        self.emit_defaults(node.fields, [f.spec for f in node.fields])
        fb.emit(Op.LOAD_GLOBAL, fb.name(node.name), node)
        for f in node.fields:
            fb.emit(Op.LOAD_CELL if f.sym.captured else Op.LOAD_LOCAL, f.sym.slot, node)
        fb.emit(Op.NEW_RECORD, len(node.fields), node)
        fb.emit(Op.RETURN, 0, node)
        self.fb = outer
        return fb.finish()

    def record_def(self, st: A.DefRegistro) -> None:
        fb = self.fb
        fb.emit(Op.MAKE_FUNCTION, fb.const(self.compile_constructor(st)), st)
        for m in st.methods:
            fb.emit(Op.MAKE_FUNCTION, fb.const(self.compile_function(m, f"{st.name}.{m.name}")), m)
        info = RecordInfo(st.name, tuple(f.name for f in st.fields), tuple(spec_tuple(f.spec) for f in st.fields),
                          tuple(m.name for m in st.methods))
        fb.emit(Op.MAKE_RECORD_TYPE, fb.const(info), st)
        self.store_decl(st.sym, st)

    # ------------------------------------------------------------ variáveis

    def load(self, res, node) -> None:
        fb = self.fb
        kind = res[0]
        if kind == "global":
            fb.emit(Op.LOAD_GLOBAL, fb.name(node.name), node)
        elif kind == "local":
            sym = res[1]
            fb.emit(Op.LOAD_CELL if sym.captured else Op.LOAD_LOCAL, sym.slot, node)
        elif kind == "free":
            fb.emit(Op.LOAD_FREE, res[1], node)
        else:  # pragma: no cover - análise semântica garante resolução
            raise AssertionError(f"nome não resolvido: {node.name}")

    def store_res(self, res, node) -> None:
        fb = self.fb
        kind = res[0]
        if kind == "global":
            fb.emit(Op.STORE_GLOBAL, fb.name(node.name), node)
        elif kind == "local":
            sym = res[1]
            fb.emit(Op.STORE_CELL if sym.captured else Op.STORE_LOCAL, sym.slot, node)
        elif kind == "free":
            fb.emit(Op.STORE_FREE, res[1], node)
        else:  # pragma: no cover
            raise AssertionError(f"nome não resolvido: {node.name}")

    def store_decl(self, sym, node) -> None:
        fb = self.fb
        if sym.is_global:
            fb.emit(Op.DEFINE_GLOBAL, fb.name(sym.name), node)
        elif sym.captured:
            fb.emit(Op.STORE_CELL, sym.slot, node)
        else:
            fb.emit(Op.STORE_LOCAL, sym.slot, node)

    # ------------------------------------------------------------ blocos

    def block(self, blk: A.Block, prologue=None) -> None:
        fb = self.fb
        for sym in blk.scope.declared:
            if sym.is_global or not sym.captured:
                continue
            fb.emit(Op.BOX_LOCAL if sym.kind == "parâmetro" else Op.MAKE_CELL, sym.slot, blk)
        if prologue is not None:
            prologue()
        for st in blk.stmts:
            if isinstance(st, A.DefRegistro):
                self.record_def(st)
        for st in blk.stmts:
            if isinstance(st, A.DefFuncao):
                self.function_def(st)
        for st in blk.stmts:
            if not isinstance(st, (A.DefFuncao, A.DefRegistro)):
                fb.pos = (st.line, st.col)
                getattr(self, "s_" + type(st).__name__)(st)

    def function_def(self, st: A.DefFuncao) -> None:
        co = self.compile_function(st, st.name)
        self.fb.emit(Op.MAKE_FUNCTION, self.fb.const(co), st)
        self.store_decl(st.sym, st)

    # ------------------------------------------------------------ instruções

    def s_Defina(self, st: A.Defina) -> None:
        if isinstance(st.value, A.FuncaoAnonima) and st.value.name == "<anônima>":
            st.value.name = st.name
        self.expr(st.value)
        if st.spec is not None:
            what = "a constante" if st.constant else "a variável"
            check = TypeCheck(spec_tuple(st.spec), f"{what} '{st.name}'")
            self.fb.emit(Op.CHECK_TYPE, self.fb.const(check), st.value)
        self.store_decl(st.sym, st)

    def s_Atribuicao(self, st: A.Atribuicao) -> None:
        fb = self.fb
        t = st.target
        binop = BINARY_OPS[st.op[0]] if st.op != "=" else None
        if isinstance(t, A.Nome):
            if binop is not None:
                self.load(t.res, t)
                self.expr(st.value)
                fb.emit(binop, 0, st)
            else:
                self.expr(st.value)
            if st.spec is not None:
                check = TypeCheck(spec_tuple(st.spec), f"a variável '{t.name}'")
                fb.emit(Op.CHECK_TYPE, fb.const(check), st.value)
            self.store_res(t.res, t)
        elif isinstance(t, A.Indice):
            if binop is None:
                self.expr(t.obj)
                self.expr(t.index)
                self.expr(st.value)
            else:
                a, b = fb.temp(), fb.temp()
                self.expr(t.obj)
                fb.emit(Op.STORE_LOCAL, a)
                self.expr(t.index)
                fb.emit(Op.STORE_LOCAL, b)
                fb.emit(Op.LOAD_LOCAL, a)
                fb.emit(Op.LOAD_LOCAL, b)
                fb.emit(Op.LOAD_LOCAL, a)
                fb.emit(Op.LOAD_LOCAL, b)
                fb.emit(Op.INDEX, 0, t)
                self.expr(st.value)
                fb.emit(binop, 0, st)
            fb.emit(Op.STORE_INDEX, 0, t)
        else:  # Campo
            name = fb.name(t.name)
            if binop is None:
                self.expr(t.obj)
                self.expr(st.value)
            else:
                a = fb.temp()
                self.expr(t.obj)
                fb.emit(Op.STORE_LOCAL, a)
                fb.emit(Op.LOAD_LOCAL, a)
                fb.emit(Op.LOAD_LOCAL, a)
                fb.emit(Op.GET_FIELD, name, t)
                self.expr(st.value)
                fb.emit(binop, 0, st)
            fb.emit(Op.SET_FIELD, name, t)

    def s_Se(self, st: A.Se) -> None:
        fb = self.fb
        ends = []
        last = len(st.branches) - 1
        for i, (cond, blk) in enumerate(st.branches):
            self.expr(cond)
            jf = fb.emit(Op.JUMP_IF_FALSE, 0, cond)
            self.block(blk)
            if i < last or st.else_block is not None:
                ends.append(fb.emit(Op.JUMP))
            fb.patch(jf)
        if st.else_block is not None:
            self.block(st.else_block)
        for j in ends:
            fb.patch(j)

    def _loop_body(self, loop: LoopInfo, body: A.Block, prologue=None) -> None:
        self.fb.loops.append(loop)
        self.block(body, prologue)
        self.fb.loops.pop()

    def s_Enquanto(self, st: A.Enquanto) -> None:
        fb = self.fb
        start = fb.here()
        self.expr(st.cond)
        jf = fb.emit(Op.JUMP_IF_FALSE, 0, st.cond)
        loop = LoopInfo(start, fb.try_depth)
        self._loop_body(loop, st.body)
        fb.emit(Op.JUMP, start)
        fb.patch(jf)
        for j in loop.breaks:
            fb.patch(j)

    def _iterator_loop(self, st, two: bool, prologue) -> None:
        fb = self.fb
        start = fb.here()
        fi = fb.emit(Op.FOR_ITER2 if two else Op.FOR_ITER, 0, st)
        loop = LoopInfo(start, fb.try_depth)
        self._loop_body(loop, st.body, prologue)
        fb.emit(Op.JUMP, start)
        if loop.breaks:
            for j in loop.breaks:
                fb.patch(j)
            fb.emit(Op.POP)  # descarta o iterador ao sair com 'pare'
        fb.patch(fi)

    def s_ParaCada(self, st: A.ParaCada) -> None:
        fb = self.fb
        self.expr(st.iterable)
        two = st.var2 is not None
        fb.emit(Op.ITER_PREPARE, 1 if two else 0, st.iterable)

        def prologue():
            if two:
                self.store_decl(st.var2.sym, st.var2)
            self.store_decl(st.var1.sym, st.var1)

        self._iterator_loop(st, two, prologue)

    def s_ParaIntervalo(self, st: A.ParaIntervalo) -> None:
        fb = self.fb
        self.expr(st.start)
        self.expr(st.end)
        if st.step is not None:
            self.expr(st.step)
        fb.emit(Op.RANGE_PREPARE, 1 if st.step is not None else 0, st)
        self._iterator_loop(st, False, lambda: self.store_decl(st.var.sym, st.var))

    def s_Repita(self, st: A.Repita) -> None:
        self.expr(st.count)
        self.fb.emit(Op.REPEAT_PREPARE, 0, st.count)
        self._iterator_loop(st, False, lambda: self.fb.emit(Op.POP))

    def s_Tente(self, st: A.Tente) -> None:
        fb = self.fb
        setup = fb.emit(Op.SETUP_TRY, 0, st)
        fb.try_depth += 1
        self.block(st.body)
        fb.try_depth -= 1
        fb.emit(Op.POP_TRY)
        jump = fb.emit(Op.JUMP)
        fb.patch(setup)

        def prologue():
            if st.err_var is not None:
                self.store_decl(st.err_var.sym, st.err_var)
            else:
                fb.emit(Op.POP)

        self.block(st.handler, prologue)
        fb.patch(jump)

    def s_Importe(self, st: A.Importe) -> None:
        fb = self.fb
        fb.emit(Op.IMPORT_MODULE, st.module_index, st)
        if st.alias is not None:
            self.store_decl(st.alias.sym, st.alias)
            return
        for v in st.names:
            fb.emit(Op.DUP)
            fb.emit(Op.GET_FIELD, fb.name(v.name), v)
            self.store_decl(v.sym, v)
        fb.emit(Op.POP)

    def s_Mostre(self, st: A.Mostre) -> None:
        for v in st.values:
            self.expr(v)
        self.fb.emit(Op.PRINT, len(st.values), st)

    def s_Retorne(self, st: A.Retorne) -> None:
        if st.value is not None:
            self.expr(st.value)
        else:
            self.fb.emit(Op.CONST, self.fb.const(None), st)
        self.fb.emit(Op.RETURN, 0, st)

    def _unwind_tries(self, loop: LoopInfo) -> None:
        for _ in range(self.fb.try_depth - loop.try_depth):
            self.fb.emit(Op.POP_TRY)

    def s_Pare(self, st: A.Pare) -> None:
        loop = self.fb.loops[-1]
        self._unwind_tries(loop)
        loop.breaks.append(self.fb.emit(Op.JUMP, 0, st))

    def s_Continue(self, st: A.Continue) -> None:
        loop = self.fb.loops[-1]
        self._unwind_tries(loop)
        self.fb.emit(Op.JUMP, loop.continue_target, st)

    def s_Lance(self, st: A.Lance) -> None:
        self.expr(st.value)
        self.fb.emit(Op.RAISE, 0, st)

    def s_ExprStmt(self, st: A.ExprStmt) -> None:
        self.expr(st.expr)
        self.fb.emit(Op.PRINT_REPL if getattr(st, "repl_print", False) else Op.POP, 0, st)

    # ------------------------------------------------------------ expressões

    def expr(self, e) -> None:
        getattr(self, "e_" + type(e).__name__)(e)

    def e_Literal(self, e: A.Literal) -> None:
        self.fb.emit(Op.CONST, self.fb.const(e.value), e)

    def e_TextoInterpolado(self, e: A.TextoInterpolado) -> None:
        for p in e.parts:
            if isinstance(p, str):
                self.fb.emit(Op.CONST, self.fb.const(p), e)
            else:
                self.expr(p)
        self.fb.emit(Op.BUILD_STRING, len(e.parts), e)

    def e_Nome(self, e: A.Nome) -> None:
        self.load(e.res, e)

    def e_ListaLit(self, e: A.ListaLit) -> None:
        for x in e.elements:
            self.expr(x)
        self.fb.emit(Op.BUILD_LIST, len(e.elements), e)

    def e_MapaLit(self, e: A.MapaLit) -> None:
        for k, v in e.pairs:
            self.expr(k)
            self.expr(v)
        self.fb.emit(Op.BUILD_MAP, len(e.pairs), e)

    def e_Binario(self, e: A.Binario) -> None:
        self.expr(e.left)
        self.expr(e.right)
        self.fb.emit(BINARY_OPS[e.op], 0, e)

    def e_Unario(self, e: A.Unario) -> None:
        self.expr(e.operand)
        op = {"-": Op.NEG, "+": Op.POS, "não": Op.NOT}[e.op]
        self.fb.emit(op, 0, e)

    def e_Logico(self, e: A.Logico) -> None:
        fb = self.fb
        self.expr(e.left)
        jump = fb.emit(Op.JUMP_IF_FALSE_KEEP if e.op == "e" else Op.JUMP_IF_TRUE_KEEP, 0, e.left)
        self.expr(e.right)
        fb.emit(Op.CHECK_BOOL, 1 if e.op == "e" else 2, e.right)
        fb.patch(jump)

    def e_Comparacao(self, e: A.Comparacao) -> None:
        fb = self.fb

        class _Pos:
            __slots__ = ("line", "col")

            def __init__(self, line, col):
                self.line, self.col = line, col

        self.expr(e.operands[0])
        ends = []
        last = len(e.ops) - 1
        for i, op in enumerate(e.ops):
            self.expr(e.operands[i + 1])
            pos = _Pos(*e.op_positions[i])
            if i < last:
                tmp = fb.temp()
                fb.emit(Op.DUP)
                fb.emit(Op.STORE_LOCAL, tmp)
                fb.emit(COMPARE_OPS[op], 0, pos)
                ends.append(fb.emit(Op.JUMP_IF_FALSE_KEEP))
                fb.emit(Op.LOAD_LOCAL, tmp)
            else:
                fb.emit(COMPARE_OPS[op], 0, pos)
        for j in ends:
            fb.patch(j)

    def e_Chamada(self, e: A.Chamada) -> None:
        self.expr(e.callee)
        for a in e.args:
            self.expr(a)
        if e.kwargs:
            for k in e.kwargs:
                self.expr(k.value)
            info = CallInfo(len(e.args), tuple(k.name for k in e.kwargs))
            self.fb.emit(Op.CALL_KW, self.fb.const(info), e)
            return
        self.fb.emit(Op.CALL, len(e.args), e)

    def e_SeExpr(self, e: A.SeExpr) -> None:
        fb = self.fb
        self.expr(e.cond)
        jf = fb.emit(Op.JUMP_IF_FALSE, 0, e.cond)
        self.expr(e.then)
        end = fb.emit(Op.JUMP)
        fb.patch(jf)
        self.expr(e.otherwise)
        fb.patch(end)

    def e_Indice(self, e: A.Indice) -> None:
        self.expr(e.obj)
        self.expr(e.index)
        self.fb.emit(Op.INDEX, 0, e)

    def e_Campo(self, e: A.Campo) -> None:
        self.expr(e.obj)
        self.fb.emit(Op.GET_FIELD, self.fb.name(e.name), e)

    def e_FuncaoAnonima(self, e: A.FuncaoAnonima) -> None:
        co = self.compile_function(e, e.name)
        self.fb.emit(Op.MAKE_FUNCTION, self.fb.const(co), e)
