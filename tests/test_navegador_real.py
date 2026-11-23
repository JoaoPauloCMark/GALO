"""A GALO em navegadores de verdade, sem janelas na tela e com perfis temporários: Chrome
(V8), Microsoft Edge, Firefox (SpiderMonkey) e WebKitGTK, o motor do Safari (WebKit +
JavaScriptCore). Os testes são pulados se o navegador não estiver instalado; o Edge pode
ser indicado pela variável GALO_EDGE (por exemplo, o msedge extraído do pacote .deb).

* Conformidade: os mesmos programas rodam na VM do navegador e na VM Python; as saídas
  precisam ser idênticas.
* Aplicativo de tarefas: digitação, tecla Enter, cliques do mouse e diálogo de confirmação
  reais (eventos nativos) no Chrome, no Edge e no WebKit, conferindo a página e o banco de dados.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from auxiliar import ESPERADO, EXEMPLOS, RAIZ, galo_cli

sys.path.insert(0, os.path.join(RAIZ, "tests", "navegador_real"))
from cdp import Chrome, encontrar_chrome, encontrar_edge  # noqa: E402
from test_web import ServidorGalo  # noqa: E402

CHROME = encontrar_chrome()
EDGE = encontrar_edge()
FIREFOX = shutil.which("firefox")
PASTA_TESTES = os.path.join(RAIZ, "tests", "navegador_real")
CONFORMIDADE = os.path.join(RAIZ, "tests", "conformidade")
EXEMPLOS_DETERMINISTICOS = ["ola_mundo", "fatorial", "fibonacci", "listas", "mapas", "maquina_turing", "brainfuck",
                            "erros", "primos", "ordenacao", "closures", "hanoi", "calculadora"]
CAPTURAS = os.environ.get("GALO_CAPTURAS")  # pasta opcional para guardar capturas de tela


def ler(caminho):
    with open(caminho, encoding="utf-8") as f:
        return f.read()


_PASTA_COMPILADOS = tempfile.mkdtemp(prefix="galo-testes-")


def _compilar_controle_webkit():
    """Compila tests/navegador_real/webkit_driver.c, o controle do WebKitGTK (o motor do Safari).

    Devolve o caminho do executável, ou None se faltar o compilador C ou o WebKitGTK.
    """
    gcc, pkg_config = shutil.which("gcc") or shutil.which("cc"), shutil.which("pkg-config")
    if not gcc or not pkg_config:
        return None
    opcoes = subprocess.run([pkg_config, "--cflags", "--libs", "webkit2gtk-4.1"], capture_output=True, text=True)
    if opcoes.returncode != 0:
        return None
    executavel = os.path.join(_PASTA_COMPILADOS, "webkit_driver")
    r = subprocess.run([gcc, "-O1", "-o", executavel, os.path.join(PASTA_TESTES, "webkit_driver.c"), *opcoes.stdout.split()],
                       capture_output=True, text=True, timeout=180)
    return executavel if r.returncode == 0 else None


WEBKIT = _compilar_controle_webkit()


def rodar_webkit(url, roteiro, limite=280):
    """Executa o roteiro no WebKitGTK e devolve a saída do controle (veja webkit_driver.c)."""
    with tempfile.TemporaryDirectory() as pasta:
        arquivo_roteiro, arquivo_saida = os.path.join(pasta, "roteiro.json"), os.path.join(pasta, "saida.json")
        with open(arquivo_roteiro, "w", encoding="utf-8") as f:
            json.dump(roteiro, f, ensure_ascii=False)
        r = subprocess.run([WEBKIT, url, arquivo_roteiro, arquivo_saida], capture_output=True, text=True, timeout=limite)
        if not os.path.exists(arquivo_saida):
            raise RuntimeError(f"o WebKit terminou sem resultado (código {r.returncode}):\n{r.stderr[-3000:]}")
        dados = json.loads(ler(arquivo_saida))
    if dados["erro"]:
        raise AssertionError(f"{dados['erro']}\ndiálogos: {dados['dialogos']}\nvalores: {dados['valores']}"
                             f"\n--- console ---\n{r.stdout[-3000:]}\n{r.stderr[-2000:]}")
    return dados


def esperar_arquivo(caminho, limite, processo=None):
    fim = time.time() + limite
    while time.time() < fim:
        if os.path.exists(caminho) and os.path.getsize(caminho) > 0:
            time.sleep(0.2)
            return json.loads(ler(caminho))
        if processo is not None and processo.poll() is not None:
            raise RuntimeError(f"o navegador terminou antes de enviar o resultado (código {processo.returncode})")
        time.sleep(0.2)
    raise TimeoutError("o navegador não enviou o resultado")


class TestConformidadeEmNavegadores(unittest.TestCase):
    """Executa exemplos e programas de conformidade na VM do navegador e compara com a VM Python."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.publica = os.path.join(cls._tmp.name, "publico")
        os.makedirs(cls.publica)
        shutil.copy(os.path.join(PASTA_TESTES, "executor.html"), os.path.join(cls.publica, "index.html"))
        programas, cls.esperado = [], {}
        fontes = [(n, os.path.join(EXEMPLOS, n + ".galo")) for n in EXEMPLOS_DETERMINISTICOS]
        fontes += [(n, os.path.join(CONFORMIDADE, n + ".galo")) for n in ("linguagem", "biblioteca", "matematica", "site")]
        for nome, fonte in fontes:
            r = galo_cli("compilar", fonte, "-o", os.path.join(cls.publica, nome + ".galoc"))
            assert r.returncode == 0, r.stderr
            entrada = os.path.join(ESPERADO, nome + ".entrada")
            linhas = ler(entrada).splitlines() if os.path.exists(entrada) else []
            programas.append({"nome": nome, "arquivo": f"/{nome}.galoc", "entradas": linhas})
            saida = os.path.join(ESPERADO, nome + ".saida")
            cls.esperado[nome] = ler(saida) if os.path.exists(saida) else galo_cli("executar", fonte).stdout
        erro = os.path.join(cls._tmp.name, "erro.galo")
        with open(erro, "w", encoding="utf-8") as f:
            f.write('defina lista como [1, 2]\nmostre lista[5]\n')
        assert galo_cli("compilar", erro, "-o", os.path.join(cls.publica, "erro.galoc")).returncode == 0
        with open(os.path.join(cls.publica, "programas.json"), "w", encoding="utf-8") as f:
            json.dump(programas, f, ensure_ascii=False)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def iniciar_servidor(self, nome):
        self.resultado = os.path.join(self._tmp.name, f"resultado-{nome}.json")
        if os.path.exists(self.resultado):
            os.remove(self.resultado)
        return ServidorGalo(os.path.join(PASTA_TESTES, "servidor_testes.galo"),
                            {"PASTA_PUBLICA": self.publica, "ARQUIVO_RESULTADO": self.resultado})

    def conferir(self, resultados):
        self.assertEqual(resultados["__erros"], [])
        for nome, esperado in self.esperado.items():
            with self.subTest(programa=nome):
                self.assertEqual(resultados.get(nome), esperado)
        caixa = resultados["__caixa_de_erro"] or ""
        self.assertIn("Erro GALO [G304]", caixa)
        self.assertIn("Linha: 2, coluna: 13", caixa)
        self.assertIn("A posição 5 está fora dos limites", caixa)

    def _rodar_cdp(self, nome, executavel):
        servidor = self.iniciar_servidor(nome)
        navegador = Chrome(executavel=executavel)
        try:
            navegador.abrir(f"http://127.0.0.1:{servidor.porta}/")
            resultados = esperar_arquivo(self.resultado, 120)
            self.conferir(resultados)
            return resultados["__agente"]
        finally:
            navegador.fechar()
            servidor.parar()

    @unittest.skipUnless(CHROME, "Chrome/Chromium não está instalado")
    def test_chrome(self):
        agente = self._rodar_cdp("chrome", CHROME)
        self.assertIn("Chrome", agente)
        self.assertNotIn("Edg/", agente)

    @unittest.skipUnless(EDGE, "Microsoft Edge não está instalado (indique o executável em GALO_EDGE)")
    def test_edge(self):
        self.assertIn("Edg/", self._rodar_cdp("edge", EDGE))

    @unittest.skipUnless(WEBKIT, "WebKitGTK (motor do Safari) não está instalado")
    def test_webkit_motor_do_safari(self):
        servidor = self.iniciar_servidor("webkit")
        try:
            dados = rodar_webkit(f"http://127.0.0.1:{servidor.porta}/", [
                {"esperar": "document.getElementById('estado').textContent === 'concluído'", "limite": 180,
                 "descricao": "os programas terminarem"}])
            agente = dados["agente"]
            self.assertIn("AppleWebKit", agente)
            self.assertNotIn("Chrome", agente)
            resultados = esperar_arquivo(self.resultado, 30)
            self.assertEqual(resultados["__agente"], agente)
            self.conferir(resultados)
        finally:
            servidor.parar()

    @unittest.skipUnless(FIREFOX, "Firefox não está instalado")
    def test_firefox(self):
        servidor = self.iniciar_servidor("firefox")
        perfil = tempfile.mkdtemp(prefix="galo-firefox-")
        with open(os.path.join(perfil, "user.js"), "w") as f:
            f.write('user_pref("browser.shell.checkDefaultBrowser", false);\n'
                    'user_pref("browser.startup.homepage_override.mstone", "ignore");\n'
                    'user_pref("datareporting.policy.dataSubmissionEnabled", false);\n'
                    'user_pref("toolkit.telemetry.reportingpolicy.firstRun", false);\n')
        proc = subprocess.Popen([FIREFOX, "--headless", "--no-remote", "--new-instance", "--profile", perfil,
                                 f"http://127.0.0.1:{servidor.porta}/"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            resultados = esperar_arquivo(self.resultado, 180, proc)
            self.assertIn("Firefox", resultados["__agente"])
            self.conferir(resultados)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
            servidor.parar()
            shutil.rmtree(perfil, ignore_errors=True)


@unittest.skipUnless(CHROME, "Chrome/Chromium não está instalado")
class TestAplicativoTarefasNoChrome(unittest.TestCase):
    """O exemplo full stack (examples/tarefas) usado como uma pessoa usaria."""

    EXECUTAVEL = CHROME

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.banco = os.path.join(self._tmp.name, "tarefas.db")
        self.servidor = ServidorGalo(os.path.join(EXEMPLOS, "tarefas", "servidor.galo"), {"BANCO": self.banco})
        self.url = f"http://127.0.0.1:{self.servidor.porta}/"
        self.chrome = Chrome(executavel=self.EXECUTAVEL)
        self.dialogos = []
        self.chrome.ao_dialogo = lambda p: self.dialogos.append((p["type"], p["message"])) or True

    def tearDown(self):
        self.chrome.fechar()
        self.servidor.parar()
        self._tmp.cleanup()

    def itens(self):
        return self.chrome.avaliar(
            "Array.from(document.querySelectorAll('#tarefas li')).map(li => "
            "(li.querySelector('span') || li).textContent + (li.classList.contains('feita') ? ' (feita)' : ''))")

    def resumo(self):
        return self.chrome.avaliar("document.querySelector('#resumo').textContent")

    def api(self):
        return json.loads(self.servidor.pedir("GET", "/api/tarefas")[2])

    def test_fluxo_completo_com_teclado_e_mouse(self):
        c = self.chrome
        self.servidor.pedir("POST", "/api/tarefas", {"título": "Criada pela API"})
        c.abrir(self.url)
        # A interface em GALO assume a página: só ela cria a caixa de seleção de cada item.
        c.esperar("document.querySelectorAll('#tarefas li input[type=checkbox]').length === 1",
                  descricao="a interface GALO desenhar a lista")
        self.assertEqual(self.itens(), ["Criada pela API"])

        # Digitar e teclar Enter envia o formulário (sem recarregar a página).
        c.avaliar("window.__mesma_pagina = true")
        c.digitar("#titulo", "  Comprar café  ")
        c.tecla_enter()
        c.esperar("document.querySelectorAll('#tarefas li').length === 2", descricao="a nova tarefa aparecer")
        self.assertEqual(self.itens(), ["Criada pela API", "Comprar café"])
        self.assertEqual(c.avaliar("document.querySelector('#titulo').value"), "")
        self.assertTrue(c.avaliar("window.__mesma_pagina === true"), "a página não deveria recarregar")
        self.assertEqual(self.resumo(), "2 tarefa(s), 2 pendente(s)")

        # Clique real na caixa de seleção marca a tarefa como feita no servidor.
        c.clicar("#tarefas li:nth-child(1) input")
        c.esperar("document.querySelector('#tarefas li:nth-child(1)').classList.contains('feita')",
                  descricao="a tarefa ficar marcada")
        self.assertEqual(self.resumo(), "2 tarefa(s), 1 pendente(s)")
        self.assertEqual([t["feita"] for t in self.api()], [True, False])

        # Título malicioso é mostrado como texto e não executa nada.
        c.digitar("#titulo", "<img src=x onerror=\"alert('xss')\">")
        c.tecla_enter()
        c.esperar("document.querySelectorAll('#tarefas li').length === 3", descricao="a terceira tarefa")
        self.assertEqual(c.avaliar("document.querySelectorAll('#tarefas img').length"), 0)
        self.assertIn("<img src=x onerror=\"alert('xss')\">", self.itens()[2])

        # Enter com o campo vazio não envia nada (o campo é obrigatório).
        c.digitar("#titulo", "")
        c.tecla_enter()
        time.sleep(0.4)
        self.assertEqual(len(self.api()), 3)

        if CAPTURAS:
            os.makedirs(CAPTURAS, exist_ok=True)
            c.captura(os.path.join(CAPTURAS, f"tarefas-{type(self).__name__}.png"))

        # Apagar pede confirmação; recusar mantém a tarefa, aceitar apaga.
        c.ao_dialogo = lambda p: self.dialogos.append((p["type"], p["message"])) and False
        c.clicar("#tarefas li:nth-child(2) button")
        time.sleep(0.4)
        self.assertEqual(len(self.itens()), 3)
        c.ao_dialogo = lambda p: self.dialogos.append((p["type"], p["message"])) or True
        c.clicar("#tarefas li:nth-child(2) button")
        c.esperar("document.querySelectorAll('#tarefas li').length === 2", descricao="a tarefa sumir")
        self.assertEqual(self.dialogos, [("confirm", 'Apagar "Comprar café"?')] * 2)
        self.assertEqual([t["título"] for t in self.api()], ["Criada pela API", "<img src=x onerror=\"alert('xss')\">"])

        # Recarregar mostra a mesma lista, agora gerada pelo servidor (com escape do HTML).
        c.abrir(self.url)
        c.esperar("document.querySelectorAll('#tarefas li input').length === 2", descricao="a lista após recarregar")
        self.assertEqual(self.itens(), ["Criada pela API (feita)", "<img src=x onerror=\"alert('xss')\">"])

        # Nenhum erro no console, nenhuma caixa de erro da GALO, nenhum alerta inesperado.
        self.assertEqual(c.mensagens_do_console(), [])
        self.assertIsNone(c.avaliar("document.getElementById('galo-erro') && document.getElementById('galo-erro').textContent"))
        self.assertTrue(all(tipo == "confirm" for tipo, _ in self.dialogos))

    def test_erro_de_compilacao_do_cliente_aparece_na_pagina(self):
        with tempfile.TemporaryDirectory() as pasta:
            os.makedirs(os.path.join(pasta, "publico"))
            with open(os.path.join(pasta, "publico", "index.html"), "w", encoding="utf-8") as f:
                f.write('<script src="/_galo/galo.js"></script><script type="application/galo" src="/app.galoc"></script>')
            with open(os.path.join(pasta, "cliente.galo"), "w", encoding="utf-8") as f:
                f.write("mostre variavel_que_nao_existe\n")
            with open(os.path.join(pasta, "srv.galo"), "w", encoding="utf-8") as f:
                f.write('defina app como criar_servidor()\napp.cliente("/app.galoc", "cliente.galo")\n'
                        'app.arquivos("/", "publico")\napp.iniciar(inteiro(variável_ambiente("PORTA")))\n')
            servidor = ServidorGalo(os.path.join(pasta, "srv.galo"))
            try:
                self.chrome.abrir(f"http://127.0.0.1:{servidor.porta}/")
                texto = self.chrome.esperar("document.getElementById('galo-erro') && document.getElementById('galo-erro').textContent",
                                            descricao="a caixa de erro")
                self.assertIn("G201", texto)
                self.assertIn("variavel_que_nao_existe", texto)
            finally:
                servidor.parar()


@unittest.skipUnless(EDGE, "Microsoft Edge não está instalado (indique o executável em GALO_EDGE)")
class TestAplicativoTarefasNoEdge(TestAplicativoTarefasNoChrome):
    """O mesmo fluxo do aplicativo de tarefas, no Microsoft Edge."""

    EXECUTAVEL = EDGE

    def test_e_mesmo_o_edge(self):
        self.chrome.abrir("about:blank")
        self.assertIn("Edg/", self.chrome.avaliar("navigator.userAgent"))


@unittest.skipUnless(WEBKIT, "WebKitGTK (motor do Safari) não está instalado")
class TestAplicativoTarefasNoWebKit(unittest.TestCase):
    """O exemplo full stack no motor do Safari, com cliques e teclas reais (eventos GDK)."""

    ITENS = ("Array.from(document.querySelectorAll('#tarefas li')).map(li => "
             "(li.querySelector('span') || li).textContent + (li.classList.contains('feita') ? ' (feita)' : ''))")
    RESUMO = "document.querySelector('#resumo').textContent"

    def test_fluxo_completo_com_teclado_e_mouse(self):
        with tempfile.TemporaryDirectory() as pasta:
            servidor = ServidorGalo(os.path.join(EXEMPLOS, "tarefas", "servidor.galo"), {"BANCO": os.path.join(pasta, "t.db")})
            try:
                servidor.pedir("POST", "/api/tarefas", {"título": "Criada pela API"})
                url = f"http://127.0.0.1:{servidor.porta}/"
                xss = "<img src=x onerror=\"alert('xss')\">"
                quantos = "document.querySelectorAll('#tarefas li').length"
                dados = rodar_webkit(url, [
                    {"esperar": "document.querySelectorAll('#tarefas li input[type=checkbox]').length === 1",
                     "descricao": "a interface GALO desenhar a lista"},
                    {"avaliar": self.ITENS, "nome": "inicio"},
                    {"avaliar": "window.__mesma_pagina = true"},
                    {"clicar": "#titulo"}, {"digitar": "  Comprar café  "}, {"tecla": "Return"},
                    {"esperar": f"{quantos} === 2", "descricao": "a nova tarefa aparecer"},
                    {"avaliar": self.ITENS, "nome": "apos_digitar"},
                    {"avaliar": "document.querySelector('#titulo').value", "nome": "campo"},
                    {"avaliar": "window.__mesma_pagina === true", "nome": "mesma_pagina"},
                    {"avaliar": self.RESUMO, "nome": "resumo1"},
                    {"clicar": "#tarefas li:nth-child(1) input"},
                    {"esperar": "document.querySelector('#tarefas li:nth-child(1)').classList.contains('feita')",
                     "descricao": "a tarefa ficar marcada"},
                    {"avaliar": self.RESUMO, "nome": "resumo2"},
                    {"clicar": "#titulo"}, {"digitar": xss}, {"tecla": "Return"},
                    {"esperar": f"{quantos} === 3", "descricao": "a terceira tarefa"},
                    {"avaliar": "document.querySelectorAll('#tarefas img').length", "nome": "imagens"},
                    {"avaliar": self.ITENS, "nome": "com_xss"},
                    {"clicar": "#titulo"}, {"tecla": "Return"}, {"pausa": 500},
                    {"avaliar": quantos, "nome": "apos_enter_vazio"},
                    {"dialogos": "recusar"}, {"clicar": "#tarefas li:nth-child(2) button"}, {"pausa": 500},
                    {"avaliar": quantos, "nome": "apos_recusar"},
                    {"dialogos": "aceitar"}, {"clicar": "#tarefas li:nth-child(2) button"},
                    {"esperar": f"{quantos} === 2", "descricao": "a tarefa sumir"},
                    {"abrir": url},
                    {"esperar": "document.querySelectorAll('#tarefas li input').length === 2", "descricao": "a lista após recarregar"},
                    {"avaliar": self.ITENS, "nome": "recarregada"},
                    {"avaliar": "document.getElementById('galo-erro') && document.getElementById('galo-erro').textContent",
                     "nome": "caixa_de_erro"},
                ])
                api = json.loads(servidor.pedir("GET", "/api/tarefas")[2])
            finally:
                servidor.parar()
        v = dados["valores"]
        self.assertIn("AppleWebKit", dados["agente"])
        self.assertEqual(v["inicio"], ["Criada pela API"])
        self.assertEqual(v["apos_digitar"], ["Criada pela API", "Comprar café"])
        self.assertEqual(v["campo"], "")
        self.assertTrue(v["mesma_pagina"], "a página não deveria recarregar")
        self.assertEqual(v["resumo1"], "2 tarefa(s), 2 pendente(s)")
        self.assertEqual(v["resumo2"], "2 tarefa(s), 1 pendente(s)")
        self.assertEqual(v["imagens"], 0)
        self.assertEqual(v["com_xss"][2], xss)
        self.assertEqual(v["apos_enter_vazio"], 3)
        self.assertEqual(v["apos_recusar"], 3)
        self.assertEqual(dados["dialogos"], [["confirm", 'Apagar "Comprar café"?']] * 2)
        self.assertEqual(v["recarregada"], ["Criada pela API (feita)", xss])
        self.assertIsNone(v["caixa_de_erro"])
        self.assertEqual([(t["título"], t["feita"]) for t in api], [("Criada pela API", True), (xss, False)])


if __name__ == "__main__":
    unittest.main()
