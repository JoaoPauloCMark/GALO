"""Modelos (templates) de texto/HTML com escape automático.

Sintaxe:
    {{ caminho }}         valor escapado para HTML (seguro para dados do usuário)
    {{{ caminho }}}       valor sem escape (use só com HTML confiável)
    {% se caminho %} ... {% senão %} ... {% fim %}     (aceita "não caminho")
    {% para cada item em caminho %} ... {% fim %}      (também "para cada i, item em ...")
    {% inclua "parcial.html" %}                        (outro modelo, com os mesmos dados)
    {# comentário #}

`caminho` é um nome ou uma sequência de campos: usuario.nome, pedido.itens.
"""

from __future__ import annotations

import html
import os
import re

from ..runtime.values import MISSING, GaloMapa, GaloRegistro, article, display, field_get, make_iter, type_name
from ..errors import GaloRuntimeError
from ._util import erro, exige_texto
from .registry import nativa

_TAG = re.compile(r"(\{\{\{.*?\}\}\}|\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\})", re.S)
_NOME = r"[^\W\d][\w]*"
_CAMINHO = re.compile(rf"{_NOME}(?:\.{_NOME})*$")


class _ErroModelo(Exception):
    pass


def _falha(origem: str, linha: int, msg: str, sugestao: str | None = None) -> GaloRuntimeError:
    return erro("G328", f"Erro no modelo {origem}, linha {linha}: {msg}", sugestao)


def _compilar(texto: str, origem: str):
    raiz: list = []
    pilha = [("raiz", raiz, None, 1)]
    pos = 0
    for m in _TAG.finditer(texto):
        linha = texto.count("\n", 0, m.start()) + 1
        if m.start() > pos:
            pilha[-1][1].append(("texto", texto[pos:m.start()]))
        pos = m.end()
        tag = m.group(0)
        atual = pilha[-1][1]
        if tag.startswith("{#"):
            continue
        if tag.startswith("{{{"):
            caminho = tag[3:-3].strip()
            _validar(caminho, origem, linha)
            atual.append(("valor", caminho, False, linha))
        elif tag.startswith("{{"):
            caminho = tag[2:-2].strip()
            _validar(caminho, origem, linha)
            atual.append(("valor", caminho, True, linha))
        else:
            comando = tag[2:-2].strip()
            palavras = comando.split()
            if not palavras:
                raise _falha(origem, linha, "comando vazio {% %}.")
            chave = palavras[0]
            if chave == "se":
                negado = len(palavras) > 1 and palavras[1] in ("não", "nao")
                resto = palavras[2:] if negado else palavras[1:]
                if len(resto) != 1:
                    raise _falha(origem, linha, f"o 'se' do modelo aceita apenas um caminho: {{% se caminho %}} (recebeu '{comando}').",
                                 "Calcule a condição em GALO e passe o resultado nos dados do modelo.")
                _validar(resto[0], origem, linha)
                no = ["se", resto[0], negado, [], [], linha]
                atual.append(no)
                pilha.append(("se", no[3], no, linha))
            elif chave in ("senão", "senao"):
                if pilha[-1][0] != "se":
                    raise _falha(origem, linha, "{% senão %} fora de um {% se %}.")
                _, _, no, ln = pilha.pop()
                pilha.append(("senão", no[4], no, ln))
            elif chave == "para":
                m2 = re.fullmatch(rf"para\s+cada\s+({_NOME})(?:\s*,\s*({_NOME}))?\s+em\s+(\S+)", comando)
                if not m2:
                    raise _falha(origem, linha, f"forma inválida: '{comando}'.", "Use: {% para cada item em lista %}")
                _validar(m2.group(3), origem, linha)
                no = ["para", m2.group(1), m2.group(2), m2.group(3), [], linha]
                atual.append(no)
                pilha.append(("para", no[4], no, linha))
            elif chave == "fim":
                if len(pilha) == 1:
                    raise _falha(origem, linha, "{% fim %} sem bloco aberto.")
                pilha.pop()
            elif chave in ("inclua", "inclui"):
                m2 = re.fullmatch(r'inclu[ai]\s+"([^"]+)"', comando)
                if not m2:
                    raise _falha(origem, linha, f"forma inválida: '{comando}'.", '{% inclua "cabecalho.html" %}')
                atual.append(("inclua", m2.group(1), linha))
            else:
                raise _falha(origem, linha, f"comando desconhecido '{chave}'.",
                             "Comandos: se, senão, para cada, fim, inclua.")
    if len(pilha) > 1:
        tipo, _, _, linha = pilha[-1]
        raise _falha(origem, linha, f"o bloco '{tipo}' não foi fechado com {{% fim %}}.")
    if pos < len(texto):
        raiz.append(("texto", texto[pos:]))
    return raiz


def _validar(caminho: str, origem: str, linha: int) -> None:
    if not _CAMINHO.match(caminho):
        raise _falha(origem, linha, f"'{caminho}' não é um caminho válido.",
                     "Modelos aceitam apenas nomes e campos (usuario.nome); faça os cálculos em GALO.")


