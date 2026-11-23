"""Web: servidor HTTP com rotas, respostas, cliente HTTP e entrega de GALO para o navegador.

    defina app como criar_servidor()
    app.rota("GET", "/api/tarefas/<id:inteiro>", função(pedido)
        retorne {"id": pedido.parâmetros.id}
    fim)
    app.arquivos("/", "publico")        # arquivos estáticos
    app.cliente("/app.galoc", "cliente.galo")   # programa GALO que roda no navegador
    app.iniciar(8000)

Uma rota recebe um `pedido` (mapa) e devolve: um texto (HTML), um mapa/lista/registro
(JSON), nulo (204) ou uma resposta criada por resposta(), resposta_json(),
resposta_html() ou redirecionar().
"""

from __future__ import annotations

import mimetypes
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, unquote, urlsplit

from ..errors import GaloExit, GaloRuntimeError, format_short
from ..runtime.values import GaloMapa, GaloObjetoNativo, GaloRegistro, article, display, type_name
from . import dados_json
from ._util import erro, exige_funcao, exige_inteiro, exige_mapa, exige_texto
from .registry import nativa

STATUS_TEXTO = {200: "OK", 201: "Created", 204: "No Content", 301: "Moved Permanently", 302: "Found",
                303: "See Other", 400: "Bad Request", 401: "Unauthorized", 403: "Forbidden", 404: "Not Found",
                405: "Method Not Allowed", 409: "Conflict", 422: "Unprocessable Entity", 500: "Internal Server Error"}


# ---------------------------------------------------------------- respostas


class Resposta:
    __slots__ = ("status", "cabecalhos", "corpo")

    def __init__(self, status: int, cabecalhos: dict, corpo: bytes) -> None:
        self.status = status
        self.cabecalhos = cabecalhos
        self.corpo = corpo


def _objeto_resposta(r: Resposta) -> GaloObjetoNativo:
    obj = GaloObjetoNativo("Resposta", r)
    obj.propriedade("status", lambda: r.status)
    obj.propriedade("corpo", lambda: r.corpo.decode("utf-8", "replace"))
    obj.propriedade("cabeçalhos", lambda: GaloMapa.from_pairs(r.cabecalhos.items()))
    return obj


def _cabecalhos(fname, cabecalhos) -> dict:
    if cabecalhos is None:
        return {}
    exige_mapa(fname, 3, cabecalhos)
    return {str(k): display(v) for k, v in cabecalhos.items()}


def _status(fname, status):
    exige_inteiro(fname, 2, status)
    if not 100 <= status <= 599:
        raise erro("G322", f"O código de status HTTP {status} é inválido (use de 100 a 599).")
    return status


@nativa("resposta", assinatura="resposta(corpo, [status], [cabeçalhos])")
def resposta(vm, corpo, status=200, cabecalhos=None):
    """Resposta HTTP completa. Textos são enviados como estão (HTML por padrão);
    mapas, listas e registros viram JSON."""
    h = _cabecalhos("resposta", cabecalhos)
    if type(corpo) is str:
        dados = corpo.encode("utf-8")
        h.setdefault("Content-Type", "text/html; charset=utf-8")
    elif corpo is None:
        dados = b""
    else:
        dados = dados_json.codificar(corpo).encode("utf-8")
        h.setdefault("Content-Type", "application/json; charset=utf-8")
    return _objeto_resposta(Resposta(_status("resposta", status), h, dados))


@nativa("resposta_json", assinatura="resposta_json(valor, [status], [cabeçalhos])")
def resposta_json(vm, valor, status=200, cabecalhos=None):
    """Resposta HTTP com o valor convertido em JSON."""
    h = _cabecalhos("resposta_json", cabecalhos)
    h["Content-Type"] = "application/json; charset=utf-8"
    return _objeto_resposta(Resposta(_status("resposta_json", status), h, dados_json.codificar(valor).encode("utf-8")))


