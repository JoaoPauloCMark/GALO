"""Bytecode da GALO: conjunto de instruções, objetos de código e formato .galoc.

A máquina virtual da GALO é uma máquina de pilha. Cada instrução ocupa
duas posições na lista `code`: o código da operação e um argumento inteiro
(0 quando não é usado). O significado do argumento depende da operação
(índice de constante, de variável local, destino de desvio, quantidade...).

Formato do arquivo .galoc (todos os inteiros multibyte em little-endian):

    "GALOC\\0"              6 bytes   assinatura
    versão do formato      u16
    conteúdo:
        versão da GALO      texto
        nome do programa    texto (vazio se não houver)
        arquivo de origem   texto
        código principal    objeto de código
    CRC32 do conteúdo      u32

Textos são gravados como (tamanho varint + bytes UTF-8). Valores constantes
têm uma marca de tipo de 1 byte: N nulo, T verdadeiro, F falso, I inteiro
(sinal + magnitude de tamanho arbitrário), D decimal (IEEE 754 de 64 bits),
S texto, C objeto de código, Y verificação de tipo.
"""

from __future__ import annotations

import struct
import zlib
from enum import IntEnum

from .. import BYTECODE_VERSION, __version__
from ..errors import GaloBytecodeError


class Op(IntEnum):
    NOP = 0
    CONST = 1               # empilha consts[arg]
    POP = 2
    DUP = 3
    LOAD_LOCAL = 4          # empilha locals[arg]
    STORE_LOCAL = 5         # locals[arg] = desempilha
    LOAD_CELL = 6           # empilha locals[arg].valor (variável capturada)
    STORE_CELL = 7
    MAKE_CELL = 8           # locals[arg] = nova caixa vazia
    BOX_LOCAL = 9           # locals[arg] = caixa(locals[arg]) (parâmetro capturado)
    LOAD_FREE = 10          # empilha células_capturadas[arg].valor
    STORE_FREE = 11
    LOAD_GLOBAL = 12        # empilha globais[names[arg]] (ou função interna)
    STORE_GLOBAL = 13       # globais[names[arg]] = desempilha (precisa existir)
    DEFINE_GLOBAL = 14      # globais[names[arg]] = desempilha
    ADD = 15
    SUB = 16
    MUL = 17
    DIV = 18
    IDIV = 19
    MOD = 20
    POW = 21
    NEG = 22
    POS = 23
    NOT = 24
    EQ = 25
    NE = 26
    LT = 27
    LE = 28
    GT = 29
    GE = 30
    IN = 31
    JUMP = 32               # desvia para arg
    JUMP_IF_FALSE = 33      # desempilha booleano; desvia se falso
    JUMP_IF_FALSE_KEEP = 34 # operador 'e': se falso, mantém e desvia; senão, descarta
    JUMP_IF_TRUE_KEEP = 35  # operador 'ou'
    CHECK_BOOL = 36         # topo deve ser booleano (arg: 1 = operando de 'e', 2 = de 'ou')
    BUILD_LIST = 37         # cria lista com arg elementos
    BUILD_MAP = 38          # cria mapa com arg pares
    BUILD_STRING = 39       # concatena arg partes (interpolação)
    INDEX = 40              # obj[i]
    STORE_INDEX = 41        # obj[i] = v
    GET_FIELD = 42          # obj.names[arg]
    SET_FIELD = 43
    CALL = 44               # chama função com arg argumentos
    RETURN = 45             # arg: 1 = retorno implícito (fim da função)
    MAKE_FUNCTION = 46      # cria closure de consts[arg]
    PRINT = 47              # mostra arg valores
    PRINT_REPL = 48         # mostra o valor de uma expressão digitada no REPL
    ITER_PREPARE = 49       # transforma coleção em iterador (arg: 1 = duas variáveis)
    RANGE_PREPARE = 50      # início, fim[, passo] -> iterador (arg: 1 = com passo)
    REPEAT_PREPARE = 51     # quantidade -> iterador
    FOR_ITER = 52           # próximo valor do iterador, ou desvia para arg ao terminar
    FOR_ITER2 = 53          # idem, empilhando dois valores
    SETUP_TRY = 54          # registra tratador de erros em arg
    POP_TRY = 55
    RAISE = 56              # lança o valor do topo como erro
    CHECK_TYPE = 57         # verifica o tipo do topo com consts[arg] (TypeCheck)
    IMPORT_MODULE = 58      # executa (uma vez) o módulo modules[arg] e empilha o valor do módulo
    MAKE_RECORD_TYPE = 59   # construtor + métodos -> tipo de registro (consts[arg]: RecordInfo)
    NEW_RECORD = 60         # tipo, v1..vN -> instância com arg campos
    CALL_KW = 61            # chamada com argumentos nomeados (consts[arg]: CallInfo)
    ARG_MISSING = 62        # empilha verdadeiro se o parâmetro locals[arg] não foi informado