def _buscar(caminho: str, escopos: list, origem: str, linha: int):
    partes = caminho.split(".")
    valor = MISSING
    for escopo in reversed(escopos):
        if type(escopo) is dict:
            if partes[0] in escopo:
                valor = escopo[partes[0]]
                break
        elif type(escopo) in (GaloMapa, GaloRegistro):
            try:
                valor = field_get(escopo, partes[0])
                break
            except GaloRuntimeError:
                continue
    if valor is MISSING:
        raise _falha(origem, linha, f"'{partes[0]}' não existe nos dados do modelo.")
    for parte in partes[1:]:
        try:
            valor = field_get(valor, parte)
        except GaloRuntimeError as exc:
            raise _falha(origem, linha, f"em '{caminho}': {exc.message}")
    return valor


class _Renderizador:
    def __init__(self, vm, pasta: str) -> None:
        self.vm = vm
        self.pasta = pasta
        self.profundidade = 0

    def render(self, nos, escopos, origem, saida: list) -> None:
        for no in nos:
            tipo = no[0]
            if tipo == "texto":
                saida.append(no[1])
            elif tipo == "valor":
                valor = _buscar(no[1], escopos, origem, no[3])
                texto = display(valor)
                saida.append(html.escape(texto, quote=True) if no[2] else texto)
            elif tipo == "se":
                valor = _buscar(no[1], escopos, origem, no[5])
                if type(valor) is not bool:
                    raise _falha(origem, no[5], f"a condição '{no[1]}' deve ser um booleano, mas é {article(type_name(valor))}.",
                                 "Ex.: passe \"tem_itens\": tamanho(itens) > 0 nos dados.")
                self.render(no[3] if valor != no[2] else no[4], escopos, origem, saida)
            elif tipo == "para":
                colecao = _buscar(no[3], escopos, origem, no[5])
                try:
                    it = make_iter(colecao, no[2] is not None)
                except GaloRuntimeError as exc:
                    raise _falha(origem, no[5], exc.message)
                for item in it:
                    local = {no[1]: item[0], no[2]: item[1]} if no[2] else {no[1]: item}
                    self.render(no[4], escopos + [local], origem, saida)
            elif tipo == "inclua":
                self.incluir(no[1], escopos, origem, no[2], saida)

    def incluir(self, caminho, escopos, origem, linha, saida) -> None:
        if self.profundidade > 20:
            raise _falha(origem, linha, "inclusões demais (um modelo está incluindo a si mesmo?).")
        completo = os.path.join(self.pasta, caminho)
        try:
            with open(completo, encoding="utf-8") as f:
                texto = f.read()
        except OSError:
            raise _falha(origem, linha, f'não foi possível abrir "{caminho}".')
        self.profundidade += 1
        anterior = self.pasta
        self.pasta = os.path.dirname(completo)
        try:
            self.render(_compilar(texto, caminho), escopos, caminho, saida)
        finally:
            self.pasta = anterior
            self.profundidade -= 1


def _dados(fname, dados):
    if dados is None:
        return GaloMapa()
    if type(dados) not in (GaloMapa, GaloRegistro):
        raise erro("G322", f"Os dados de {fname}() devem ser um mapa ou um registro, mas são {article(type_name(dados))}.")
    return dados


@nativa("modelo", retorna="texto", assinatura="modelo(texto_do_modelo, [dados])")
def modelo(vm, texto, dados=None):
    """Preenche um modelo de texto com os dados (mapa ou registro).
    {{ x }} insere o valor com escape HTML; {{{ x }}} sem escape; {% se x %}, {% para cada i em lista %},
    {% inclua "arquivo" %} e {% fim %} controlam o modelo."""
    exige_texto("modelo", 1, texto)
    saida: list = []
    _Renderizador(vm, vm.base_dir).render(_compilar(texto, "(texto)"), [_dados("modelo", dados)], "(texto)", saida)
    return "".join(saida)


@nativa("renderizar", retorna="texto", assinatura="renderizar(arquivo, [dados])")
def renderizar(vm, caminho, dados=None):
    """Lê um arquivo de modelo (por exemplo, paginas/inicio.html) e o preenche com os dados.
    Veja modelo() para a sintaxe. Inclusões são relativas à pasta do arquivo."""
    exige_texto("renderizar", 1, caminho)
    completo = vm.resolve_path(caminho)
    try:
        with open(completo, encoding="utf-8") as f:
            texto = f.read()
    except OSError:
        raise erro("G313", f'O modelo "{caminho}" não foi encontrado.',
                   "Caminhos relativos partem da pasta do programa principal.")
    saida: list = []
    _Renderizador(vm, os.path.dirname(completo)).render(_compilar(texto, caminho), [_dados("renderizar", dados)], caminho, saida)
    return "".join(saida)