@nativa("resposta_html", assinatura="resposta_html(texto, [status], [cabeçalhos])")
def resposta_html(vm, texto, status=200, cabecalhos=None):
    """Resposta HTTP com uma página HTML."""
    h = _cabecalhos("resposta_html", cabecalhos)
    h["Content-Type"] = "text/html; charset=utf-8"
    return _objeto_resposta(Resposta(_status("resposta_html", status), h, display(texto).encode("utf-8")))


@nativa("redirecionar", assinatura="redirecionar(endereço, [status])")
def redirecionar(vm, endereco, status=303):
    """Resposta que manda o navegador para outro endereço (útil depois de enviar formulários)."""
    exige_texto("redirecionar", 1, endereco)
    return _objeto_resposta(Resposta(_status("redirecionar", status), {"Location": endereco}, b""))


def _converter_retorno(valor) -> Resposta:
    if type(valor) is GaloObjetoNativo and valor.tipo == "Resposta":
        return valor.dados
    if type(valor) is str:
        return Resposta(200, {"Content-Type": "text/html; charset=utf-8"}, valor.encode("utf-8"))
    if valor is None:
        return Resposta(204, {}, b"")
    if type(valor) in (GaloMapa, list, GaloRegistro, int, float, bool):
        return Resposta(200, {"Content-Type": "application/json; charset=utf-8"},
                        dados_json.codificar(valor).encode("utf-8"))
    raise erro("G326", f"Uma rota devolveu {article(type_name(valor))}, que não pode ser enviado como resposta.",
               "Devolva um texto (HTML), um mapa/lista (JSON), nulo ou use resposta(...).")


def _json_erro(status: int, mensagem: str, extra: dict | None = None) -> Resposta:
    corpo = {"erro": mensagem, **(extra or {})}
    import json

    return Resposta(status, {"Content-Type": "application/json; charset=utf-8"},
                    json.dumps(corpo, ensure_ascii=False).encode("utf-8"))


# ---------------------------------------------------------------- servidor


class _Rota:
    __slots__ = ("metodo", "padrao", "regex", "parametros", "funcao")

    def __init__(self, metodo: str, padrao: str, funcao) -> None:
        self.metodo = metodo
        self.padrao = padrao
        self.funcao = funcao
        self.parametros: list[tuple[str, str]] = []
        partes = []
        pos = 0
        for m in re.finditer(r"<([^<>:]+)(?::(inteiro|texto|caminho))?>", padrao):
            partes.append(re.escape(padrao[pos:m.start()]))
            nome, tipo = m.group(1).strip(), m.group(2) or "texto"
            self.parametros.append((nome, tipo))
            partes.append({"inteiro": r"(-?\d+)", "texto": r"([^/]+)", "caminho": r"(.+)"}[tipo])
            pos = m.end()
        partes.append(re.escape(padrao[pos:]))
        self.regex = re.compile("".join(partes) + "/?" if not padrao.endswith("/") else "".join(partes))


