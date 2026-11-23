"""Servidor Language Server Protocol (LSP) da GALO.

Implementação mínima e sem dependências, sobre JSON-RPC 2.0 em stdin/stdout:
  * diagnósticos (erros e avisos) ao abrir, editar e salvar arquivos;
  * autocompletar (palavras-chave, funções internas, nomes do documento, modelos);
  * informações ao passar o mouse (hover) sobre funções internas e palavras-chave.

Uso: galo lsp   (o editor inicia o processo e conversa com ele)
"""

from __future__ import annotations

import json
import re
import sys
from urllib.parse import unquote, urlparse

from .. import __version__
from ..compiler import check_source
from ..compiler.tokens import CONTEXTUAL_WORDS, KEYWORDS, canonical
from ..stdlib import BUILTINS, CONSTANTS

# Tipos de item de autocompletar (numeração do LSP)
K_FUNCTION, K_VARIABLE, K_KEYWORD, K_SNIPPET, K_CONSTANT = 3, 6, 14, 15, 21

KEYWORD_HELP = {
    "defina": "Declara uma variável: `defina nome como valor`",
    "constante": "Declara uma constante (não pode mudar): `constante PI como 3.14`",
    "mostre": "Mostra valores na tela: `mostre \"Olá\", nome`",
    "se": "Condicional: `se condição então ... senão ... fim`",
    "enquanto": "Repete enquanto a condição for verdadeira: `enquanto condição faça ... fim`",
    "para": "Laço: `para i de 1 até 10 faça ... fim` ou `para cada x em lista faça ... fim`",
    "repita": "Repete um número de vezes: `repita 3 vezes ... fim`",
    "função": "Define uma função: `função nome(a, b) retorna tipo ... fim`",
    "retorne": "Devolve um valor de dentro de uma função",
    "pare": "Interrompe o laço atual",
    "continue": "Pula para a próxima volta do laço atual",
    "tente": "Trata erros: `tente ... capture erro ... fim`",
    "lance": "Lança um erro: `lance \"mensagem\"`",
    "importe": "Usa outro arquivo: `importe \"util.galo\" como util` ou `importe a, b de \"util.galo\"`",
    "registro": "Define um tipo com campos e métodos: `registro Pessoa ... fim`",
    "eu": "Dentro de um método, a instância que recebeu a chamada: `eu.campo`",
}

SNIPPETS = [
    ("se", "se ${1:condição} então\n\t$0\nfim", "Condicional"),
    ("se/senão", "se ${1:condição} então\n\t$2\nsenão\n\t$0\nfim", "Condicional com senão"),
    ("enquanto", "enquanto ${1:condição} faça\n\t$0\nfim", "Laço enquanto"),
    ("para", "para ${1:i} de ${2:1} até ${3:10} faça\n\t$0\nfim", "Laço numérico"),
    ("para cada", "para cada ${1:item} em ${2:lista} faça\n\t$0\nfim", "Percorre uma coleção"),
    ("função", "função ${1:nome}(${2:parâmetros})\n\t$0\nfim", "Nova função"),
    ("tente", "tente\n\t$1\ncapture ${2:erro}\n\tmostre ${2:erro}.mensagem\nfim", "Tratamento de erros"),
    ("registro", "registro ${1:Nome}\n\t${2:campo} como ${3:texto}\n\n\tfunção ${4:método}()\n\t\t$0\n\tfim\nfim", "Novo registro"),
    ("importe", 'importe "${1:arquivo}.galo" como ${2:nome}', "Importar um módulo"),
    ("rota", 'app.get("${1:/caminho}", função(pedido)\n\t$0\nfim)', "Rota do servidor web"),
]

_WORD = re.compile(r"[^\W\d]\w*", re.UNICODE)


def _utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _to_utf16_col(line_text: str, col: int) -> int:
    """Converte coluna (pontos de código, base 0) para unidades UTF-16 (padrão do LSP)."""
    return _utf16_len(line_text[:col])


def _from_utf16_col(line_text: str, units: int) -> int:
    count = 0
    for i, ch in enumerate(line_text):
        if count >= units:
            return i
        count += 2 if ord(ch) > 0xFFFF else 1
    return len(line_text)


