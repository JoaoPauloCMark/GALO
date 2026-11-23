"""Conversão entre valores GALO e JSON."""

from __future__ import annotations

import json
import math

from ..runtime.values import GaloMapa, GaloRegistro, article, display, type_name
from ._util import erro, exige_texto
from .registry import nativa


def para_python(valor, _caminho: str = "valor", _vistos=None):
    """Converte um valor GALO em estruturas Python serializáveis em JSON."""
    t = type(valor)
    if valor is None or t is bool or t is int or t is str:
        return valor
    if t is float:
        if math.isnan(valor) or math.isinf(valor):
            raise erro("G323", f"{_caminho} é {display(valor)}, que não pode ser representado em JSON.")
        return valor
    if t in (list, GaloMapa, GaloRegistro):
        _vistos = _vistos or set()
        if id(valor) in _vistos:
            raise erro("G323", f"{_caminho} contém a si mesmo e não pode ser convertido em JSON.")
        _vistos.add(id(valor))
        try:
            if t is list:
                return [para_python(x, f"{_caminho}[{i}]", _vistos) for i, x in enumerate(valor, 1)]
            if t is GaloRegistro:
                return {campo: para_python(v, f"{_caminho}.{campo}", _vistos)
                        for campo, v in zip(valor.tipo.fields, valor.valores)}
            saida = {}
            for k, v in valor.items():
                if type(k) is str:
                    chave = k
                elif type(k) in (int, float):
                    chave = display(k)
                else:
                    raise erro("G323", f"A chave {display(k)} de {_caminho} não pode ser usada em JSON (use textos como chaves).")
                saida[chave] = para_python(v, f"{_caminho}[{chave!r}]", _vistos)
            return saida
        finally:
            _vistos.discard(id(valor))
    raise erro("G323", f"{_caminho} é {article(type_name(valor))}, que não pode ser convertido em JSON.")


def de_python(obj):
    """Converte estruturas Python (vindas de JSON, banco de dados...) em valores GALO."""
    if isinstance(obj, dict):
        m = GaloMapa()
        for k, v in obj.items():
            m.set(str(k), de_python(v))
        return m
    if isinstance(obj, (list, tuple)):
        return [de_python(x) for x in obj]
    if isinstance(obj, bytes):
        return obj.decode("utf-8", "replace")
    return obj


def codificar(valor, indentacao=None) -> str:
    return json.dumps(para_python(valor), ensure_ascii=False, indent=indentacao,
                      separators=None if indentacao else (",", ":"))


def decodificar(texto: str):
    def recusar(constante):
        raise ValueError(f"o valor {constante} não é permitido em JSON")

    try:
        return de_python(json.loads(texto, parse_constant=recusar))
    except json.JSONDecodeError as exc:
        raise erro("G323", f"JSON inválido na linha {exc.lineno}, coluna {exc.colno}: {_traduzir(exc.msg)}.",
                   "Confira aspas, vírgulas e chaves. Textos JSON usam aspas duplas.")
    except ValueError as exc:
        raise erro("G323", f"JSON inválido: {exc}.")
    except RecursionError:
        raise erro("G323", "JSON aninhado demais.")


_MENSAGENS = {
    "Expecting value": "esperava um valor",
    "Expecting property name enclosed in double quotes": "esperava o nome de um campo entre aspas duplas",
    "Expecting ',' delimiter": "esperava uma vírgula",
    "Expecting ':' delimiter": "esperava ':'",
    "Unterminated string starting at": "texto não fechado",
    "Extra data": "há conteúdo depois do fim do JSON",
    "Invalid control character at": "caractere de controle inválido",
}


def _traduzir(msg: str) -> str:
    return _MENSAGENS.get(msg, msg)


@nativa("para_json", retorna="texto", assinatura="para_json(valor, [indentação])")
def para_json(vm, valor, indentacao=None):
    """Converte o valor (mapas, listas, registros, textos, números, booleanos, nulo) em um texto JSON.
    Com indentação (por exemplo 2), o resultado fica formatado em várias linhas."""
    if indentacao is not None and type(indentacao) is not int:
        raise erro("G322", "A indentação de para_json() deve ser um inteiro.")
    return codificar(valor, indentacao)


@nativa("de_json", assinatura="de_json(texto)")
def de_json(vm, texto):
    """Converte um texto JSON em valor GALO: objetos viram mapas, arrays viram listas."""
    return decodificar(exige_texto("de_json", 1, texto))