class _Servidor:
    def __init__(self, vm) -> None:
        self.vm = vm
        self.rotas: list[_Rota] = []
        self.estaticos: list[tuple[str, str]] = []
        self.antes: list = []
        self.clientes: dict[str, str] = {}
        self.cache_clientes: dict[str, tuple] = {}
        self.http: ThreadingHTTPServer | None = None
        self.trava = threading.Lock()
        self.saida: GaloExit | None = None

    # -- despacho (usado pelo servidor real e por testar()) --

    def despachar(self, metodo: str, alvo: str, cabecalhos: dict, corpo: bytes) -> Resposta:
        with self.trava:
            try:
                return self._despachar(metodo.upper(), alvo, cabecalhos, corpo)
            except GaloExit as ex:
                self.saida = ex
                self.parar()
                return _json_erro(503, "O servidor está sendo encerrado.")
            except GaloRuntimeError as err:
                sys.stderr.write(f"[GALO] erro em {metodo} {alvo}: {format_short(err)}\n")
                if os.environ.get("GALO_PRODUCAO"):
                    return _json_erro(500, "Erro interno no servidor.")
                return _json_erro(500, err.message, {"código": err.code, "linha": err.line})

    def _despachar(self, metodo, alvo, cabecalhos, corpo) -> Resposta:
        partes = urlsplit(alvo)
        caminho = unquote(partes.path) or "/"
        if caminho == "/_galo/galo.js":
            from ..web import runtime_js

            return Resposta(200, {"Content-Type": "application/javascript; charset=utf-8"}, runtime_js())
        if caminho in self.clientes and metodo in ("GET", "HEAD"):
            return self._cliente(caminho)
        com_caminho = [r for r in self.rotas if r.regex.fullmatch(caminho)]
        rota = next((r for r in com_caminho if r.metodo in (metodo, "*") or (metodo == "HEAD" and r.metodo == "GET")), None)
        if rota is None:
            if metodo in ("GET", "HEAD"):
                estatico = self._estatico(caminho)
                if estatico is not None:
                    return estatico
            if com_caminho:
                permitidos = sorted({r.metodo for r in com_caminho})
                r = _json_erro(405, f"Método {metodo} não permitido para {caminho}.")
                r.cabecalhos["Allow"] = ", ".join(permitidos)
                return r
            return _json_erro(404, f"Nada encontrado em {caminho}.")
        m = rota.regex.fullmatch(caminho)
        parametros = GaloMapa()
        for (nome, tipo), valor in zip(rota.parametros, m.groups()):
            parametros.set(nome, int(valor) if tipo == "inteiro" else valor)
        pedido = self._pedido(metodo, caminho, partes.query, cabecalhos, corpo, parametros)
        for funcao in self.antes:
            r = self.vm.call_value(funcao, [pedido])
            if r is not None:
                return _converter_retorno(r)
        return _converter_retorno(self.vm.call_value(rota.funcao, [pedido]))

    def _pedido(self, metodo, caminho, consulta, cabecalhos, corpo, parametros) -> GaloMapa:
        texto = corpo.decode("utf-8", "replace")
        tipo = cabecalhos.get("content-type", "")
        dados_json_ = None
        if "application/json" in tipo and texto.strip():
            try:
                dados_json_ = dados_json.decodificar(texto)
            except GaloRuntimeError:
                dados_json_ = None
        formulario = GaloMapa()
        if "application/x-www-form-urlencoded" in tipo:
            for k, v in parse_qsl(texto, keep_blank_values=True):
                formulario.set(k, v)
        cookies = GaloMapa()
        if "cookie" in cabecalhos:
            c = SimpleCookie()
            try:
                c.load(cabecalhos["cookie"])
            except Exception:
                pass
            for k, morsel in c.items():
                cookies.set(k, morsel.value)
        return GaloMapa.from_pairs([
            ("método", metodo), ("caminho", caminho), ("parâmetros", parametros),
            ("consulta", GaloMapa.from_pairs(parse_qsl(consulta, keep_blank_values=True))),
            ("cabeçalhos", GaloMapa.from_pairs(cabecalhos.items())), ("corpo", texto),
            ("json", dados_json_), ("formulário", formulario), ("cookies", cookies),
        ])

    def _arquivo(self, caminho: str, tipo: str | None = None) -> Resposta:
        try:
            with open(caminho, "rb") as f:
                dados = f.read()
        except OSError:
            return _json_erro(404, "Arquivo não encontrado.")
        tipo = tipo or (mimetypes.guess_type(caminho)[0] or "application/octet-stream")
        if tipo.startswith("text/") and "charset" not in tipo:
            tipo += "; charset=utf-8"
        return Resposta(200, {"Content-Type": tipo}, dados)

    def _estatico(self, caminho: str) -> Resposta | None:
        for prefixo, pasta in self.estaticos:
            base = prefixo.rstrip("/")
            if caminho != base and not caminho.startswith(base + "/"):
                continue
            relativo = caminho[len(base):].lstrip("/") or "index.html"
            alvo = os.path.realpath(os.path.join(pasta, relativo))
            raiz = os.path.realpath(pasta)
            if alvo != raiz and not alvo.startswith(raiz + os.sep):
                return _json_erro(403, "Acesso negado.")  # tentativa de sair da pasta (../)
            if os.path.isdir(alvo):
                alvo = os.path.join(alvo, "index.html")
            if os.path.isfile(alvo):
                return self._arquivo(alvo)
        return None

    def _cliente(self, url: str) -> Resposta:
        from ..compiler import compile_source
        from ..compiler.bytecode import dump_module
        from ..errors import CompilationError, format_diagnostic

        fonte = self.clientes[url]
        cache = self.cache_clientes.get(url)
        if cache is not None and all(os.path.getmtime(p) == t for p, t in cache[0] if os.path.exists(p)):
            return Resposta(200, {"Content-Type": "application/octet-stream", "Cache-Control": "no-cache"}, cache[1])
        try:
            with open(fonte, encoding="utf-8") as f:
                codigo = f.read()
            resultado = compile_source(codigo, os.path.basename(fonte), base_dir=os.path.dirname(fonte))
        except OSError:
            return _json_erro(500, f"Não foi possível ler {fonte}.")
        except CompilationError as exc:
            mensagens = [format_diagnostic(e, getattr(exc, "sources", {}).get(e.file)) for e in exc.errors]
            for m in mensagens:
                sys.stderr.write(m + "\n\n")
            return Resposta(500, {"Content-Type": "text/plain; charset=utf-8"}, "\n\n".join(mensagens).encode("utf-8"))
        dados = dump_module(resultado.module)
        arquivos = [os.path.abspath(fonte)] + [
            os.path.join(os.path.dirname(os.path.abspath(fonte)), m.name) for m in resultado.module.modules]
        self.cache_clientes[url] = ([(p, os.path.getmtime(p)) for p in arquivos if os.path.exists(p)], dados)
        return Resposta(200, {"Content-Type": "application/octet-stream", "Cache-Control": "no-cache"}, dados)

    # -- rede --

    def iniciar(self, porta: int, host: str) -> None:
        servidor = self

        class Manipulador(BaseHTTPRequestHandler):
            server_version = "GALO"
            sys_version = ""

            def _tratar(self):
                inicio = time.perf_counter()
                tamanho = int(self.headers.get("Content-Length") or 0)
                corpo = self.rfile.read(tamanho) if tamanho > 0 else b""
                cab = {k.lower(): v for k, v in self.headers.items()}
                r = servidor.despachar(self.command, self.path, cab, corpo)
                self.send_response(r.status, STATUS_TEXTO.get(r.status))
                for k, v in r.cabecalhos.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(r.corpo)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(r.corpo)
                ms = (time.perf_counter() - inicio) * 1000
                sys.stderr.write(f"{self.command} {self.path} -> {r.status} ({ms:.0f} ms)\n")

            do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _tratar

            def log_message(self, *args):
                pass

        try:
            self.http = ThreadingHTTPServer((host, porta), Manipulador)
        except OSError as exc:
            raise erro("G326", f"Não foi possível iniciar o servidor em {host}:{porta}: {exc.strerror or exc}.",
                       "A porta pode estar em uso por outro programa. Tente outra porta.")
        # Ao encerrar, espera as respostas em andamento terminarem de ser enviadas.
        self.http.daemon_threads = False
        self.http.block_on_close = True
        endereco = f"http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{self.http.server_address[1]}"
        sys.stderr.write(f"Servidor GALO em {endereco}  (Ctrl+C para parar)\n")
        sys.stderr.flush()
        self.vm.flush()
        try:
            self.http.serve_forever(poll_interval=0.2)
        except KeyboardInterrupt:
            sys.stderr.write("\nServidor encerrado.\n")
        finally:
            self.http.server_close()
            self.http = None
        if self.saida is not None:
            raise self.saida

    def parar(self) -> None:
        if self.http is not None:
            threading.Thread(target=self.http.shutdown, daemon=True).start()


