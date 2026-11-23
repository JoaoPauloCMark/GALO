"""Cliente mínimo do Chrome DevTools Protocol (CDP), só com a biblioteca padrão.

Usado pelos testes que abrem a GALO num Chrome ou num Microsoft Edge de verdade (os dois
usam o mesmo protocolo), em modo headless e com um perfil temporário: o navegador do
usuário não é tocado.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import time
import urllib.request
from urllib.parse import urlsplit

NAVEGADORES_CHROME = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")
NAVEGADORES_EDGE = ("microsoft-edge", "microsoft-edge-stable", "msedge")


def encontrar_chrome() -> str | None:
    for nome in NAVEGADORES_CHROME:
        caminho = shutil.which(nome)
        if caminho:
            return caminho
    return None


def encontrar_edge() -> str | None:
    """Microsoft Edge instalado, ou o executável indicado em GALO_EDGE (por exemplo, extraído do .deb)."""
    indicado = os.environ.get("GALO_EDGE")
    if indicado:
        return indicado if os.access(indicado, os.X_OK) else None
    for nome in NAVEGADORES_EDGE:
        caminho = shutil.which(nome)
        if caminho:
            return caminho
    return "/opt/microsoft/msedge/msedge" if os.access("/opt/microsoft/msedge/msedge", os.X_OK) else None


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class WebSocket:
    """Cliente WebSocket (RFC 6455) suficiente para o CDP."""

    def __init__(self, url: str) -> None:
        partes = urlsplit(url)
        self.sock = socket.create_connection((partes.hostname, partes.port), timeout=30)
        chave = base64.b64encode(os.urandom(16)).decode()
        pedido = (f"GET {partes.path} HTTP/1.1\r\nHost: {partes.hostname}:{partes.port}\r\n"
                  f"Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {chave}\r\n"
                  f"Sec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(pedido.encode())
        resposta = b""
        while b"\r\n\r\n" not in resposta:
            parte = self.sock.recv(4096)
            if not parte:
                raise ConnectionError("conexão fechada durante o handshake")
            resposta += parte
        cabecalho, self.sobra = resposta.split(b"\r\n\r\n", 1)
        if b" 101 " not in cabecalho.split(b"\r\n")[0]:
            raise ConnectionError("handshake recusado: " + cabecalho.decode(errors="replace"))

    def _ler(self, n: int) -> bytes:
        dados = self.sobra
        while len(dados) < n:
            parte = self.sock.recv(max(65536, n - len(dados)))
            if not parte:
                raise ConnectionError("conexão fechada")
            dados += parte
        self.sobra = dados[n:]
        return dados[:n]

    def enviar(self, texto: str) -> None:
        dados = texto.encode()
        cab = bytearray([0x81])
        n = len(dados)
        if n < 126:
            cab.append(0x80 | n)
        elif n < 65536:
            cab.append(0x80 | 126)
            cab += struct.pack(">H", n)
        else:
            cab.append(0x80 | 127)
            cab += struct.pack(">Q", n)
        mascara = os.urandom(4)
        cab += mascara
        self.sock.sendall(bytes(cab) + bytes(b ^ mascara[i % 4] for i, b in enumerate(dados)))

    def receber(self) -> str:
        mensagem = b""
        while True:
            b1, b2 = self._ler(2)
            opcode = b1 & 0x0F
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._ler(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._ler(8))[0]
            dados = self._ler(n)
            if opcode == 0x9:  # ping
                continue
            if opcode == 0x8:
                raise ConnectionError("o navegador fechou a conexão")
            mensagem += dados
            if b1 & 0x80:
                return mensagem.decode()

    def fechar(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class Chrome:
    """Chrome (ou Edge, com `executavel`) headless isolado + sessão CDP na primeira aba."""

    def __init__(self, largura: int = 1000, altura: int = 800, executavel: str | None = None) -> None:
        executavel = executavel or encontrar_chrome()
        if not executavel:
            raise RuntimeError("Chrome/Chromium não encontrado")
        self.perfil = tempfile.mkdtemp(prefix="galo-chrome-")
        self.porta = porta_livre()
        self.proc = subprocess.Popen(
            [executavel, "--headless=new", f"--remote-debugging-port={self.porta}", f"--user-data-dir={self.perfil}",
             "--no-first-run", "--no-default-browser-check", "--disable-extensions", "--disable-sync",
             f"--window-size={largura},{altura}", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        alvos = None
        limite = time.time() + 30
        while time.time() < limite:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.porta}/json/list", timeout=2) as r:
                    alvos = [a for a in json.load(r) if a.get("type") == "page"]
                if alvos:
                    break
            except OSError:
                pass
            time.sleep(0.1)
        if not alvos:
            self.fechar()
            raise RuntimeError("o Chrome não abriu a porta de depuração")
        self.ws = WebSocket(alvos[0]["webSocketDebuggerUrl"])
        self.proximo = 0
        self.eventos: list[dict] = []
        self.ao_dialogo = None  # função(params) -> bool (aceitar?)
        for dominio in ("Page", "Runtime", "Log", "Network"):
            self.chamar(f"{dominio}.enable")

    def chamar(self, metodo: str, params: dict | None = None, limite: float = 30) -> dict:
        self.proximo += 1
        ident = self.proximo
        self.ws.enviar(json.dumps({"id": ident, "method": metodo, "params": params or {}}))
        fim = time.time() + limite
        while time.time() < fim:
            msg = json.loads(self.ws.receber())
            if msg.get("id") == ident:
                if "error" in msg:
                    raise RuntimeError(f"{metodo}: {msg['error']}")
                return msg.get("result", {})
            self._evento(msg)
        raise TimeoutError(metodo)

    def _evento(self, msg: dict) -> None:
        if "method" not in msg:
            return
        self.eventos.append(msg)
        if msg["method"] == "Page.javascriptDialogOpening":
            aceitar = self.ao_dialogo(msg["params"]) if self.ao_dialogo else False
            self.proximo += 1
            self.ws.enviar(json.dumps({"id": self.proximo, "method": "Page.handleJavaScriptDialog",
                                       "params": {"accept": bool(aceitar)}}))

    def avaliar(self, expressao: str):
        r = self.chamar("Runtime.evaluate", {"expression": expressao, "returnByValue": True, "awaitPromise": True})
        if "exceptionDetails" in r:
            raise RuntimeError("erro no JavaScript: " + json.dumps(r["exceptionDetails"])[:500])
        return r["result"].get("value")

    def esperar(self, expressao: str, limite: float = 10, descricao: str = ""):
        """Espera até a expressão JavaScript ficar verdadeira (processando eventos enquanto isso)."""
        fim = time.time() + limite
        ultimo = None
        while time.time() < fim:
            ultimo = self.avaliar(expressao)
            if ultimo:
                return ultimo
            time.sleep(0.05)
        raise TimeoutError(f"esperando {descricao or expressao} (último valor: {ultimo!r})")

    def abrir(self, url: str) -> None:
        self.chamar("Page.navigate", {"url": url})
        self.esperar("document.readyState === 'complete'", descricao="carregamento da página")

    def centro(self, seletor: str) -> tuple[float, float]:
        caixa = self.avaliar(f"(() => {{ const e = document.querySelector({json.dumps(seletor)});"
                             f" e.scrollIntoView({{block: 'center', behavior: 'instant'}}); const r = e.getBoundingClientRect();"
                             f" return [r.x + r.width / 2, r.y + r.height / 2]; }})()")
        return caixa[0], caixa[1]

    def clicar(self, seletor: str) -> None:
        """Clique real do mouse (eventos de entrada do navegador, não .click() em JavaScript)."""
        x, y = self.centro(seletor)
        for tipo in ("mouseMoved", "mousePressed", "mouseReleased"):
            self.chamar("Input.dispatchMouseEvent", {"type": tipo, "x": x, "y": y, "button": "left", "clickCount": 1})

    def digitar(self, seletor: str, texto: str) -> None:
        self.clicar(seletor)
        self.chamar("Input.insertText", {"text": texto})

    def tecla_enter(self) -> None:
        for tipo in ("keyDown", "keyUp"):
            self.chamar("Input.dispatchKeyEvent", {"type": tipo, "key": "Enter", "code": "Enter",
                                                   "windowsVirtualKeyCode": 13, "text": "\r" if tipo == "keyDown" else ""})

    def captura(self, caminho: str) -> None:
        dados = self.chamar("Page.captureScreenshot", {"format": "png"})["data"]
        with open(caminho, "wb") as f:
            f.write(base64.b64decode(dados))

    def mensagens_do_console(self) -> list[str]:
        saida = []
        for e in self.eventos:
            if e["method"] == "Runtime.consoleAPICalled":
                saida.append(f"{e['params']['type']}: " + " ".join(str(a.get("value", a.get("description", "")))
                                                                for a in e["params"]["args"]))
            elif e["method"] == "Runtime.exceptionThrown":
                saida.append("exceção: " + e["params"]["exceptionDetails"].get("text", "") + " " +
                             str(e["params"]["exceptionDetails"].get("exception", {}).get("description", "")))
            elif e["method"] == "Log.entryAdded" and e["params"]["entry"]["level"] == "error":
                saida.append("log: " + e["params"]["entry"]["text"])
        return saida

    def fechar(self) -> None:
        if getattr(self, "ws", None):
            self.ws.fechar()
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        shutil.rmtree(self.perfil, ignore_errors=True)
