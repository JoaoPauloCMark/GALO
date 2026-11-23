"""Máquina virtual da GALO.

Máquina de pilha com uma pilha explícita de quadros de chamada (`frames`).
Chamadas entre funções GALO NÃO usam a pilha do Python: a recursão é
limitada apenas por `max_frames` (padrão: 100 000 chamadas aninhadas) e pela
memória disponível.

Cada quadro (Frame) possui:
  * code     -> CodeObject em execução
  * pc       -> posição da próxima instrução
  * locals   -> variáveis locais (ou Cells, para variáveis capturadas)
  * stack    -> pilha de operandos
  * cells    -> variáveis capturadas pela closure
  * handlers -> tratadores de erro ativos (`tente`): (destino, altura da pilha)
"""

from __future__ import annotations

import os
import sys

from ..compiler.bytecode import Op
from ..names import canonical
from ..errors import GaloExit, GaloInternalError, GaloRuntimeError
from .builtins import builtin_namespace
from .matematica_exata import Aleatorio
from .values import (
    MISSING, UNSET, Cell, Closure, GaloMapa, GaloModulo, GaloRegistro, GaloTipoRegistro, MetodoLigado,
    NativeFunction, article, coerce, describe_spec, display,
    equals, field_get, field_set, index_get, index_set, make_iter, make_range, make_repeat, op_add,
    op_div, op_ge, op_gt, op_idiv, op_in, op_le, op_lt, op_mod, op_mul, op_neg, op_not, op_pos,
    op_pow, op_sub, repr_value, require_bool, type_name,
)

DEFAULT_MAX_FRAMES = 100_000

# Códigos de operação como inteiros simples (comparação mais rápida no laço principal).
NOP = int(Op.NOP); CONST = int(Op.CONST); POP = int(Op.POP); DUP = int(Op.DUP)
LOAD_LOCAL = int(Op.LOAD_LOCAL); STORE_LOCAL = int(Op.STORE_LOCAL)
LOAD_CELL = int(Op.LOAD_CELL); STORE_CELL = int(Op.STORE_CELL)
MAKE_CELL = int(Op.MAKE_CELL); BOX_LOCAL = int(Op.BOX_LOCAL)
LOAD_FREE = int(Op.LOAD_FREE); STORE_FREE = int(Op.STORE_FREE)
LOAD_GLOBAL = int(Op.LOAD_GLOBAL); STORE_GLOBAL = int(Op.STORE_GLOBAL); DEFINE_GLOBAL = int(Op.DEFINE_GLOBAL)
ADD = int(Op.ADD); SUB = int(Op.SUB); MUL = int(Op.MUL); DIV = int(Op.DIV); IDIV = int(Op.IDIV)
MOD = int(Op.MOD); POW = int(Op.POW); NEG = int(Op.NEG); POS = int(Op.POS); NOT = int(Op.NOT)
EQ = int(Op.EQ); NE = int(Op.NE); LT = int(Op.LT); LE = int(Op.LE); GT = int(Op.GT); GE = int(Op.GE); IN = int(Op.IN)
JUMP = int(Op.JUMP); JUMP_IF_FALSE = int(Op.JUMP_IF_FALSE)
JUMP_IF_FALSE_KEEP = int(Op.JUMP_IF_FALSE_KEEP); JUMP_IF_TRUE_KEEP = int(Op.JUMP_IF_TRUE_KEEP)
CHECK_BOOL = int(Op.CHECK_BOOL)
BUILD_LIST = int(Op.BUILD_LIST); BUILD_MAP = int(Op.BUILD_MAP); BUILD_STRING = int(Op.BUILD_STRING)
INDEX = int(Op.INDEX); STORE_INDEX = int(Op.STORE_INDEX); GET_FIELD = int(Op.GET_FIELD); SET_FIELD = int(Op.SET_FIELD)
CALL = int(Op.CALL); RETURN = int(Op.RETURN); MAKE_FUNCTION = int(Op.MAKE_FUNCTION)
PRINT = int(Op.PRINT); PRINT_REPL = int(Op.PRINT_REPL)
ITER_PREPARE = int(Op.ITER_PREPARE); RANGE_PREPARE = int(Op.RANGE_PREPARE); REPEAT_PREPARE = int(Op.REPEAT_PREPARE)
FOR_ITER = int(Op.FOR_ITER); FOR_ITER2 = int(Op.FOR_ITER2)
SETUP_TRY = int(Op.SETUP_TRY); POP_TRY = int(Op.POP_TRY); RAISE = int(Op.RAISE); CHECK_TYPE = int(Op.CHECK_TYPE)
IMPORT_MODULE = int(Op.IMPORT_MODULE); MAKE_RECORD_TYPE = int(Op.MAKE_RECORD_TYPE); NEW_RECORD = int(Op.NEW_RECORD)
CALL_KW = int(Op.CALL_KW); ARG_MISSING = int(Op.ARG_MISSING)