# Tipo do argumento de cada instrução (usado pelo verificador e pelo desmontador).
ARG_KIND = {
    Op.CONST: "const", Op.LOAD_LOCAL: "local", Op.STORE_LOCAL: "local", Op.LOAD_CELL: "local",
    Op.STORE_CELL: "local", Op.MAKE_CELL: "local", Op.BOX_LOCAL: "local",
    Op.LOAD_FREE: "free", Op.STORE_FREE: "free",
    Op.LOAD_GLOBAL: "name", Op.STORE_GLOBAL: "name", Op.DEFINE_GLOBAL: "name",
    Op.GET_FIELD: "name", Op.SET_FIELD: "name",
    Op.JUMP: "jump", Op.JUMP_IF_FALSE: "jump", Op.JUMP_IF_FALSE_KEEP: "jump", Op.JUMP_IF_TRUE_KEEP: "jump",
    Op.FOR_ITER: "jump", Op.FOR_ITER2: "jump", Op.SETUP_TRY: "jump",
    Op.BUILD_LIST: "count", Op.BUILD_MAP: "count", Op.BUILD_STRING: "count", Op.CALL: "count", Op.PRINT: "count",
    Op.CHECK_BOOL: "flag", Op.RETURN: "flag", Op.ITER_PREPARE: "flag", Op.RANGE_PREPARE: "flag",
    Op.MAKE_FUNCTION: "code", Op.CHECK_TYPE: "typecheck",
    Op.IMPORT_MODULE: "module", Op.MAKE_RECORD_TYPE: "record", Op.NEW_RECORD: "count",
    Op.CALL_KW: "callinfo", Op.ARG_MISSING: "local",
}

MAX_OP = max(int(o) for o in Op)


class TypeCheck:
    """Constante usada por CHECK_TYPE: tipos aceitos + descrição para a mensagem de erro."""

    __slots__ = ("spec", "label")

    def __init__(self, spec: tuple, label: str) -> None:
        self.spec = spec
        self.label = label

    def __repr__(self) -> str:
        return f"<tipo {' ou '.join(self.spec)} para {self.label}>"


class RecordInfo:
    """Constante usada por MAKE_RECORD_TYPE: nome, campos, tipos dos campos e métodos."""

    __slots__ = ("name", "fields", "specs", "methods")

    def __init__(self, name: str, fields: tuple, specs: tuple, methods: tuple) -> None:
        self.name = name
        self.fields = fields
        self.specs = specs
        self.methods = methods

    def __repr__(self) -> str:
        return f"<registro {self.name}({', '.join(self.fields)})>"


class CallInfo:
    """Constante usada por CALL_KW: quantidade de argumentos posicionais e nomes dos nomeados."""

    __slots__ = ("npos", "names")

    def __init__(self, npos: int, names: tuple) -> None:
        self.npos = npos
        self.names = names

    def __repr__(self) -> str:
        return f"<{self.npos} posicionais; nomeados: {', '.join(self.names)}>"


class ModuleEntry:
    """Módulo importado incluído no programa compilado."""

    __slots__ = ("name", "code", "exports")

    def __init__(self, name: str, code: "CodeObject", exports: list) -> None:
        self.name = name
        self.code = code
        self.exports = list(exports)