def _criar_servidor(vm) -> GaloObjetoNativo:
    s = _Servidor(vm)
    obj = GaloObjetoNativo("Servidor", s)

    def rota(vm, _o, metodo, caminho, funcao):
        exige_texto("rota", 1, metodo)
        exige_texto("rota", 2, caminho)
        exige_funcao("rota", 3, funcao)
        if not caminho.startswith("/"):
            raise erro("G322", f"O caminho da rota deve começar com '/': \"{caminho}\".")
        s.rotas.append(_Rota(metodo.upper(), caminho, funcao))
        return None

    def atalho(metodo):
        return lambda vm, _o, caminho, funcao: rota(vm, _o, metodo, caminho, funcao)

    def arquivos(vm, _o, prefixo, pasta):
        exige_texto("arquivos", 1, prefixo)
        exige_texto("arquivos", 2, pasta)
        real = vm.resolve_path(pasta)
        if not os.path.isdir(real):
            raise erro("G326", f'A pasta de arquivos estáticos "{pasta}" não existe.')
        s.estaticos.append((prefixo, real))
        return None

    def antes(vm, _o, funcao):
        s.antes.append(exige_funcao("antes", 1, funcao))
        return None

    def cliente(vm, _o, url, arquivo):
        exige_texto("cliente", 1, url)
        exige_texto("cliente", 2, arquivo)
        real = vm.resolve_path(arquivo)
        if not os.path.isfile(real):
            raise erro("G326", f'O programa do navegador "{arquivo}" não existe.')
        s.clientes[url] = real
        return None

    def iniciar(vm, _o, porta=8000, host="127.0.0.1"):
        exige_inteiro("iniciar", 1, porta)
        exige_texto("iniciar", 2, host)
        s.iniciar(porta, host)
        return None

    def parar(vm, _o):
        s.parar()
        return None

    def testar(vm, _o, metodo, caminho, corpo=None, cabecalhos=None):
        exige_texto("testar", 1, metodo)
        exige_texto("testar", 2, caminho)
        cab = {str(k).lower(): display(v) for k, v in (exige_mapa("testar", 4, cabecalhos).items() if cabecalhos else [])}
        if corpo is None:
            dados = b""
        elif type(corpo) is str:
            dados = corpo.encode("utf-8")
        else:
            dados = dados_json.codificar(corpo).encode("utf-8")
            cab.setdefault("content-type", "application/json")
        r = s.despachar(metodo, caminho, cab, dados)
        return _resultado_http(r.status, r.cabecalhos, r.corpo)

    obj.metodo("rota", rota, 3, 3, ("nulo",), "Registra uma função para um método HTTP e um caminho.")
    for metodo in ("get", "post", "put", "delete", "patch"):
        obj.metodo(metodo, atalho(metodo.upper()), 2, 2, ("nulo",), f"Atalho para rota(\"{metodo.upper()}\", ...).")
    obj.metodo("arquivos", arquivos, 2, 2, ("nulo",), "Serve os arquivos de uma pasta a partir de um prefixo de URL.")
    obj.metodo("antes", antes, 1, 1, ("nulo",), "Função executada antes de toda rota; se devolver algo, responde no lugar dela.")
    obj.metodo("cliente", cliente, 2, 2, ("nulo",), "Compila e entrega um programa GALO para o navegador.")
    obj.metodo("iniciar", iniciar, 0, 2, ("nulo",), "Inicia o servidor (bloqueia até Ctrl+C ou parar()).")
    obj.metodo("parar", parar, 0, 0, ("nulo",), "Encerra o servidor.")
    obj.metodo("testar", testar, 2, 4, ("mapa",), "Simula um pedido HTTP sem rede e devolve a resposta (útil em testes).")
    return obj