def _uri_to_name(uri: str) -> str:
    parsed = urlparse(uri)
    if parsed.scheme == "file":
        return unquote(parsed.path).rsplit("/", 1)[-1]
    return uri


def _uri_to_dir(uri: str) -> str | None:
    import os

    parsed = urlparse(uri)
    if parsed.scheme == "file":
        path = unquote(parsed.path)
        if os.name == "nt" and path.startswith("/") and len(path) > 2 and path[2] == ":":
            path = path[1:]
        return os.path.dirname(path)
    return None


class Server:
    def __init__(self, inp, out) -> None:
        self.inp = inp
        self.out = out
        self.docs: dict[str, str] = {}
        self.shutting_down = False

    # ------------------------------------------------------------ transporte

    def read_message(self):
        headers = {}
        while True:
            line = self.inp.readline()
            if not line:
                return None
            line = line.decode("ascii", "replace").strip()
            if not line:
                break
            name, _, value = line.partition(":")
            headers[name.strip().lower()] = value.strip()
        length = int(headers.get("content-length", "0"))
        body = self.inp.read(length) if length else b""
        try:
            return json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def send(self, message: dict) -> None:
        data = json.dumps(message, ensure_ascii=False).encode("utf-8")
        self.out.write(b"Content-Length: " + str(len(data)).encode("ascii") + b"\r\n\r\n" + data)
        self.out.flush()

    def respond(self, msg_id, result=None, error=None) -> None:
        message = {"jsonrpc": "2.0", "id": msg_id}
        if error is not None:
            message["error"] = error
        else:
            message["result"] = result
        self.send(message)

    def notify(self, method: str, params: dict) -> None:
        self.send({"jsonrpc": "2.0", "method": method, "params": params})

    # ------------------------------------------------------------ laço

    def run(self) -> int:
        while True:
            msg = self.read_message()
            if msg is None:
                return 0 if self.shutting_down else 1
            if msg.get("method") == "exit":
                return 0 if self.shutting_down else 1
            try:
                self.handle(msg)
            except Exception as exc:  # pragma: no cover - nunca derrubar o editor
                if msg.get("id") is not None:
                    self.respond(msg["id"], error={"code": -32603, "message": f"erro interno: {exc}"})

    def handle(self, msg: dict) -> None:
        method = msg.get("method")
        msg_id = msg.get("id")
        params = msg.get("params") or {}
        if method == "initialize":
            self.respond(msg_id, {
                "capabilities": {
                    "textDocumentSync": {"openClose": True, "change": 1, "save": {"includeText": True}},
                    "completionProvider": {"triggerCharacters": ["."]},
                    "hoverProvider": True,
                },
                "serverInfo": {"name": "galo-lsp", "version": __version__},
            })
        elif method == "initialized":
            pass
        elif method == "shutdown":
            self.shutting_down = True
            self.respond(msg_id, None)
        elif method == "textDocument/didOpen":
            doc = params["textDocument"]
            self.docs[doc["uri"]] = doc.get("text", "")
            self.publish(doc["uri"])
        elif method == "textDocument/didChange":
            uri = params["textDocument"]["uri"]
            changes = params.get("contentChanges") or []
            if changes:
                self.docs[uri] = changes[-1].get("text", "")
            self.publish(uri)
        elif method == "textDocument/didSave":
            uri = params["textDocument"]["uri"]
            if "text" in params:
                self.docs[uri] = params["text"]
            self.publish(uri)
        elif method == "textDocument/didClose":
            uri = params["textDocument"]["uri"]
            self.docs.pop(uri, None)
            self.notify("textDocument/publishDiagnostics", {"uri": uri, "diagnostics": []})
        elif method == "textDocument/completion":
            self.respond(msg_id, {"isIncomplete": False, "items": self.completions(params)})
        elif method == "textDocument/hover":
            self.respond(msg_id, self.hover(params))
        elif msg_id is not None:
            self.respond(msg_id, error={"code": -32601, "message": f"método não suportado: {method}"})

    # ------------------------------------------------------------ recursos

    def diagnostics(self, uri: str) -> list[dict]:
        text = self.docs.get(uri, "")
        lines = text.splitlines() or [""]
        out = []
        name = _uri_to_name(uri)
        for d in check_source(text, name, base_dir=_uri_to_dir(uri)):
            if d.file not in (None, name):
                # Erro em um módulo importado: aparece na primeira linha deste documento.
                d.message = f"Erro no módulo '{d.file}' (linha {d.line}): {d.message}"
                d.line, d.col, d.length = 1, 1, 1
            line = max(0, (d.line or 1) - 1)
            line_text = lines[line] if line < len(lines) else ""
            col = max(0, (d.col or 1) - 1)
            start = _to_utf16_col(line_text, col)
            end = _to_utf16_col(line_text, min(len(line_text), col + d.length)) if col < len(line_text) else start + 1
            message = d.message + (f"\nSugestão: {d.suggestion}" if d.suggestion else "")
            out.append({
                "range": {"start": {"line": line, "character": start}, "end": {"line": line, "character": max(end, start + 1)}},
                "severity": 2 if d.is_warning else 1,
                "code": d.code,
                "source": "galo",
                "message": message,
            })
        return out

    def publish(self, uri: str) -> None:
        self.notify("textDocument/publishDiagnostics", {"uri": uri, "diagnostics": self.diagnostics(uri)})

    def completions(self, params: dict) -> list[dict]:
        items: list[dict] = []
        seen: set[str] = set()

        def add(label, kind, detail=None, doc=None, insert=None, snippet=False):
            if label in seen:
                return
            seen.add(label)
            item = {"label": label, "kind": kind}
            if detail:
                item["detail"] = detail
            if doc:
                item["documentation"] = {"kind": "markdown", "value": doc}
            if insert:
                item["insertText"] = insert
                item["insertTextFormat"] = 2 if snippet else 1
            items.append(item)

        for label, body, detail in SNIPPETS:
            add(label, K_SNIPPET, detail, f"```galo\n{body}\n```", body, snippet=True)
        for kw in KEYWORDS + CONTEXTUAL_WORDS:
            add(kw, K_KEYWORD, "palavra-chave", KEYWORD_HELP.get(kw))
        for nf in BUILTINS.values():
            add(nf.name, K_FUNCTION, nf.signature, nf.doc)
        for name, value, doc in CONSTANTS.values():
            add(name, K_CONSTANT, "constante", doc)
        text = self.docs.get(params.get("textDocument", {}).get("uri", ""), "")
        keyword_keys = {canonical(k) for k in KEYWORDS}
        for word in sorted(set(_WORD.findall(_strip_strings_and_comments(text)))):
            if canonical(word) not in keyword_keys:
                add(word, K_VARIABLE, "nome do documento")
        return items

    def hover(self, params: dict):
        uri = params.get("textDocument", {}).get("uri", "")
        pos = params.get("position", {})
        lines = self.docs.get(uri, "").splitlines()
        line_no = pos.get("line", 0)
        if line_no >= len(lines):
            return None
        line = lines[line_no]
        col = _from_utf16_col(line, pos.get("character", 0))
        for m in _WORD.finditer(line):
            if m.start() <= col <= m.end():
                key = canonical(m.group())
                if key in BUILTINS:
                    nf = BUILTINS[key]
                    return {"contents": {"kind": "markdown", "value": f"```galo\n{nf.signature}\n```\n{nf.doc}"}}
                if key in CONSTANTS:
                    name, value, doc = CONSTANTS[key]
                    return {"contents": {"kind": "markdown", "value": f"**{name}** — {doc}"}}
                for kw, help_text in KEYWORD_HELP.items():
                    if canonical(kw) == key:
                        return {"contents": {"kind": "markdown", "value": help_text}}
                return None
        return None


def _strip_strings_and_comments(text: str) -> str:
    text = re.sub(r"#\[.*?\]#", " ", text, flags=re.S)
    text = re.sub(r"#.*", " ", text)
    return re.sub(r'"(?:\\.|[^"\\\n])*"', " ", text)


def serve() -> int:
    return Server(sys.stdin.buffer, sys.stdout.buffer).run()