class CodeObject:
    """Código compilado de uma função (ou do programa principal)."""

    __slots__ = (
        "name", "filename", "params", "param_types", "nlocals", "local_names",
        "free_sources", "free_names", "return_type", "names", "consts", "code", "positions",
        "keys", "defaults", "typed",
    )

    def __init__(self, name: str, filename: str) -> None:
        self.name = name
        self.filename = filename
        self.params: tuple = ()
        self.param_types: tuple = ()      # tupla de (tupla de tipos ou None)
        self.nlocals = 0
        self.local_names: list[str] = []
        self.free_sources: list[tuple[int, int]] = []  # (0, slot local do pai) | (1, índice livre do pai)
        self.free_names: list[str] = []
        self.return_type: tuple | None = None
        self.names: list[str] = []
        self.consts: list = []
        self.code: list[int] = []
        self.positions: list[tuple[int, int]] = []
        self.defaults: tuple = ()          # para cada parâmetro: tem valor padrão?
        # Calculados pela VM (não são gravados no .galoc):
        self.keys: list[str] | None = None  # formas canônicas de `names`
        self.typed: bool | None = None      # algum parâmetro tem tipo anotado?

    @property
    def nparams(self) -> int:
        return len(self.params)

    def __repr__(self) -> str:
        return f"<código {self.name}>"


class Module:
    """Unidade compilada: um programa .galo completo, com todos os módulos que ele importa."""

    __slots__ = ("code", "program_name", "source_name", "galo_version", "modules")

    def __init__(self, code: CodeObject, program_name: str | None, source_name: str, galo_version: str = __version__,
                 modules: list | None = None) -> None:
        self.code = code
        self.program_name = program_name
        self.source_name = source_name
        self.galo_version = galo_version
        self.modules: list[ModuleEntry] = list(modules or [])


# ---------------------------------------------------------------- gravação

MAGIC = b"GALOC\x00"


def _w_varint(buf: bytearray, n: int) -> None:
    if n < 0:
        raise ValueError("varint negativo")
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            buf.append(b | 0x80)
        else:
            buf.append(b)
            return


def _w_str(buf: bytearray, s: str) -> None:
    data = s.encode("utf-8", "surrogatepass")
    _w_varint(buf, len(data))
    buf += data


def _w_spec(buf: bytearray, spec) -> None:
    if spec is None:
        _w_varint(buf, 0)
        return
    _w_varint(buf, len(spec))
    for name in spec:
        _w_str(buf, name)


def _w_value(buf: bytearray, v) -> None:
    t = type(v)
    if v is None:
        buf += b"N"
    elif t is bool:
        buf += b"T" if v else b"F"
    elif t is int:
        buf += b"I"
        buf.append(1 if v < 0 else 0)
        mag = abs(v)
        nbytes = (mag.bit_length() + 7) // 8
        _w_varint(buf, nbytes)
        buf += mag.to_bytes(nbytes, "little")
    elif t is float:
        buf += b"D"
        buf += struct.pack("<d", v)
    elif t is str:
        buf += b"S"
        _w_str(buf, v)
    elif t is CodeObject:
        buf += b"C"
        _w_code(buf, v)
    elif t is TypeCheck:
        buf += b"Y"
        _w_spec(buf, v.spec)
        _w_str(buf, v.label)
    elif t is RecordInfo:
        buf += b"R"
        _w_str(buf, v.name)
        _w_varint(buf, len(v.fields))
        for f, spec in zip(v.fields, v.specs):
            _w_str(buf, f)
            _w_spec(buf, spec)
        _w_varint(buf, len(v.methods))
        for m in v.methods:
            _w_str(buf, m)
    elif t is CallInfo:
        buf += b"K"
        _w_varint(buf, v.npos)
        _w_varint(buf, len(v.names))
        for n in v.names:
            _w_str(buf, n)
    else:  # pragma: no cover - erro de implementação
        raise TypeError(f"constante não serializável: {v!r}")


