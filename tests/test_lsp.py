"""Testa o servidor LSP conversando com ele por um processo real."""

import json
import os
import subprocess
import sys
import unittest

from auxiliar import RAIZ


class ClienteLSP:
    def __init__(self):
        env = dict(os.environ, PYTHONPATH=RAIZ)
        self.proc = subprocess.Popen([sys.executable, "-m", "galo", "lsp"], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        self.next_id = 1

    def enviar(self, msg):
        data = json.dumps(msg).encode("utf-8")
        self.proc.stdin.write(b"Content-Length: %d\r\n\r\n" % len(data) + data)
        self.proc.stdin.flush()

    def receber(self):
        headers = {}
        while True:
            line = self.proc.stdout.readline().decode("ascii").strip()
            if not line:
                break
            k, _, v = line.partition(":")
            headers[k.lower()] = v.strip()
        return json.loads(self.proc.stdout.read(int(headers["content-length"])).decode("utf-8"))

    def pedir(self, method, params):
        msg_id = self.next_id
        self.next_id += 1
        self.enviar({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params})
        while True:
            msg = self.receber()
            if msg.get("id") == msg_id:
                return msg

    def avisar(self, method, params):
        self.enviar({"jsonrpc": "2.0", "method": method, "params": params})

    def encerrar(self):
        self.pedir("shutdown", None)
        self.avisar("exit", None)
        return self.proc.wait(timeout=10)


class TestLSP(unittest.TestCase):
    def setUp(self):
        self.c = ClienteLSP()
        resp = self.c.pedir("initialize", {"processId": None, "rootUri": None, "capabilities": {}})
        self.assertIn("capabilities", resp["result"])
        self.c.avisar("initialized", {})

    def tearDown(self):
        if self.c.proc.poll() is None:
            self.c.proc.kill()
            self.c.proc.wait()
        for stream in (self.c.proc.stdin, self.c.proc.stdout, self.c.proc.stderr):
            stream.close()

    def test_diagnosticos_ao_abrir_e_editar(self):
        uri = "file:///tmp/teste.galo"
        self.c.avisar("textDocument/didOpen", {"textDocument": {
            "uri": uri, "languageId": "galo", "version": 1, "text": "defina ação como 1\nmostre açao + pontos\n"}})
        msg = self.c.receber()
        self.assertEqual(msg["method"], "textDocument/publishDiagnostics")
        (d,) = msg["params"]["diagnostics"]
        self.assertEqual(d["code"], "G201")
        self.assertEqual(d["range"]["start"], {"line": 1, "character": 14})
        self.assertEqual(d["severity"], 1)
        self.c.avisar("textDocument/didChange", {"textDocument": {"uri": uri, "version": 2},
                                                 "contentChanges": [{"text": "mostre 1\n"}]})
        msg = self.c.receber()
        self.assertEqual(msg["params"]["diagnostics"], [])
        self.assertEqual(self.c.encerrar(), 0)

    def test_erro_de_sintaxe_e_aviso(self):
        self.c.avisar("textDocument/didOpen", {"textDocument": {
            "uri": "file:///x.galo", "languageId": "galo", "version": 1, "text": "se x > 1\nfim\n"}})
        d = self.c.receber()["params"]["diagnostics"][0]
        self.assertEqual(d["code"], "G102")
        self.c.avisar("textDocument/didChange", {"textDocument": {"uri": "file:///x.galo", "version": 2},
                                                 "contentChanges": [{"text": 'defina texto como "a"\nmostre texto\n'}]})
        d = self.c.receber()["params"]["diagnostics"][0]
        self.assertEqual((d["code"], d["severity"]), ("A201", 2))
        self.c.encerrar()

    def test_autocompletar_e_hover(self):
        uri = "file:///y.galo"
        self.c.avisar("textDocument/didOpen", {"textDocument": {
            "uri": uri, "languageId": "galo", "version": 1, "text": "defina minha_variavel como 1\nmostre tamanho([1])\n"}})
        self.c.receber()
        itens = self.c.pedir("textDocument/completion", {"textDocument": {"uri": uri}, "position": {"line": 1, "character": 0}})
        rotulos = {i["label"] for i in itens["result"]["items"]}
        self.assertTrue({"enquanto", "tamanho", "mapear", "minha_variavel", "pi", "para cada"} <= rotulos)
        hover = self.c.pedir("textDocument/hover", {"textDocument": {"uri": uri}, "position": {"line": 1, "character": 9}})
        self.assertIn("tamanho(valor)", hover["result"]["contents"]["value"])
        self.c.encerrar()


if __name__ == "__main__":
    unittest.main()
