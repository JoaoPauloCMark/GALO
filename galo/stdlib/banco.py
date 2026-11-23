"""Banco de dados SQL (SQLite), embutido e sem servidor.

    defina banco como abrir_banco("dados.db")       # ou ":memória:"
    banco.executar("CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY, nome TEXT)")
    defina id como banco.inserir("INSERT INTO t (nome) VALUES (?)", ["Ana"])
    defina linhas como banco.consultar("SELECT * FROM t WHERE nome = ?", ["Ana"])

Valores sempre são passados como parâmetros (`?` ou `:nome`), nunca colados no
texto do SQL: isso impede ataques de injeção de SQL.
"""

from __future__ import annotations

import re
import sqlite3

from ..runtime.values import GaloMapa, GaloObjetoNativo, article, type_name
from ._util import erro, exige_funcao, exige_texto
from .registry import nativa

_TRADUCOES = [
    (r"no such table: (.+)", "a tabela '{0}' não existe", "Crie a tabela com CREATE TABLE antes de usá-la."),
    (r"no such column: (.+)", "a coluna '{0}' não existe", "Confira o nome da coluna na definição da tabela."),
    (r"table (.+) already exists", "a tabela '{0}' já existe", "Use CREATE TABLE IF NOT EXISTS."),
    (r"UNIQUE constraint failed: (.+)", "já existe um registro com o mesmo valor em {0}", None),
    (r"NOT NULL constraint failed: (.+)", "o valor de {0} é obrigatório", None),
    (r"FOREIGN KEY constraint failed", "a referência aponta para um registro que não existe", None),
    (r'near "(.+)": syntax error', "erro de sintaxe no SQL perto de '{0}'", None),
    (r"incomplete input", "o comando SQL está incompleto", None),
    (r"Incorrect number of bindings supplied. The current statement uses (\d+), and there are (\d+) supplied.",
     "o SQL usa {0} parâmetro(s), mas foram informados {1}", "Cada ? no SQL precisa de um valor na lista de parâmetros."),
    (r"You did not supply a value for binding parameter :(\w+).", "faltou o valor do parâmetro :{0}", None),
]


def _erro_sql(exc: Exception):
    msg = str(exc)
    for padrao, traducao, sugestao in _TRADUCOES:
        m = re.search(padrao, msg)
        if m:
            return erro("G324", "Erro no banco de dados: " + traducao.format(*m.groups()) + ".", sugestao)
    return erro("G324", f"Erro no banco de dados: {msg}.")


def _para_sql(valor, posicao):
    t = type(valor)
    if valor is None or t is int or t is float or t is str:
        return valor
    if t is bool:
        return 1 if valor else 0
    raise erro("G324", f"O parâmetro {posicao} do SQL é {article(type_name(valor))}, que não pode ser guardado diretamente.",
               "Guarde listas e mapas como texto com para_json(valor) e leia de volta com de_json(texto).")


def _parametros(fname, parametros):
    if parametros is None:
        return ()
    if type(parametros) is list:
        return tuple(_para_sql(v, i) for i, v in enumerate(parametros, 1))
    if type(parametros) is GaloMapa:
        return {str(k): _para_sql(v, f":{k}") for k, v in parametros.items()}
    raise erro("G322", f"Os parâmetros de {fname} devem ser uma lista (para ?) ou um mapa (para :nome).")


def _linha(cursor, row) -> GaloMapa:
    m = GaloMapa()
    for coluna, valor in zip(cursor.description, row):
        if isinstance(valor, bytes):
            valor = valor.decode("utf-8", "replace")
        m.set(coluna[0], valor)
    return m