def _w_code(buf: bytearray, co: CodeObject) -> None:
    _w_str(buf, co.name)
    _w_str(buf, co.filename)
    _w_varint(buf, len(co.params))
    defaults = co.defaults or (False,) * len(co.params)
    for p, spec, has_default in zip(co.params, co.param_types, defaults):
        _w_str(buf, p)
        _w_spec(buf, spec)
        buf.append(1 if has_default else 0)
    _w_varint(buf, co.nlocals)
    _w_varint(buf, len(co.local_names))
    for n in co.local_names:
        _w_str(buf, n)
    _w_varint(buf, len(co.free_sources))
    for (kind, idx), name in zip(co.free_sources, co.free_names):
        buf.append(kind)
        _w_varint(buf, idx)
        _w_str(buf, name)
    buf.append(0 if co.return_type is None else 1)
    if co.return_type is not None:
        _w_spec(buf, co.return_type)
    _w_varint(buf, len(co.names))
    for n in co.names:
        _w_str(buf, n)
    _w_varint(buf, len(co.consts))
    for c in co.consts:
        _w_value(buf, c)
    _w_varint(buf, len(co.code))
    for x in co.code:
        _w_varint(buf, x)
    for line, col in co.positions:
        _w_varint(buf, line)
        _w_varint(buf, col)


def dump_module(module: Module) -> bytes:
    payload = bytearray()
    _w_str(payload, module.galo_version)
    _w_str(payload, module.program_name or "")
    _w_str(payload, module.source_name or "")
    _w_code(payload, module.code)
    _w_varint(payload, len(module.modules))
    for entry in module.modules:
        _w_str(payload, entry.name)
        _w_code(payload, entry.code)
        _w_varint(payload, len(entry.exports))
        for e in entry.exports:
            _w_str(payload, e)
    out = bytearray(MAGIC)
    out += struct.pack("<H", BYTECODE_VERSION)
    out += payload
    out += struct.pack("<I", zlib.crc32(bytes(payload)) & 0xFFFFFFFF)
    return bytes(out)


# ---------------------------------------------------------------- leitura


