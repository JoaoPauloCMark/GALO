"""O site da linguagem (site/), escrito em GALO, e as funções que o tornam possível.

* compilar_programa / executar_programa: compilar no servidor, executar isolado no navegador.
* site/testes.galo: os testes do próprio site, escritos em GALO (sem rede, banco em memória).
* O site de verdade num navegador, usado com mouse e teclado reais: página inicial (exemplos,
  calculadora), "Experimente" (execução, erros, laço infinito interrompido, leia, compartilhar)
  e painel. No Chrome e no Edge (protocolo DevTools) e no WebKit, o motor do Safari (eventos
  nativos do GTK).
"""

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from auxiliar import RAIZ, erro_de_execucao, executar, galo_cli
from galo.compiler import compile_source
from galo.compiler.bytecode import dump_module

sys.path.insert(0, os.path.join(RAIZ, "tests", "navegador_real"))
from cdp import Chrome, encontrar_chrome, encontrar_edge  # noqa: E402
from test_navegador_real import WEBKIT, rodar_webkit  # noqa: E402
from test_web import ServidorGalo  # noqa: E402

SITE = os.path.join(RAIZ, "site")
GJS = shutil.which("gjs")
GALO_JS = os.path.join(RAIZ, "galo", "web", "galo.js")
CHROME = encontrar_chrome()
EDGE = encontrar_edge()


class TestCompilarPrograma(unittest.TestCase):
    def test_programa_valido(self):
        saida = executar('defina r como compilar_programa("mostre 1 + 1")\n'
                         'mostre r.ok, tipo(r.bytecode), tamanho(r.erros), tamanho(r.avisos)')
        self.assertEqual(saida.strip(), "verdadeiro texto 0 0")

    def test_bytecode_e_o_mesmo_do_compilador(self):
        saida = executar('mostre compilar_programa("mostre 42", "x.galo").bytecode')
        esperado = base64.b64encode(dump_module(compile_source("mostre 42", "x.galo").module)).decode()
        self.assertEqual(saida.strip(), esperado)

    def test_erros_com_posicao_sugestao_e_texto(self):
        saida = executar('defina r como compilar_programa("defina nome como 1\\nmostre nmoe")\n'
                         "defina e1 como r.erros[1]\n"
                         "mostre r.ok, r.bytecode, e1.código, e1.tipo, e1.linha, e1.coluna\n"
                         "mostre e1.sugestão\nmostre e1.texto")
        linhas = saida.splitlines()
        self.assertEqual(linhas[0], "falso nulo G201 erro semântico 2 8")
        self.assertIn("Você quis dizer 'nome'?", saida)
        self.assertIn("Erro GALO [G201] — erro semântico", saida)
        self.assertIn("2 | mostre nmoe", saida)

    def test_varios_erros_e_avisos(self):
        saida = executar('defina r como compilar_programa("mostre a\\nmostre b")\nmostre tamanho(r.erros)')
        self.assertEqual(saida.strip(), "2")

    def test_importe_nao_le_arquivos_do_servidor(self):
        with tempfile.TemporaryDirectory() as pasta:
            with open(os.path.join(pasta, "segredo.galo"), "w", encoding="utf-8") as f:
                f.write("defina SENHA como 123\n")
            fonte = os.path.join(pasta, "p.galo")
            with open(fonte, "w", encoding="utf-8") as f:
                f.write('defina r como compilar_programa("importe SENHA de \\"segredo.galo\\"\\nmostre SENHA")\n'
                        "mostre r.ok, r.erros[1].código, r.erros[1].mensagem\n")
            r = galo_cli("executar", fonte)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("falso G220", r.stdout)
        self.assertIn("não pode importar", r.stdout)

    def test_limites(self):
        self.assertEqual(erro_de_execucao("compilar_programa(repetir(\"#\", 200001))").code, "G322")
        self.assertEqual(erro_de_execucao("compilar_programa(42)").code, "G322")
        saida = executar('mostre compilar_programa(repetir("(", 30000) + "1" + repetir(")", 30000)).erros[1].código')
        self.assertTrue(saida.strip().startswith("G"), saida)

    def test_executar_programa_so_existe_no_navegador(self):
        self.assertEqual(erro_de_execucao('executar_programa("", nulo, função(r) fim)').code, "G327")