_LOGIC_NAMES = {1: "e", 2: "ou"}


class Frame:
    __slots__ = ("code", "pc", "locals", "stack", "cells", "handlers", "keys", "globals")

    def __init__(self, code, locs: list, cells: tuple, globals_: dict) -> None:
        self.code = code
        self.pc = 0
        self.locals = locs
        self.stack: list = []
        self.cells = cells
        self.handlers: list | None = None
        self.globals = globals_
        keys = code.keys
        if keys is None:
            keys = code.keys = [canonical(n) for n in code.names]
        self.keys = keys


class VM:
    def __init__(self, out=None, input_fn=None, args=(), max_frames: int = DEFAULT_MAX_FRAMES) -> None:
        if hasattr(sys, "set_int_max_str_digits"):
            sys.set_int_max_str_digits(0)  # inteiros grandes podem ser mostrados por inteiro
        self.out = out if out is not None else sys.stdout
        self.input_fn = input_fn if input_fn is not None else input
        self.program_args = [str(a) for a in args]
        self.max_frames = max_frames
        self.globals: dict = {}
        self.global_names: dict[str, str] = {}
        self.builtins: dict = builtin_namespace()
        self.frames: list[Frame] = []
        self.random = Aleatorio()
        self.module_table: list = []
        self.loaded_modules: dict[str, GaloModulo] = {}
        # Pasta usada para resolver caminhos relativos (arquivos, banco de dados, modelos):
        # a pasta do programa principal quando executado pela CLI.
        self.base_dir = os.getcwd()

    def resolve_path(self, path: str) -> str:
        return path if os.path.isabs(path) else os.path.join(self.base_dir, path)

    # ------------------------------------------------------------ E/S

    def write(self, text: str) -> None:
        self.out.write(text)

    def flush(self) -> None:
        try:
            self.out.flush()
        except Exception:
            pass

    def read_line(self, prompt: str):
        self.flush()
        try:
            return self.input_fn(prompt)
        except EOFError:
            return None

    # ------------------------------------------------------------ execução

    def run(self, module):
        self.module_table = list(getattr(module, "modules", []) or [])
        frame = Frame(module.code, [None] * module.code.nlocals, (), self.globals)
        stop = len(self.frames)
        self.frames.append(frame)
        try:
            return self._execute(stop)
        finally:
            del self.frames[stop:]
            self.flush()

    def call_value(self, fn, args: list, kwargs: dict | None = None):
        """Chama uma função GALO a partir de uma função interna (ex.: mapear, rotas do servidor)."""
        t = type(fn)
        if t is NativeFunction:
            if kwargs:
                raise GaloRuntimeError("G307", f"A função interna '{fn.name}' não aceita argumentos nomeados.")
            self._check_native_arity(fn, len(args))
            return fn.fn(self, *args)
        if t is MetodoLigado:
            return self.call_value(fn.funcao, [fn.receptor] + list(args), kwargs)
        if t is GaloTipoRegistro:
            return self.call_value(fn.ctor, args, kwargs)
        if t is Closure:
            args = list(args)
            if kwargs:
                args = self._bind_kwargs(fn, args, list(kwargs), list(kwargs.values()))
            frame = self._new_frame(fn, args)
            stop = len(self.frames)
            self.frames.append(frame)
            return self._execute(stop)
        raise GaloRuntimeError("G306", f"Tentou chamar {article(type_name(fn))} como se fosse uma função.")

    def _bind_kwargs(self, fn: Closure, args: list, names, values) -> list:
        co = fn.code
        params = co.params
        keys = [canonical(p) for p in params]
        if len(args) > len(params):
            raise GaloRuntimeError("G307", f"A função '{co.name}' espera no máximo {len(params)} argumentos, "
                                           f"mas recebeu {len(args)} sem nome.")
        bound = args + [UNSET] * (len(params) - len(args))
        for name, value in zip(names, values):
            key = canonical(name)
            if key not in keys:
                raise GaloRuntimeError("G307", f"A função '{co.name}' não tem o parâmetro '{name}'.",
                                       suggestion=f"Parâmetros: {', '.join(params)}")
            i = keys.index(key)
            if bound[i] is not UNSET:
                raise GaloRuntimeError("G307", f"O parâmetro '{params[i]}' recebeu valor duas vezes.")
            bound[i] = value
        defaults = co.defaults or (False,) * len(params)
        for i, v in enumerate(bound):
            if v is UNSET and not defaults[i]:
                raise GaloRuntimeError("G307", f"Falta o argumento '{params[i]}' na chamada de '{co.name}'.",
                                       suggestion=f"Forma correta: {co.name}({', '.join(params)})")
        return bound

    def _new_frame(self, fn: Closure, args: list) -> Frame:
        co = fn.code
        n = len(args)
        params = co.params
        nparams = len(params)
        if n != nparams:
            if n > nparams:
                plural = "argumento" if nparams == 1 else "argumentos"
                limite = "no máximo " if any(co.defaults) else ""
                raise GaloRuntimeError(
                    "G307", f"A função '{co.name}' espera {limite}{nparams} {plural}, mas recebeu {n}.",
                    suggestion=f"Forma correta: {co.name}({', '.join(params)})",
                )
            args.extend([UNSET] * (nparams - n))
            defaults = co.defaults or (False,) * nparams
            for i in range(nparams):
                if args[i] is UNSET and not defaults[i]:
                    raise GaloRuntimeError(
                        "G307", f"Falta o argumento '{params[i]}' na chamada de '{co.name}'.",
                        suggestion=f"Forma correta: {co.name}({', '.join(params)})",
                    )
        typed = co.typed
        if typed is None:
            typed = co.typed = any(spec is not None for spec in co.param_types)
        if typed:
            for i, spec in enumerate(co.param_types):
                if spec is not None and args[i] is not UNSET:
                    v = coerce(args[i], spec)
                    if v is MISSING:
                        raise GaloRuntimeError(
                            "G308", f"O parâmetro '{params[i]}' da função '{co.name}' espera {describe_spec(spec)}, "
                                    f"mas recebeu {article(type_name(args[i]))}.",
                        )
                    args[i] = v
        if len(self.frames) >= self.max_frames:
            raise GaloRuntimeError(
                "G311", f"Estouro de pilha: mais de {self.max_frames} chamadas de função aninhadas.",
                suggestion="Isso costuma indicar uma recursão sem caso base (a função chama a si mesma para sempre). "
                           "Verifique a condição de parada. Se a recursão profunda for intencional, aumente o limite "
                           "com a opção --limite-pilha.",
            )
        if co.nlocals > len(args):
            args.extend([None] * (co.nlocals - len(args)))
        return Frame(co, args, fn.cells, fn.globals)

    def _resolve_callable(self, fn, args: list):
        """Converte métodos ligados e tipos de registro na Closure que será executada."""
        t = type(fn)
        if t is MetodoLigado:
            return self._resolve_callable(fn.funcao, [fn.receptor] + args)
        if t is GaloTipoRegistro:
            return fn.ctor, args
        return fn, args

    def _import_module(self, index: int) -> GaloModulo:
        entry = self.module_table[index]
        m = self.loaded_modules.get(entry.name)
        if m is not None:
            return m
        m = GaloModulo(entry.name, entry.exports)
        self.loaded_modules[entry.name] = m
        frame = Frame(entry.code, [None] * entry.code.nlocals, (), m.globals)
        stop = len(self.frames)
        self.frames.append(frame)
        try:
            self._execute(stop)
        except BaseException:
            self.loaded_modules.pop(entry.name, None)
            raise
        m.ready = True
        return m

    @staticmethod
    def _check_native_arity(fn: NativeFunction, n: int) -> None:
        if n < fn.min_args or (fn.max_args is not None and n > fn.max_args):
            if fn.max_args is None:
                expected = f"pelo menos {fn.min_args}"
            elif fn.min_args == fn.max_args:
                expected = str(fn.min_args)
            else:
                expected = f"de {fn.min_args} a {fn.max_args}"
            raise GaloRuntimeError("G307", f"A função interna '{fn.name}' espera {expected} argumento(s), mas recebeu {n}.",
                                   suggestion=f"Forma de uso: {fn.signature}")

    def _undefined_global(self, name: str) -> GaloRuntimeError:
        return GaloRuntimeError(
            "G301", f"A variável \"{name}\" ainda não tem valor neste ponto da execução.",
            suggestion="Ela é definida mais adiante no programa. Defina-a antes de executar o código que a utiliza.",
        )

    def _user_error(self, value) -> GaloRuntimeError:
        if type(value) is GaloMapa:
            msg = value.get("mensagem")
            message = display(msg) if msg is not MISSING else repr_value(value)
        else:
            message = display(value)
        return GaloRuntimeError("G400", message, value=value)

    def _error_value(self, err: GaloRuntimeError):
        if type(err.value) is GaloMapa:
            return err.value
        m = GaloMapa.from_pairs([("mensagem", err.message), ("código", err.code), ("linha", err.line)])
        if err.value is not None:
            m.set("valor", err.value)
        return m

    @staticmethod
    def _line_of(f: Frame):
        idx = (f.pc - 2) // 2
        if 0 <= idx < len(f.code.positions):
            return f.code.positions[idx][0]
        return None

    def _attach(self, err: GaloRuntimeError) -> None:
        if not self.frames:
            return
        if err.line is None:
            f = self.frames[-1]
            idx = (f.pc - 2) // 2
            if 0 <= idx < len(f.code.positions):
                err.line, err.col = f.code.positions[idx]
            err.file = err.file or f.code.filename
        if not err.trace:
            err.trace = [(f.code.name, self._line_of(f)) for f in self.frames]

    def _unwind(self, err: GaloRuntimeError, stop: int) -> bool:
        frames = self.frames
        while len(frames) > stop:
            f = frames[-1]
            if f.handlers:
                target, depth = f.handlers.pop()
                del f.stack[depth:]
                f.stack.append(self._error_value(err))
                f.pc = target
                return True
            frames.pop()
        return False

    def _execute(self, stop: int):
        frames = self.frames
        builtins = self.builtins
        out_write = self.out.write
        while True:
            frame = frames[-1]
            globals_ = frame.globals
            co = frame.code
            code = co.code
            consts = co.consts
            stack = frame.stack
            locs = frame.locals
            push = stack.append
            pop = stack.pop
            pc = frame.pc
            try:
                while True:
                    op = code[pc]
                    arg = code[pc + 1]
                    pc += 2
                    if op == LOAD_LOCAL:
                        push(locs[arg])
                    elif op == CONST:
                        push(consts[arg])
                    elif op == STORE_LOCAL:
                        locs[arg] = pop()
                    elif op == LOAD_GLOBAL:
                        key = frame.keys[arg]
                        v = globals_.get(key, MISSING)
                        if v is MISSING:
                            v = builtins.get(key, MISSING)
                            if v is MISSING:
                                raise self._undefined_global(co.names[arg])
                        push(v)
                    elif op == JUMP_IF_FALSE:
                        v = pop()
                        if v is False:
                            pc = arg
                        elif v is not True:
                            require_bool(v)
                    elif op == JUMP:
                        pc = arg
                    elif op == FOR_ITER:
                        v = next(stack[-1], MISSING)
                        if v is MISSING:
                            pop()
                            pc = arg
                        else:
                            push(v)
                    elif op == STORE_GLOBAL:
                        key = frame.keys[arg]
                        if key not in globals_:
                            raise self._undefined_global(co.names[arg])
                        globals_[key] = pop()
                    elif op == ADD:
                        b = pop()
                        a = stack[-1]
                        if type(a) is int and type(b) is int:
                            stack[-1] = a + b
                        else:
                            stack[-1] = op_add(a, b)
                    elif op == SUB:
                        b = pop()
                        a = stack[-1]
                        if type(a) is int and type(b) is int:
                            stack[-1] = a - b
                        else:
                            stack[-1] = op_sub(a, b)
                    elif op == LT:
                        b = pop()
                        a = stack[-1]
                        stack[-1] = a < b if type(a) is int and type(b) is int else op_lt(a, b)
                    elif op == LE:
                        b = pop()
                        a = stack[-1]
                        stack[-1] = a <= b if type(a) is int and type(b) is int else op_le(a, b)
                    elif op == GT:
                        b = pop()
                        a = stack[-1]
                        stack[-1] = a > b if type(a) is int and type(b) is int else op_gt(a, b)
                    elif op == GE:
                        b = pop()
                        a = stack[-1]
                        stack[-1] = a >= b if type(a) is int and type(b) is int else op_ge(a, b)
                    elif op == EQ:
                        b = pop()
                        a = stack[-1]
                        ta = type(a)
                        stack[-1] = a == b if ta is type(b) and (ta is int or ta is str) else equals(a, b)
                    elif op == NE:
                        b = pop()
                        a = stack[-1]
                        ta = type(a)
                        stack[-1] = a != b if ta is type(b) and (ta is int or ta is str) else not equals(a, b)
                    elif op == CALL:
                        fn = stack[-arg - 1]
                        t = type(fn)
                        if t is MetodoLigado or t is GaloTipoRegistro:
                            args = stack[-arg:] if arg else []
                            del stack[-arg - 1:]
                            fn, args = self._resolve_callable(fn, args)
                            t = type(fn)
                            stack.append(fn)
                            stack.extend(args)
                            arg = len(args)
                        if t is Closure:
                            if arg:
                                args = stack[-arg:]
                                del stack[-arg - 1:]
                            else:
                                args = []
                                pop()
                            new_frame = self._new_frame(fn, args)
                            frame.pc = pc
                            frames.append(new_frame)
                            break
                        if t is NativeFunction:
                            args = stack[-arg:] if arg else []
                            del stack[-arg - 1:]
                            self._check_native_arity(fn, arg)
                            frame.pc = pc
                            push(fn.fn(self, *args))
                        else:
                            raise GaloRuntimeError(
                                "G306", f"Tentou chamar {article(type_name(fn))} como se fosse uma função.",
                                suggestion="Só funções podem ser chamadas com parênteses: nome(argumentos).",
                            )
                    elif op == RETURN:
                        v = pop()
                        rt = co.return_type
                        if rt is not None:
                            c = coerce(v, rt)
                            if c is MISSING:
                                if arg == 1:
                                    raise GaloRuntimeError(
                                        "G309", f"A função '{co.name}' deveria retornar {describe_spec(rt)}, "
                                                f"mas terminou sem executar 'retorne'.",
                                        suggestion="Garanta que todos os caminhos da função terminem com 'retorne <valor>'.",
                                    )
                                raise GaloRuntimeError(
                                    "G309", f"A função '{co.name}' deveria retornar {describe_spec(rt)}, "
                                            f"mas retornou {article(type_name(v))}.",
                                )
                            v = c
                        frames.pop()
                        if len(frames) == stop:
                            return v
                        frames[-1].stack.append(v)
                        break
                    elif op == INDEX:
                        i = pop()
                        o = stack[-1]
                        if type(o) is list and type(i) is int and 0 < i <= len(o):
                            stack[-1] = o[i - 1]
                        else:
                            stack[-1] = index_get(o, i)
                    elif op == MUL:
                        b = pop()
                        a = stack[-1]
                        if type(a) is int and type(b) is int:
                            stack[-1] = a * b
                        else:
                            stack[-1] = op_mul(a, b)
                    elif op == LOAD_CELL:
                        v = locs[arg].value
                        if v is UNSET:
                            raise GaloRuntimeError("G318", f"'{co.local_names[arg]}' foi usada antes de receber um valor.")
                        push(v)
                    elif op == LOAD_FREE:
                        v = frame.cells[arg].value
                        if v is UNSET:
                            raise GaloRuntimeError("G318", f"'{co.free_names[arg]}' foi usada antes de receber um valor.",
                                                   suggestion="A função foi chamada antes de a variável ser definida.")
                        push(v)
                    elif op == STORE_CELL:
                        locs[arg].value = pop()
                    elif op == STORE_FREE:
                        frame.cells[arg].value = pop()
                    elif op == FOR_ITER2:
                        v = next(stack[-1], MISSING)
                        if v is MISSING:
                            pop()
                            pc = arg
                        else:
                            push(v[0])
                            push(v[1])
                    elif op == POP:
                        pop()
                    elif op == DUP:
                        push(stack[-1])
                    elif op == DEFINE_GLOBAL:
                        key = frame.keys[arg]
                        globals_[key] = pop()
                        self.global_names[key] = co.names[arg]
                    elif op == MAKE_CELL:
                        locs[arg] = Cell()
                    elif op == BOX_LOCAL:
                        locs[arg] = Cell(locs[arg])
                    elif op == DIV:
                        b = pop()
                        stack[-1] = op_div(stack[-1], b)
                    elif op == IDIV:
                        b = pop()
                        stack[-1] = op_idiv(stack[-1], b)
                    elif op == MOD:
                        b = pop()
                        stack[-1] = op_mod(stack[-1], b)
                    elif op == POW:
                        b = pop()
                        stack[-1] = op_pow(stack[-1], b)
                    elif op == NEG:
                        a = stack[-1]
                        stack[-1] = -a if type(a) is int else op_neg(a)
                    elif op == POS:
                        stack[-1] = op_pos(stack[-1])
                    elif op == NOT:
                        stack[-1] = op_not(stack[-1])
                    elif op == IN:
                        b = pop()
                        stack[-1] = op_in(stack[-1], b)
                    elif op == JUMP_IF_FALSE_KEEP:
                        v = stack[-1]
                        if v is False:
                            pc = arg
                        elif v is True:
                            pop()
                        else:
                            require_bool(v, "Cada lado do operador 'e'")
                    elif op == JUMP_IF_TRUE_KEEP:
                        v = stack[-1]
                        if v is True:
                            pc = arg
                        elif v is False:
                            pop()
                        else:
                            require_bool(v, "Cada lado do operador 'ou'")
                    elif op == CHECK_BOOL:
                        v = stack[-1]
                        if type(v) is not bool:
                            require_bool(v, f"Cada lado do operador '{_LOGIC_NAMES.get(arg, 'e')}'")
                    elif op == BUILD_LIST:
                        if arg:
                            items = stack[-arg:]
                            del stack[-arg:]
                        else:
                            items = []
                        push(items)
                    elif op == BUILD_MAP:
                        m = GaloMapa()
                        if arg:
                            items = stack[-2 * arg:]
                            del stack[-2 * arg:]
                            for i in range(0, 2 * arg, 2):
                                m.set(items[i], items[i + 1])
                        push(m)
                    elif op == BUILD_STRING:
                        parts = stack[-arg:]
                        del stack[-arg:]
                        push("".join(p if type(p) is str else display(p) for p in parts))
                    elif op == STORE_INDEX:
                        v = pop()
                        i = pop()
                        index_set(pop(), i, v)
                    elif op == GET_FIELD:
                        stack[-1] = field_get(stack[-1], co.names[arg])
                    elif op == SET_FIELD:
                        v = pop()
                        field_set(pop(), co.names[arg], v)
                    elif op == MAKE_FUNCTION:
                        fco = consts[arg]
                        cells = tuple(locs[i] if kind == 0 else frame.cells[i] for kind, i in fco.free_sources)
                        push(Closure(fco, cells, globals_))
                    elif op == PRINT:
                        if arg:
                            values = stack[-arg:]
                            del stack[-arg:]
                            out_write(" ".join(v if type(v) is str else display(v) for v in values) + "\n")
                        else:
                            out_write("\n")
                    elif op == PRINT_REPL:
                        v = pop()
                        if v is not None:
                            out_write(repr_value(v) + "\n")
                    elif op == ITER_PREPARE:
                        stack[-1] = make_iter(stack[-1], arg == 1)
                    elif op == RANGE_PREPARE:
                        step = pop() if arg else None
                        end = pop()
                        stack[-1] = make_range(stack[-1], end, step)
                    elif op == REPEAT_PREPARE:
                        stack[-1] = make_repeat(stack[-1])
                    elif op == SETUP_TRY:
                        if frame.handlers is None:
                            frame.handlers = []
                        frame.handlers.append((arg, len(stack)))
                    elif op == POP_TRY:
                        frame.handlers.pop()
                    elif op == RAISE:
                        raise self._user_error(pop())
                    elif op == CHECK_TYPE:
                        tc = consts[arg]
                        v = coerce(stack[-1], tc.spec)
                        if v is MISSING:
                            label = tc.label[0].upper() + tc.label[1:]
                            raise GaloRuntimeError(
                                "G315", f"{label} é do tipo {describe_spec(tc.spec)}, mas recebeu "
                                        f"{article(type_name(stack[-1]))}.",
                            )
                        stack[-1] = v
                    elif op == ARG_MISSING:
                        v = locs[arg]
                        push(v is UNSET or (type(v) is Cell and v.value is UNSET))
                    elif op == CALL_KW:
                        info = consts[arg]
                        total = info.npos + len(info.names)
                        values = stack[-total:] if total else []
                        fn = stack[-total - 1]
                        del stack[-total - 1:]
                        fn, positional = self._resolve_callable(fn, values[:info.npos])
                        if type(fn) is not Closure:
                            if type(fn) is NativeFunction:
                                raise GaloRuntimeError("G307", f"A função interna '{fn.name}' não aceita argumentos nomeados.",
                                                       suggestion=f"Forma de uso: {fn.signature}")
                            raise GaloRuntimeError("G306", f"Tentou chamar {article(type_name(fn))} como se fosse uma função.")
                        args = self._bind_kwargs(fn, positional, info.names, values[info.npos:])
                        new_frame = self._new_frame(fn, args)
                        frame.pc = pc
                        frames.append(new_frame)
                        break
                    elif op == NEW_RECORD:
                        values = stack[-arg:] if arg else []
                        if arg:
                            del stack[-arg:]
                        stack[-1] = GaloRegistro(stack[-1], values)
                    elif op == MAKE_RECORD_TYPE:
                        info = consts[arg]
                        k = len(info.methods)
                        methods = stack[-k:] if k else []
                        if k:
                            del stack[-k:]
                        stack[-1] = GaloTipoRegistro(info.name, info.fields, info.specs, stack[-1],
                                                     {canonical(n): m for n, m in zip(info.methods, methods)})
                    elif op == IMPORT_MODULE:
                        frame.pc = pc
                        push(self._import_module(arg))
                    elif op == NOP:
                        pass
                    else:  # pragma: no cover - o verificador impede
                        raise GaloInternalError(f"instrução desconhecida: {op}")
                continue
            except GaloRuntimeError as e:
                err = e
            except (GaloExit, KeyboardInterrupt, GaloInternalError):
                raise
            except RecursionError:
                err = GaloRuntimeError("G311", "Estouro de pilha: há estruturas ou chamadas aninhadas demais.")
            except ZeroDivisionError:
                err = GaloRuntimeError("G303", "Divisão por zero.")
            except OverflowError:
                err = GaloRuntimeError("G317", "Número grande demais para ser representado.",
                                       suggestion="Decimais (ponto flutuante) têm limite de aproximadamente 1.8e308.")
            except MemoryError:
                err = GaloRuntimeError("G320", "Memória insuficiente para continuar a execução.")
            except Exception as exc:  # pragma: no cover - falha da implementação
                raise GaloInternalError(f"falha interna da máquina virtual: {exc!r}") from exc
            frame.pc = pc
            self._attach(err)
            if not self._unwind(err, stop):
                raise err
