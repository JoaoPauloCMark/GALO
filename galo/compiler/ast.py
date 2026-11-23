"""Árvore sintática abstrata (AST) da GALO.

Cada nó guarda a posição (linha, coluna) do trecho de código que o originou.
O analisador semântico acrescenta anotações aos nós (atributos `sym`, `res`,
`ctx`, `scope`), consumidas depois pelo gerador de bytecode.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(eq=False)
class Node:
    line: int
    col: int


# ---------------------------------------------------------------- expressões


@dataclass(eq=False)
class Literal(Node):
    value: object  # int, float, str, bool ou None


@dataclass(eq=False)
class TextoInterpolado(Node):
    parts: list  # str ou expressões


@dataclass(eq=False)
class Nome(Node):
    name: str
    key: str
    length: int = 1


@dataclass(eq=False)
class ListaLit(Node):
    elements: list


@dataclass(eq=False)
class MapaLit(Node):
    pairs: list  # lista de (chave, valor)


@dataclass(eq=False)
class Binario(Node):
    op: str
    left: Node
    right: Node


@dataclass(eq=False)
class Comparacao(Node):
    """Comparação possivelmente encadeada: a < b <= c."""

    ops: list
    operands: list
    op_positions: list


@dataclass(eq=False)
class Logico(Node):
    op: str  # "e" | "ou"
    left: Node
    right: Node


@dataclass(eq=False)
class Unario(Node):
    op: str  # "-" | "+" | "não"
    operand: Node


@dataclass(eq=False)
class Chamada(Node):
    callee: Node
    args: list
    kwargs: list = field(default_factory=list)  # lista de ArgNomeado


@dataclass(eq=False)
class ArgNomeado(Node):
    name: str
    key: str
    value: Node


@dataclass(eq=False)
class SeExpr(Node):
    """Expressão condicional: se cond então a senão b."""

    cond: Node
    then: Node
    otherwise: Node


@dataclass(eq=False)
class Indice(Node):
    obj: Node
    index: Node


@dataclass(eq=False)
class Campo(Node):
    obj: Node
    name: str


@dataclass(eq=False)
class FuncaoAnonima(Node):
    params: list
    ret: "TypeAnnot | None"
    body: "Block"
    name: str = "<anônima>"


# ---------------------------------------------------------------- auxiliares


@dataclass(eq=False)
class TypeAnnot(Node):
    names: list  # nomes como escritos
    keys: list   # formas canônicas


@dataclass(eq=False)
class Param(Node):
    name: str
    key: str
    type: TypeAnnot | None = None
    default: Node | None = None


@dataclass(eq=False)
class VarDecl(Node):
    """Variável introduzida por um laço `para` ou por `capture`."""

    name: str
    key: str


# ---------------------------------------------------------------- instruções


@dataclass(eq=False)
class Block(Node):
    stmts: list


@dataclass(eq=False)
class Programa(Node):
    name: str | None
    body: Block


@dataclass(eq=False)
class Defina(Node):
    name: str
    key: str
    type: TypeAnnot | None
    value: Node
    constant: bool = False
    name_line: int = 0
    name_col: int = 0


@dataclass(eq=False)
class DefFuncao(Node):
    name: str
    key: str
    params: list
    ret: TypeAnnot | None
    body: Block
    name_line: int = 0
    name_col: int = 0


@dataclass(eq=False)
class DefRegistro(Node):
    """registro Nome ... fim: campos (como parâmetros) e métodos."""

    name: str
    key: str
    fields: list   # lista de Param
    methods: list  # lista de DefFuncao (o parâmetro implícito 'eu' é acrescentado na análise)
    name_line: int = 0
    name_col: int = 0


@dataclass(eq=False)
class Importe(Node):
    """Importação: `importe "arquivo.galo" como nome` ou `importe a, b de "arquivo.galo"`."""

    path: str
    alias: VarDecl | None
    names: list  # lista de VarDecl


@dataclass(eq=False)
class Atribuicao(Node):
    target: Node  # Nome, Indice ou Campo
    op: str       # "=", "+=", "-=", "*=", "/="
    value: Node


@dataclass(eq=False)
class Se(Node):
    branches: list  # lista de (condição, Block)
    else_block: Block | None


@dataclass(eq=False)
class Enquanto(Node):
    cond: Node
    body: Block


@dataclass(eq=False)
class Repita(Node):
    count: Node
    body: Block


@dataclass(eq=False)
class ParaCada(Node):
    var1: VarDecl
    var2: VarDecl | None
    iterable: Node
    body: Block


@dataclass(eq=False)
class ParaIntervalo(Node):
    var: VarDecl
    start: Node
    end: Node
    step: Node | None
    body: Block


@dataclass(eq=False)
class Tente(Node):
    body: Block
    err_var: VarDecl | None
    handler: Block


@dataclass(eq=False)
class Mostre(Node):
    values: list


@dataclass(eq=False)
class Retorne(Node):
    value: Node | None


@dataclass(eq=False)
class Pare(Node):
    pass


@dataclass(eq=False)
class Continue(Node):
    pass


@dataclass(eq=False)
class Lance(Node):
    value: Node


@dataclass(eq=False)
class ExprStmt(Node):
    expr: Node


# ---------------------------------------------------------------- utilidades


def dump(node, indent: int = 0) -> str:
    """Representação textual da AST (usada por `galo ast` e nos testes)."""
    pad = "  " * indent
    if isinstance(node, list):
        return "\n".join(dump(n, indent) for n in node)
    if isinstance(node, tuple):
        return "\n".join(dump(n, indent) for n in node)
    if not isinstance(node, Node):
        return pad + repr(node)
    name = type(node).__name__
    simple = []
    children = []
    for f in node.__dataclass_fields__:
        if f in ("line", "col", "length", "name_line", "name_col", "op_positions", "key", "keys"):
            continue
        if f in ("kwargs", "default") and not getattr(node, f, None):
            continue
        v = getattr(node, f)
        if isinstance(v, (Node, list, tuple)) and v:
            children.append((f, v))
        else:
            simple.append(f"{f}={v!r}")
    out = f"{pad}{name}({', '.join(simple)})"
    for f, v in children:
        out += f"\n{pad}  {f}:"
        if isinstance(v, list):
            for item in v:
                if isinstance(item, tuple):
                    out += "\n" + "\n".join(dump(x, indent + 2) for x in item)
                else:
                    out += "\n" + dump(item, indent + 2)
        else:
            out += "\n" + dump(v, indent + 2)
    return out