@unittest.skipUnless(GJS, "gjs não está instalado")
class TestExecutarProgramaNoGjs(unittest.TestCase):
    """Sem Web Worker (gjs), executar_programa roda o programa na hora, numa VM separada."""

    def rodar_cliente(self, fonte_cliente):
        with tempfile.TemporaryDirectory() as pasta:
            fonte = os.path.join(pasta, "cliente.galo")
            with open(fonte, "w", encoding="utf-8") as f:
                f.write(fonte_cliente)
            galoc = os.path.join(pasta, "cliente.galoc")
            self.assertEqual(galo_cli("compilar", fonte, "-o", galoc).returncode, 0)
            saida = os.path.join(pasta, "saida.txt")
            r = subprocess.run([GJS, os.path.join(RAIZ, "tests", "js", "rodar_galoc.js"), GALO_JS, galoc, saida],
                               capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(saida, encoding="utf-8") as f:
                return f.read()

    def test_saida_entradas_e_erro(self):
        programa = 'defina n como leia("Nome? ")\nmostre "Oi, {n}!"\nmostre 2 ^ 70\nmostre [1][3]\n'
        bc = base64.b64encode(dump_module(compile_source(programa, "visitante.galo").module)).decode()
        saida = self.rodar_cliente(
            f'mostre "antes"\n'
            f'executar_programa("{bc}", {{"entradas": ["Bia"]}}, função(r)\n'
            f'    mostre "saída:", r.saída\n'
            f'    mostre r.erro.código, r.erro.linha, r.erro.coluna, r.interrompido, tipo(r.tempo)\n'
            f'    mostre r.erro.texto\n'
            f'fim)\nmostre "depois"\n')
        self.assertIn("saída: Nome? Bia\nOi, Bia!\n1180591620717411303424\n", saida)
        self.assertIn("G304 4 11 falso decimal", saida)
        self.assertIn("Arquivo: visitante.galo", saida)
        # o programa visitante não enxerga as variáveis de quem o executa
        self.assertTrue(saida.startswith("antes\n"))

    def test_isolamento_e_bytecode_invalido(self):
        programa = "mostre tipo(segredo)\n"
        with self.assertRaises(Exception):
            compile_source(programa, "x.galo")  # nem compila: 'segredo' não existe para ele
        bc = base64.b64encode(dump_module(compile_source('mostre "ok"', "x.galo").module)).decode()
        saida = self.rodar_cliente(
            'defina segredo como "123"\n'
            f'executar_programa("{bc}", nulo, função(r) mostre r.saída, r.erro fim)\n'
            'tente\n    executar_programa("AAAA", nulo, função(r) fim)\ncapture problema\n'
            '    mostre "recusado:", problema.código\nfim\n'
            'tente\n    executar_programa("não é base64!", nulo, função(r) fim)\ncapture problema\n'
            '    mostre "recusado:", problema.código\nfim\n')
        self.assertIn("ok\n nulo", saida)
        self.assertIn("recusado: G502", saida)
        self.assertIn("recusado: G312", saida)


class TestTestesDoSite(unittest.TestCase):
    def test_testes_escritos_em_galo(self):
        r = galo_cli("executar", os.path.join(SITE, "testes.galo"), timeout=180)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("verificações do site passaram", r.stdout)

    def test_todos_os_arquivos_do_site_compilam(self):
        for raiz, _, arquivos in os.walk(SITE):
            for a in sorted(arquivos):
                if a.endswith(".galo"):
                    with self.subTest(arquivo=os.path.relpath(os.path.join(raiz, a), SITE)):
                        r = galo_cli("verificar", os.path.join(raiz, a))
                        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_exemplos_da_galeria_rodam(self):
        for a in sorted(os.listdir(os.path.join(SITE, "exemplos"))):
            with self.subTest(exemplo=a):
                r = galo_cli("executar", os.path.join(SITE, "exemplos", a), entrada="Ana\n")
                if a.endswith("erro.galo"):  # este exemplo existe para mostrar um erro de execução
                    self.assertEqual(r.returncode, 2)
                    self.assertIn("[G304]", r.stderr)
                else:
                    self.assertEqual(r.returncode, 0, r.stderr)
                    self.assertTrue(r.stdout.strip())


class _SiteNoNavegador:
    """Fluxo completo do site, com mouse e teclado reais (protocolo DevTools)."""

    EXECUTAVEL = None

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.servidor = ServidorGalo(os.path.join(SITE, "servidor.galo"))
        self.url = f"http://127.0.0.1:{self.servidor.porta}"
        self.nav = Chrome(1280, 900, executavel=self.EXECUTAVEL)
        self.nav.chamar("Runtime.enable")

    def tearDown(self):
        self.nav.fechar()
        self.servidor.parar()
        self._tmp.cleanup()

    def abrir(self, caminho):
        self.nav.abrir(self.url + caminho)
        self.nav.esperar("document.body.dataset.pronto === 'sim'", 20, "o programa GALO da página")

    def texto(self, seletor):
        return self.nav.avaliar(f"document.querySelector({json.dumps(seletor)}).textContent")

    def tecla(self, nome, texto=None, modificadores=0):
        for tipo in ("keyDown", "keyUp"):
            p = {"type": tipo, "key": nome, "modifiers": modificadores}
            if nome == "Enter":
                p.update(code="Enter", windowsVirtualKeyCode=13)
            if texto and tipo == "keyDown":
                p["text"] = texto
            self.nav.chamar("Input.dispatchKeyEvent", p)

    def trocar_codigo(self, codigo):
        self.nav.avaliar("(() => { const a = document.querySelector('#codigo'); a.focus(); a.select(); })()")
        self.nav.chamar("Input.insertText", {"text": codigo})

    def esperar_execucao(self, limite=20):
        return self.nav.esperar("(() => { const s = document.querySelector('#status').textContent;"
                                " return !s.includes('compilando') && s !== 'pronto' && s; })()", limite, "fim da execução")

    def test_pagina_inicial(self):
        self.abrir("/")
        nav = self.nav
        # a janela do topo executa o primeiro programa de verdade
        nav.esperar("document.querySelector('#vitrine-saida').textContent.includes('Olá, mundo!')", 10)
        # exemplo com leia(): a entrada configurada no exemplo é usada
        nav.clicar(".exemplo.ativa .executar-exemplo")
        saida = nav.esperar("(() => { const t = document.querySelector('.exemplo.ativa .console-saida').textContent;"
                            " return t.includes('Ana') && t; })()", 20, "saída do exemplo")
        self.assertIn("Olá, Ana! Bem-vindo(a) à GALO 🐓", saida)
        # trocar de aba e ver um erro de execução explicado
        nav.clicar(".aba[data-id=erro]")
        self.assertEqual(nav.avaliar("document.querySelector('.exemplo.ativa').dataset.id"), "erro")
        nav.clicar(".exemplo.ativa .executar-exemplo")
        erro = nav.esperar("document.querySelector('.exemplo.ativa .erros').textContent", 20, "erro do exemplo")
        self.assertIn("G304", erro)
        self.assertIn("linha 4", erro)
        # calculadora: cliques e teclado
        for k in ["C", "1", "+", "2", "×", "3", "="]:
            nav.clicar(f".tecla[data-tecla='{k}']")
        self.assertEqual(self.texto("#calc-resultado"), "7")
        for nome, texto in [("Escape", None), ("2", "2"), ("^", "^"), ("1", "1"), ("0", "0"), ("0", "0"), ("Enter", None)]:
            self.tecla(nome, texto)
        nav.esperar("document.querySelector('#calc-resultado').textContent === '1.267.650.600.228.229.401.496.703.205.376'", 5)
        for nome, texto in [("Escape", None), ("1", "1"), ("/", "/"), ("0", "0"), ("Enter", None)]:
            self.tecla(nome, texto)
        self.assertIn("dividir por zero", self.texto("#calc-resultado"))
        self.assertIn("2 ^ 100", self.texto("#calc-historico"))
        # mini painel atualiza sozinho
        hora = self.texto("#mini-hora")
        nav.esperar(f"document.querySelector('#mini-hora').textContent !== {json.dumps(hora)}", 5, "a simulação andar")
        self.assertEqual(nav.mensagens_do_console(), [])

    def test_experimente(self):
        self.abrir("/experimente")
        nav = self.nav
        nav.clicar("#botao-executar")
        self.assertIn("executado", self.esperar_execucao())
        self.assertIn("Olá, mundo! 🐓", self.texto("#saida"))
        # erro de compilação com Ctrl+Enter: cartão do erro e linha marcada no editor
        self.trocar_codigo('defina nome como "Ana"\nmostre nmoe\n')
        nav.clicar("#codigo")
        self.tecla("Enter", modificadores=2)
        self.assertIn("erro de compilação", self.esperar_execucao())
        self.assertIn("Você quis dizer 'nome'?", self.texto("#erros"))
        self.assertTrue(nav.avaliar("!document.querySelector('#marca-erro').hidden"))
        self.assertEqual(nav.avaliar("getComputedStyle(document.querySelector('#marca-erro')).getPropertyValue('--linha')").strip(), "2")
        # laço infinito: roda num worker, é interrompido e a página continua respondendo
        self.trocar_codigo('mostre "antes"\nenquanto verdadeiro faça\nfim\n')
        inicio = time.time()
        nav.clicar("#botao-executar")
        time.sleep(1)
        self.assertEqual(nav.avaliar("1 + 1"), 2)
        self.assertIn("interrompido", self.esperar_execucao(20))
        self.assertGreater(time.time() - inicio, 4.5)
        self.assertIn("G330", self.texto("#erros"))
        self.assertIn("antes", self.texto("#saida"))
        # leia() com as entradas da página
        self.trocar_codigo('defina n como leia("Número: ")\nmostre "dobro:", inteiro(n) * 2\n')
        nav.avaliar("document.querySelector('details.entradas').open = true")
        nav.digitar("#entradas", "21")
        nav.clicar("#botao-executar")
        self.assertIn("executado", self.esperar_execucao())
        self.assertEqual(self.texto("#saida"), "Número: 21\ndobro: 42\n")
        # o código fica salvo no navegador
        self.abrir("/experimente")
        self.assertIn("dobro", nav.avaliar("document.querySelector('#codigo').value"))
        # compartilhar: o programa vai dentro do link (nada é guardado no servidor)
        nav.clicar("#botao-compartilhar")
        link = nav.esperar("document.querySelector('#link').value", 10, "o link")
        self.assertRegex(link, r"/experimente#codigo=[A-Za-z0-9_-]+$")
        self.trocar_codigo("mostre 1\n")   # mudou depois de compartilhar: o link continua com o programa antigo
        nav.abrir("about:blank")
        self.abrir(link.split(str(self.servidor.porta), 1)[1])
        self.assertEqual(nav.avaliar("document.querySelector('#codigo').value"),
                         'defina n como leia("Número: ")\nmostre "dobro:", inteiro(n) * 2\n')
        self.assertTrue(nav.avaliar("!document.querySelector('#aviso-link').hidden"))
        # exemplo escolhido na lista
        nav.avaliar("(() => { const s = document.querySelector('#seletor-exemplo'); s.value = 'tabuada';"
                    " s.dispatchEvent(new Event('change')); })()")
        nav.esperar("document.querySelector('#codigo').value.includes('{n} × {i}')", 10, "o exemplo carregar")
        self.assertEqual(nav.mensagens_do_console(), [])

    def test_painel(self):
        # "Seus números" vêm do que a pessoa executou neste navegador
        self.abrir("/experimente")
        self.trocar_codigo("mostre x\n")
        self.nav.clicar("#botao-executar")
        self.esperar_execucao()
        self.abrir("/painel")
        nav = self.nav
        nav.esperar("document.querySelectorAll('#ranking li').length === 5", 10)
        self.assertEqual(nav.avaliar("document.querySelectorAll('#grafico-xicaras rect').length"), 7)
        self.assertEqual(nav.avaliar("document.querySelectorAll('#legenda-categorias li').length"), 4)
        self.assertTrue(nav.avaliar("document.querySelector('#grafico-temperatura svg path') !== null"))
        nav.esperar("document.querySelector('#lista-erros').textContent.includes('G201')", 10, "as estatísticas")
        self.assertEqual(self.texto("#st-execucoes"), "1")
        self.assertIn("mostre", self.texto("#nuvem"))
        self.assertEqual(nav.avaliar("document.querySelectorAll('#grafico-horas rect').length"), 24)
        nav.ao_dialogo = lambda p: True
        nav.clicar("#apagar-numeros")
        nav.esperar("document.querySelector('#st-execucoes').textContent === '0'", 5, "apagar os números")
        self.assertIn("Nenhum erro", self.texto("#lista-erros"))
        hora = self.texto("#hora-cafeteria")
        nav.esperar(f"document.querySelector('#hora-cafeteria').textContent !== {json.dumps(hora)}", 5)
        self.assertEqual(nav.mensagens_do_console(), [])

    def test_celular(self):
        self.nav.chamar("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True})
        for caminho in ("/", "/experimente", "/painel"):
            with self.subTest(pagina=caminho):
                self.abrir(caminho)
                self.assertEqual(self.nav.avaliar("document.documentElement.scrollWidth"), 390, "nada pode vazar para o lado")
        self.assertFalse(self.nav.avaliar("getComputedStyle(document.querySelector('#menu')).display !== 'none'"))
        self.nav.clicar("#menu-botao")
        self.assertTrue(self.nav.avaliar("getComputedStyle(document.querySelector('#menu')).display !== 'none'"))


@unittest.skipUnless(CHROME, "Chrome/Chromium não está instalado")
class TestSiteNoChrome(_SiteNoNavegador, unittest.TestCase):
    EXECUTAVEL = CHROME


@unittest.skipUnless(EDGE, "Microsoft Edge não está instalado (indique o executável em GALO_EDGE)")
class TestSiteNoEdge(_SiteNoNavegador, unittest.TestCase):
    EXECUTAVEL = EDGE


@unittest.skipUnless(WEBKIT, "WebKitGTK (motor do Safari) não está instalado")
class TestSiteNoWebKit(unittest.TestCase):
    """O mesmo site no motor do Safari, com cliques e teclas nativos."""

    def test_fluxo(self):
        with tempfile.TemporaryDirectory() as pasta:
            servidor = ServidorGalo(os.path.join(SITE, "servidor.galo"))
            url = f"http://127.0.0.1:{servidor.porta}"
            pronto = {"esperar": "document.body.dataset.pronto === 'sim'", "limite": 30, "descricao": "o programa GALO"}
            status = "document.querySelector('#status').textContent"
            try:
                inicio = rodar_webkit(url + "/", [
                    pronto,
                    {"clicar": ".exemplo.ativa .executar-exemplo"},
                    {"esperar": "document.querySelector('.exemplo.ativa .console-saida').textContent.includes('Ana')",
                     "descricao": "o exemplo executar"},
                    {"avaliar": "document.querySelector('.exemplo.ativa .console-saida').textContent", "nome": "exemplo"},
                    {"clicar": "#calc-expressao"}, {"tecla": "Escape"}, {"digitar": "7*6"}, {"tecla": "Return"},
                    {"avaliar": "document.querySelector('#calc-resultado').textContent", "nome": "conta"},
                ])
                experimente = rodar_webkit(url + "/experimente", [
                    pronto,
                    {"clicar": "#botao-executar"},
                    {"esperar": f"{status}.includes('executado')", "descricao": "a execução"},
                    {"avaliar": "document.querySelector('#saida').textContent", "nome": "saida"},
                    {"avaliar": "(() => { const a = document.querySelector('#codigo'); a.value = 'enquanto verdadeiro faça\\nfim'; a.dispatchEvent(new Event('input')); })()"},
                    {"clicar": "#botao-executar"},
                    {"esperar": f"{status}.includes('interrompido')", "limite": 20, "descricao": "a interrupção"},
                    {"avaliar": "document.querySelector('#erros').textContent", "nome": "erros"},
                ])
            finally:
                servidor.parar()
        self.assertIn("Olá, Ana!", inicio["valores"]["exemplo"])
        self.assertEqual(inicio["valores"]["conta"], "42")
        self.assertIn("Olá, mundo! 🐓", experimente["valores"]["saida"])
        self.assertIn("G330", experimente["valores"]["erros"])


if __name__ == "__main__":
    unittest.main()