@nativa("criar_servidor", assinatura="criar_servidor()")
def criar_servidor(vm):
    """Cria um servidor web. Métodos: rota(método, caminho, função), get/post/put/delete/patch(caminho, função),
    arquivos(prefixo, pasta), antes(função), cliente(url, arquivo.galo), iniciar([porta], [host]), parar()
    e testar(método, caminho, [corpo], [cabeçalhos])."""
    return _criar_servidor(vm)


# ---------------------------------------------------------------- cliente HTTP


def _resultado_http(status: int, cabecalhos, corpo: bytes) -> GaloMapa:
    texto = corpo.decode("utf-8", "replace")
    cab = GaloMapa.from_pairs((k.lower(), v) for k, v in dict(cabecalhos).items())
    tipo = cab.get("content-type") if cab.contains("content-type") else ""
    valor_json = None
    if isinstance(tipo, str) and "json" in tipo and texto.strip():
        try:
            valor_json = dados_json.decodificar(texto)
        except GaloRuntimeError:
            valor_json = None
    return GaloMapa.from_pairs([("status", status), ("ok", 200 <= status < 300), ("corpo", texto),
                                ("cabeçalhos", cab), ("json", valor_json)])


def requisicao(url: str, opcoes) -> GaloMapa:
    from ..runtime.values import MISSING

    if opcoes is None:
        opcoes = GaloMapa()
    exige_mapa("requisitar", 2, opcoes)

    def opt(*nomes):
        for n in nomes:
            v = opcoes.get(n)
            if v is not MISSING:
                return v
        return None

    if not url.startswith(("http://", "https://")):
        raise erro("G325", f'Endereço inválido: "{url}".', "O endereço deve começar com http:// ou https://.")
    metodo = (opt("método", "metodo") or "GET").upper()
    cab = {str(k): display(v) for k, v in (opt("cabeçalhos", "cabecalhos") or GaloMapa()).items()}
    dados = None
    if opt("json") is not None:
        dados = dados_json.codificar(opt("json")).encode("utf-8")
        cab.setdefault("Content-Type", "application/json")
    elif opt("corpo") is not None:
        corpo = opt("corpo")
        if type(corpo) is str:
            dados = corpo.encode("utf-8")
        else:
            dados = dados_json.codificar(corpo).encode("utf-8")
            cab.setdefault("Content-Type", "application/json")
    limite = opt("tempo_limite") or 30
    pedido = urllib.request.Request(url, data=dados, headers=cab, method=metodo)
    try:
        with urllib.request.urlopen(pedido, timeout=limite) as r:
            return _resultado_http(r.status, r.headers.items(), r.read())
    except urllib.error.HTTPError as exc:
        return _resultado_http(exc.code, exc.headers.items(), exc.read())
    except urllib.error.URLError as exc:
        raise erro("G325", f'Não foi possível acessar "{url}": {exc.reason}.',
                   "Verifique o endereço e a conexão com a internet.")
    except (TimeoutError, OSError) as exc:
        raise erro("G325", f'Não foi possível acessar "{url}": {exc}.')