class _Banco:
    def __init__(self, caminho: str, exibido: str) -> None:
        try:
            self.conn = sqlite3.connect(caminho, isolation_level=None, check_same_thread=False)
            self.conn.execute("PRAGMA foreign_keys = ON")
        except sqlite3.Error as exc:
            raise erro("G324", f"Não foi possível abrir o banco de dados \"{exibido}\": {exc}.")
        self.em_transacao = False

    def __del__(self):
        conn = getattr(self, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    def cursor(self, fname, sql, parametros):
        exige_texto(fname, 1, sql)
        if self.conn is None:
            raise erro("G324", "O banco de dados já foi fechado.")
        try:
            return self.conn.execute(sql, _parametros(fname, parametros))
        except sqlite3.Warning as exc:
            if "one statement at a time" in str(exc):
                raise erro("G324", "Só é possível executar um comando SQL por vez.",
                           "Para vários comandos sem parâmetros, use banco.executar_script(sql).")
            raise _erro_sql(exc)
        except (sqlite3.Error, OverflowError) as exc:
            raise _erro_sql(exc)


def _criar(vm, caminho: str) -> GaloObjetoNativo:
    real = ":memory:" if caminho in (":memória:", ":memoria:", ":memory:") else vm.resolve_path(caminho)
    banco = _Banco(real, caminho)
    obj = GaloObjetoNativo("BancoDeDados", banco)

    def executar(vm, _o, sql, parametros=None):
        return max(banco.cursor("executar", sql, parametros).rowcount, 0)

    def executar_script(vm, _o, sql):
        exige_texto("executar_script", 1, sql)
        try:
            banco.conn.executescript(sql)
        except sqlite3.Error as exc:
            raise _erro_sql(exc)
        return None

    def inserir(vm, _o, sql, parametros=None):
        return banco.cursor("inserir", sql, parametros).lastrowid

    def consultar(vm, _o, sql, parametros=None):
        c = banco.cursor("consultar", sql, parametros)
        return [_linha(c, r) for r in c.fetchall()] if c.description else []

    def consultar_um(vm, _o, sql, parametros=None):
        c = banco.cursor("consultar_um", sql, parametros)
        r = c.fetchone() if c.description else None
        return None if r is None else _linha(c, r)

    def transacao(vm, _o, funcao):
        exige_funcao("transação", 1, funcao)
        if banco.em_transacao:
            return vm.call_value(funcao, [])
        banco.conn.execute("BEGIN")
        banco.em_transacao = True
        try:
            resultado = vm.call_value(funcao, [])
        except BaseException:
            banco.conn.execute("ROLLBACK")
            raise
        else:
            banco.conn.execute("COMMIT")
            return resultado
        finally:
            banco.em_transacao = False

    def fechar(vm, _o):
        if banco.conn is not None:
            banco.conn.close()
            banco.conn = None
        return None

    obj.metodo("executar", executar, 1, 2, ("inteiro",), "Executa um comando SQL; devolve quantas linhas foram afetadas.")
    obj.metodo("executar_script", executar_script, 1, 1, ("nulo",), "Executa vários comandos SQL separados por ';' (sem parâmetros).")
    obj.metodo("inserir", inserir, 1, 2, ("inteiro",), "Executa um INSERT e devolve o id da linha criada.")
    obj.metodo("consultar", consultar, 1, 2, ("lista",), "Executa um SELECT e devolve uma lista de mapas (coluna -> valor).")
    obj.metodo("consultar_um", consultar_um, 1, 2, None, "Executa um SELECT e devolve a primeira linha (mapa) ou nulo.")
    obj.metodo("transação", transacao, 1, 1, None, "Executa a função dentro de uma transação: tudo ou nada.")
    obj.metodo("fechar", fechar, 0, 0, ("nulo",), "Fecha o banco de dados.")
    return obj


@nativa("abrir_banco", assinatura="abrir_banco(caminho)")
def abrir_banco(vm, caminho):
    """Abre (ou cria) um banco de dados SQLite. Use ":memória:" para um banco temporário.
    Devolve um BancoDeDados com os métodos executar, executar_script, inserir, consultar,
    consultar_um, transação e fechar. Valores entram sempre como parâmetros (? ou :nome)."""
    return _criar(vm, exige_texto("abrir_banco", 1, caminho))