class _Reader:
    def __init__(self, data: bytes, filename: str) -> None:
        self.data = data
        self.pos = 0
        self.filename = filename

    def fail(self, detail: str):
        return GaloBytecodeError("G502", f"O arquivo de bytecode está corrompido ou incompleto ({detail}).",
                                 suggestion="Compile novamente o programa com: galo compilar programa.galo",
                                 file=self.filename)

    def byte(self) -> int:
        if self.pos >= len(self.data):
            raise self.fail("fim inesperado")
        b = self.data[self.pos]
        self.pos += 1
        return b

    def varint(self) -> int:
        result = shift = 0
        while True:
            b = self.byte()
            result |= (b & 0x7F) << shift
            if not b & 0x80:
                return result
            shift += 7
            if shift > 7 * 10_000:
                raise self.fail("número inválido")

    def raw(self, n: int) -> bytes:
        if self.pos + n > len(self.data):
            raise self.fail("fim inesperado")
        out = self.data[self.pos:self.pos + n]
        self.pos += n
        return out

    def str(self) -> str:
        n = self.varint()
        try:
            return self.raw(n).decode("utf-8", "surrogatepass")
        except UnicodeDecodeError:
            raise self.fail("texto inválido")

    def spec(self):
        n = self.varint()
        if n == 0:
            return None
        return tuple(self.str() for _ in range(n))

    def value(self, depth: int):
        tag = self.raw(1)
        if tag == b"N":
            return None
        if tag == b"T":
            return True
        if tag == b"F":
            return False
        if tag == b"I":
            neg = self.byte()
            nbytes = self.varint()
            mag = int.from_bytes(self.raw(nbytes), "little")
            return -mag if neg else mag
        if tag == b"D":
            return struct.unpack("<d", self.raw(8))[0]
        if tag == b"S":
            return self.str()
        if tag == b"C":
            if depth > 200:
                raise self.fail("aninhamento excessivo")
            return self.code(depth + 1)
        if tag == b"Y":
            spec = self.spec()
            return TypeCheck(spec or (), self.str())
        if tag == b"R":
            name = self.str()
            fields, specs = [], []
            for _ in range(self.varint()):
                fields.append(self.str())
                specs.append(self.spec())
            methods = tuple(self.str() for _ in range(self.varint()))
            return RecordInfo(name, tuple(fields), tuple(specs), methods)
        if tag == b"K":
            npos = self.varint()
            return CallInfo(npos, tuple(self.str() for _ in range(self.varint())))
        raise self.fail(f"marca de constante desconhecida {tag!r}")

    def code(self, depth: int = 0) -> CodeObject:
        co = CodeObject(self.str(), self.str())
        nparams = self.varint()
        params, types, defaults = [], [], []
        for _ in range(nparams):
            params.append(self.str())
            types.append(self.spec())
            defaults.append(bool(self.byte()))
        co.params, co.param_types, co.defaults = tuple(params), tuple(types), tuple(defaults)
        co.nlocals = self.varint()
        co.local_names = [self.str() for _ in range(self.varint())]
        nfree = self.varint()
        for _ in range(nfree):
            kind = self.byte()
            idx = self.varint()
            co.free_sources.append((kind, idx))
            co.free_names.append(self.str())
        if self.byte():
            co.return_type = self.spec()
        co.names = [self.str() for _ in range(self.varint())]
        co.consts = [self.value(depth) for _ in range(self.varint())]
        n = self.varint()
        co.code = [self.varint() for _ in range(n)]
        co.positions = [(self.varint(), self.varint()) for _ in range(n // 2)]
        return co


def load_module(data: bytes, filename: str = "<bytecode>") -> Module:
    if not data.startswith(MAGIC):
        raise GaloBytecodeError("G502", "Este arquivo não é um programa GALO compilado (.galoc).",
                                suggestion="Para executar código-fonte, use: galo executar programa.galo", file=filename)
    if len(data) < len(MAGIC) + 2 + 4:
        raise GaloBytecodeError("G502", "O arquivo de bytecode está incompleto.", file=filename)
    (version,) = struct.unpack_from("<H", data, len(MAGIC))
    if version != BYTECODE_VERSION:
        raise GaloBytecodeError(
            "G503", f"Este bytecode usa o formato versão {version}, mas esta GALO entende a versão {BYTECODE_VERSION}.",
            suggestion="Compile o programa novamente com a versão atual: galo compilar programa.galo", file=filename,
        )
    payload = data[len(MAGIC) + 2:-4]
    (crc,) = struct.unpack("<I", data[-4:])
    if zlib.crc32(payload) & 0xFFFFFFFF != crc:
        raise GaloBytecodeError("G502", "O arquivo de bytecode está corrompido (soma de verificação inválida).",
                                suggestion="Compile novamente o programa com: galo compilar programa.galo", file=filename)
    r = _Reader(payload, filename)
    galo_version = r.str()
    program_name = r.str() or None
    source_name = r.str()
    code = r.code()
    modules = []
    for _ in range(r.varint()):
        name = r.str()
        mcode = r.code()
        exports = [r.str() for _ in range(r.varint())]
        modules.append(ModuleEntry(name, mcode, exports))
    if r.pos != len(payload):
        raise r.fail("dados extras no final")
    verify(code, filename, module_count=len(modules))
    for entry in modules:
        verify(entry.code, filename, module_count=len(modules))
    return Module(code, program_name, source_name, galo_version, modules)


# ---------------------------------------------------------------- verificação


def verify(co: CodeObject, filename: str = "<bytecode>", parent: CodeObject | None = None, module_count: int = 0) -> None:
    """Confere se o bytecode é bem formado antes de executá-lo."""

    def bad(detail: str):
        return GaloBytecodeError("G502", f"Bytecode inválido na função '{co.name}': {detail}.",
                                 suggestion="Compile novamente o programa com: galo compilar programa.galo", file=filename)

    n = len(co.code)
    if n % 2:
        raise bad("tamanho ímpar")
    if len(co.positions) != n // 2:
        raise bad("tabela de posições inconsistente")
    if len(co.params) > co.nlocals:
        raise bad("mais parâmetros do que variáveis locais")
    if co.defaults and len(co.defaults) != len(co.params):
        raise bad("tabela de valores padrão inconsistente")
    if n == 0 or co.code[n - 2] not in (Op.RETURN, Op.JUMP):
        raise bad("o código não termina com um retorno")
    if parent is not None:
        for kind, idx in co.free_sources:
            if kind == 0 and idx >= parent.nlocals:
                raise bad("captura de variável inexistente")
            if kind == 1 and idx >= len(parent.free_sources):
                raise bad("captura de variável inexistente")
            if kind not in (0, 1):
                raise bad("tipo de captura desconhecido")
    elif co.free_sources:
        raise bad("o programa principal não pode capturar variáveis")
    for pc in range(0, n, 2):
        op, arg = co.code[pc], co.code[pc + 1]
        if op > MAX_OP:
            raise bad(f"instrução desconhecida {op}")
        kind = ARG_KIND.get(Op(op))
        if kind == "const" and arg >= len(co.consts):
            raise bad("constante inexistente")
        if kind == "local" and arg >= co.nlocals:
            raise bad("variável local inexistente")
        if kind == "free" and arg >= len(co.free_sources):
            raise bad("variável capturada inexistente")
        if kind == "name" and arg >= len(co.names):
            raise bad("nome inexistente")
        if kind == "jump" and (arg % 2 or arg > n):
            raise bad("desvio para posição inválida")
        if kind == "code" and (arg >= len(co.consts) or type(co.consts[arg]) is not CodeObject):
            raise bad("função inexistente")
        if kind == "typecheck" and (arg >= len(co.consts) or type(co.consts[arg]) is not TypeCheck):
            raise bad("verificação de tipo inexistente")
        if kind == "record" and (arg >= len(co.consts) or type(co.consts[arg]) is not RecordInfo):
            raise bad("descrição de registro inexistente")
        if kind == "callinfo" and (arg >= len(co.consts) or type(co.consts[arg]) is not CallInfo):
            raise bad("descrição de chamada inexistente")
        if kind == "module" and arg >= module_count:
            raise bad("módulo inexistente")
    for c in co.consts:
        if type(c) is CodeObject:
            verify(c, filename, co, module_count)


# ---------------------------------------------------------------- desmontagem


def _short(v) -> str:
    from ..runtime.values import repr_value

    if type(v) is CodeObject:
        return f"<função {v.name}>"
    if type(v) in (TypeCheck, RecordInfo, CallInfo):
        return repr(v)
    text = repr_value(v)
    return text if len(text) <= 40 else text[:37] + "..."


def disassemble_module(module: "Module") -> list[str]:
    out = disassemble(module.code)
    for i, entry in enumerate(module.modules):
        out.append("")
        out.append(f"######## módulo {i}: {entry.name} (exporta: {', '.join(entry.exports) or 'nada'})")
        disassemble(entry.code, out)
    return out


def disassemble(co: CodeObject, out: list[str] | None = None) -> list[str]:
    out = [] if out is None else out
    if co.name == "<programa>":
        header = "programa principal"
    elif co.name.startswith("<módulo"):
        header = co.name.strip("<>")
    else:
        header = f"função {co.name}"
    out.append(f"== {header} ==")
    if co.params:
        shown = []
        for p, spec in zip(co.params, co.param_types):
            shown.append(f"{p} como {' ou '.join(spec)}" if spec else p)
        out.append(f"parâmetros: {', '.join(shown)}")
    if co.return_type:
        out.append(f"retorna: {' ou '.join(co.return_type)}")
    out.append(f"variáveis locais: {co.nlocals}   capturadas: {len(co.free_sources)}   constantes: {len(co.consts)}")
    last_line = None
    for pc in range(0, len(co.code), 2):
        op, arg = Op(co.code[pc]), co.code[pc + 1]
        line = co.positions[pc // 2][0]
        line_txt = f"{line:>4}" if line != last_line else "    "
        last_line = line
        kind = ARG_KIND.get(op)
        detail = ""
        if kind == "const" or kind in ("code", "typecheck", "record", "callinfo"):
            detail = f"{arg} ({_short(co.consts[arg])})"
        elif kind == "local":
            name = co.local_names[arg] if arg < len(co.local_names) else "?"
            detail = f"{arg} ({name})"
        elif kind == "free":
            detail = f"{arg} ({co.free_names[arg]})"
        elif kind == "name":
            detail = f"{arg} ({co.names[arg]})"
        elif kind == "jump":
            detail = f"-> {arg}"
        elif kind in ("count", "flag", "module"):
            detail = str(arg)
        out.append(f"{line_txt}  {pc:>5}  {op.name:<20}{detail}")
    for c in co.consts:
        if type(c) is CodeObject:
            out.append("")
            disassemble(c, out)
    return out