@nativa("requisitar", retorna="mapa", assinatura="requisitar(endereço, [opções])")
def requisitar(vm, url, opcoes=None):
    """Faz uma requisição HTTP e espera a resposta. Opções (mapa): "método", "cabeçalhos", "json"
    (valor enviado como JSON), "corpo" (texto) e "tempo_limite" (segundos).
    Devolve um mapa com status, ok, corpo, cabeçalhos e json (corpo já convertido, quando for JSON)."""
    return requisicao(exige_texto("requisitar", 1, url), opcoes)


@nativa("buscar", retorna="nulo", assinatura="buscar(endereço, opções, ao_concluir)")
def buscar(vm, url, opcoes, ao_concluir):
    """Como requisitar(), mas entrega a resposta para a função ao_concluir(resposta).
    No navegador a requisição não bloqueia a página; no servidor ela é feita na hora.
    Assim o mesmo código funciona nos dois lados. Se a rede falhar, a resposta tem
    status 0, ok falso e o campo "erro" com a explicação."""
    exige_funcao("buscar", 3, ao_concluir)
    try:
        resultado = requisicao(exige_texto("buscar", 1, url), opcoes)
    except GaloRuntimeError as exc:
        if exc.code != "G325":
            raise
        resultado = GaloMapa.from_pairs([("status", 0), ("ok", False), ("corpo", ""), ("cabeçalhos", GaloMapa()),
                                         ("json", None), ("erro", exc.message)])
    vm.call_value(ao_concluir, [resultado])
    return None
