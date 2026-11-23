"""Biblioteca de backend: JSON, segurança, modelos HTML, banco de dados e servidor web."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

from auxiliar import EXEMPLOS, RAIZ, erro_de_execucao, executar, galo_cli


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ServidorGalo:
    """Inicia um programa GALO que chama app.iniciar(...) e espera a porta abrir."""

    def __init__(self, programa: str, env: dict | None = None, comando: list[str] | None = None) -> None:
        """`comando` troca o `python -m galo` do repositório por outro (por exemplo, um `galo` instalado)."""
        self.porta = porta_livre()
        ambiente = dict(os.environ, PORTA=str(self.porta), GALO_SEM_COR="1", **(env or {}))
        if comando is None:
            ambiente["PYTHONPATH"] = RAIZ
            comando = [sys.executable, "-m", "galo"]
        else:
            ambiente.pop("PYTHONPATH", None)
        self.proc = subprocess.Popen([*comando, "executar", programa], env=ambiente,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        limite = time.time() + 15
        while time.time() < limite:
            try:
                socket.create_connection(("127.0.0.1", self.porta), timeout=0.2).close()
                return
            except OSError:
                if self.proc.poll() is not None:
                    raise RuntimeError("o servidor terminou: " + self.proc.stderr.read())
                time.sleep(0.05)
        raise RuntimeError("o servidor não abriu a porta")

    def pedir(self, metodo, caminho, corpo=None, cabecalhos=None):
        dados = None
        cab = dict(cabecalhos or {})
        if corpo is not None:
            dados = json.dumps(corpo).encode() if not isinstance(corpo, (str, bytes)) else (
                corpo.encode() if isinstance(corpo, str) else corpo)
            cab.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(f"http://127.0.0.1:{self.porta}{caminho}", data=dados, headers=cab, method=metodo)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def parar(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        finally:
            self.proc.stdout.close()
            self.proc.stderr.close()


def valor(expr):
    return executar(f"mostre {expr}").rstrip("\n")


class TestJSON(unittest.TestCase):
    def test_ida_e_volta(self):
        self.assertEqual(valor("""para_json({"a": [1, 2.5, nulo, verdadeiro], "b": "ã"})"""), '{"a":[1,2.5,null,true],"b":"ã"}')
        self.assertEqual(valor("""de_json('{"x": [1, 2.0, {"y": null}]}')"""), '{"x": [1, 2.0, {"y": nulo}]}')
        self.assertEqual(valor("""tipo(de_json('1')), tipo(de_json('1.0')), tipo(de_json('[]'))"""), "inteiro decimal lista")
        self.assertEqual(executar('escreva(para_json([1, {"a": []}], 2))'), '[\n  1,\n  {\n    "a": []\n  }\n]')

    def test_erros(self):
        self.assertEqual(erro_de_execucao("""mostre de_json('{"a": }')""").code, "G323")
        self.assertIn("linha 1, coluna 7", erro_de_execucao("""mostre de_json('{"a": }')""").message)
        self.assertEqual(erro_de_execucao("mostre de_json('NaN')").code, "G323")
        self.assertEqual(erro_de_execucao("mostre para_json(tamanho)").code, "G323")
        self.assertEqual(erro_de_execucao("defina l como []\nadicionar(l, l)\nmostre para_json(l)").code, "G323")


class TestSegurancaETexto(unittest.TestCase):
    def test_senhas(self):
        fonte = ('defina h como hash_senha("s3nh@")\nmostre começa_com(h, "pbkdf2_sha256$"), verificar_senha("s3nh@", h), '
                 'verificar_senha("outra", h), verificar_senha("x", "lixo"), hash_senha("a") == hash_senha("a")')
        self.assertEqual(executar(fonte), "verdadeiro verdadeiro falso falso falso\n")

    def test_codificacoes_e_identificadores(self):
        self.assertEqual(valor("""escapar_html('<a href="x">&</a>')"""), "&lt;a href=&quot;x&quot;&gt;&amp;&lt;/a&gt;")
        self.assertEqual(valor('codificar_url("a b/ç"), decodificar_url("a%20b%2F")'), "a%20b%2F%C3%A7 a b/")
        self.assertEqual(valor('decodificar_base64(codificar_base64("Olá 🐓"))'), "Olá 🐓")
        self.assertEqual(valor('tamanho(uuid()), tamanho(token_aleatório(16)) >= 16, token_aleatório() != token_aleatório()'),
                         "36 verdadeiro verdadeiro")
        import hashlib

        self.assertEqual(valor('sha256("galo")'), hashlib.sha256("galo".encode()).hexdigest())

    def test_expressoes_regulares(self):
        self.assertEqual(valor("corresponde(\"ana@x.com\", '^[^@]+@[^@]+\\.[a-z]+$'), corresponde(\"ana\", '@')"),
                         "verdadeiro falso")
        self.assertEqual(valor("procurar_todos(\"R$ 10 e R$ 250\", '[0-9]+')"), '["10", "250"]')
        self.assertEqual(valor("substituir_padrão(\"2026-11-22\", '(\\d+)-(\\d+)-(\\d+)', '\\3/\\2/\\1')"), "22/11/2026")
        self.assertEqual(erro_de_execucao("mostre corresponde(\"a\", '(')").code, "G322")

    def test_variavel_ambiente_e_afirmar(self):
        self.assertEqual(valor('variável_ambiente("GALO_NAO_EXISTE"), variável_ambiente("GALO_NAO_EXISTE", "padrão")'),
                         "nulo padrão")
        self.assertEqual(erro_de_execucao('afirmar(1 > 2, "um não é maior")').code, "G329")
        self.assertIn("um não é maior", erro_de_execucao('afirmar(1 > 2, "um não é maior")').message)


class TestModelos(unittest.TestCase):
    def test_escape_condicoes_e_lacos(self):
        fonte = ("""escreva(modelo('<h1>{{ t }}</h1>{{{ cru }}}{% se ok %}S{% senão %}N{% fim %}{% se não ok %}!{% fim %}' + """
                 """'{% para cada i, x em itens %}[{{ i }}:{{ x.nome }}]{% fim %}{# comentário #}', """
                 """{"t": "<b>", "cru": "<i>", "ok": verdadeiro, "itens": [{"nome": "a&b"}, {"nome": "c"}]}))""")
        self.assertEqual(executar(fonte), "<h1>&lt;b&gt;</h1><i>S[1:a&amp;b][2:c]")

    def test_registros_nos_dados(self):
        fonte = "registro P(nome)\nescreva(modelo('{{ p.nome }}', {\"p\": P(\"Zé\")}))"
        self.assertEqual(executar(fonte), "Zé")

    def test_renderizar_arquivo_com_inclusao(self):
        with tempfile.TemporaryDirectory() as pasta:
            os.makedirs(os.path.join(pasta, "paginas"))
            with open(os.path.join(pasta, "paginas", "base.html"), "w", encoding="utf-8") as f:
                f.write("<main>{% inclua \"parcial.html\" %}</main>")
            with open(os.path.join(pasta, "paginas", "parcial.html"), "w", encoding="utf-8") as f:
                f.write("Olá, {{ nome }}!")
            programa = os.path.join(pasta, "p.galo")
            with open(programa, "w", encoding="utf-8") as f:
                f.write('escreva(renderizar("paginas/base.html", {"nome": "<Ana>"}))')
            self.assertEqual(galo_cli("executar", programa).stdout, "<main>Olá, &lt;Ana&gt;!</main>")

    def test_erros_de_modelo(self):
        casos = ["{{ x }}", "{% se x %}", "{% para x %}", "{% fim %}", "{{ 1 + 1 }}", "{% foo %}"]
        for texto in casos:
            with self.subTest(modelo=texto):
                self.assertEqual(erro_de_execucao(f"mostre modelo('{texto}', {{\"y\": 1}})").code, "G328")
        e = erro_de_execucao("mostre modelo('{% se n %}{% fim %}', {\"n\": 1})")
        self.assertIn("booleano", e.message)


class TestBancoDeDados(unittest.TestCase):
    BASE = ('defina b como abrir_banco(":memória:")\n'
            'b.executar("CREATE TABLE p (id INTEGER PRIMARY KEY, nome TEXT UNIQUE NOT NULL, ativo INTEGER, nota REAL)")\n')

    def test_crud_com_parametros(self):
        fonte = self.BASE + ('defina id como b.inserir("INSERT INTO p (nome, ativo, nota) VALUES (?, ?, ?)", ["Ana", verdadeiro, 9.5])\n'
                             'b.inserir("INSERT INTO p (nome, ativo) VALUES (:n, :a)", {"n": "Bia", "a": falso})\n'
                             'mostre id, b.consultar("SELECT nome, ativo, nota FROM p ORDER BY id")\n'
                             'mostre b.consultar_um("SELECT nome FROM p WHERE id = ?", [2]), b.consultar_um("SELECT * FROM p WHERE id = 9")\n'
                             'mostre b.executar("UPDATE p SET ativo = 1"), b.executar("DELETE FROM p WHERE nome = ?", ["Bia"])\n'
                             'b.fechar()')
        self.assertEqual(executar(fonte),
                         '1 [{"nome": "Ana", "ativo": 1, "nota": 9.5}, {"nome": "Bia", "ativo": 0, "nota": nulo}]\n'
                         '{"nome": "Bia"} nulo\n2 1\n')

    def test_injecao_de_sql_nao_funciona(self):
        fonte = self.BASE + ('b.inserir("INSERT INTO p (nome) VALUES (?)", ["x\'); DROP TABLE p; --"])\n'
                             'mostre b.consultar("SELECT nome FROM p")[1].nome, tamanho(b.consultar("SELECT * FROM p"))')
        self.assertEqual(executar(fonte), "x'); DROP TABLE p; -- 1\n")

    def test_transacao_desfaz_em_caso_de_erro(self):
        fonte = self.BASE + ('tente\n    b.transação(função()\n        b.inserir("INSERT INTO p (nome) VALUES (?)", ["A"])\n'
                             '        b.inserir("INSERT INTO p (nome) VALUES (?)", ["A"])\n    fim)\ncapture erro\n'
                             '    mostre erro.código, erro.mensagem\nfim\nmostre tamanho(b.consultar("SELECT * FROM p"))\n'
                             'mostre b.transação(função() retorne b.inserir("INSERT INTO p (nome) VALUES (?)", ["C"]) fim)')
        self.assertEqual(executar(fonte), "G324 Erro no banco de dados: já existe um registro com o mesmo valor em p.nome.\n0\n1\n")

    def test_erros_traduzidos(self):
        for sql, trecho in [("SELECT * FROM nada", "a tabela 'nada' não existe"), ("SELEC 1", "erro de sintaxe"),
                            ("SELECT * FROM p WHERE id = ?", "o SQL usa 1 parâmetro(s)")]:
            with self.subTest(sql=sql):
                e = erro_de_execucao(self.BASE + f'b.consultar("{sql}")')
                self.assertEqual(e.code, "G324")
                self.assertIn(trecho, e.message)
        self.assertIn("para_json", erro_de_execucao(self.BASE + 'b.executar("SELECT ?", [[1]])').suggestion)

    def test_arquivo_relativo_ao_programa(self):
        with tempfile.TemporaryDirectory() as pasta:
            programa = os.path.join(pasta, "db.galo")
            with open(programa, "w", encoding="utf-8") as f:
                f.write('defina b como abrir_banco("dados.db")\nb.executar("CREATE TABLE t (x)")\n')
            self.assertEqual(galo_cli("executar", programa, cwd=tempfile.gettempdir()).returncode, 0)
            self.assertTrue(os.path.exists(os.path.join(pasta, "dados.db")))


ROTAS = '''
defina app como criar_servidor()
app.get("/oi/<nome>", função(p) retorne {"oi": p.parâmetros.nome, "q": obter(p.consulta, "q")} fim)
app.get("/num/<n:inteiro>", função(p) retorne p.parâmetros.n * 2 fim)
app.post("/eco", função(p) retorne p.json fim)
app.post("/form", função(p) retorne p.formulário fim)
app.get("/html", função(p) retorne "<p>oi</p>" fim)
app.get("/vazio", função(p) retorne nulo fim)
app.get("/criado", função(p) retorne resposta_json({"ok": verdadeiro}, 201, {"X-Teste": "1"}) fim)
app.get("/ir", função(p) retorne redirecionar("/html") fim)
app.get("/quebra", função(p) retorne 1 / 0 fim)
app.get("/biscoito", função(p) retorne p.cookies fim)
app.antes(função(p)
    se começa_com(p.caminho, "/admin") então
        retorne resposta_json({"erro": "proibido"}, 403)
    fim
    retorne nulo
fim)
app.get("/admin/painel", função(p) retorne "segredo" fim)
'''


class TestServidor(unittest.TestCase):
    def executar_chamadas(self, *chamadas):
        fonte = ROTAS + "\n".join(f"mostre {c}" for c in chamadas)
        return executar(fonte).splitlines()

    def test_rotas_parametros_e_respostas(self):
        saida = self.executar_chamadas(
            'app.testar("GET", "/oi/Ana%20Maria?q=1").json',
            'app.testar("GET", "/num/21").json, app.testar("GET", "/num/abc").status',
            'app.testar("POST", "/eco", {"a": [1]}).json',
            'app.testar("POST", "/form", "x=1&y=a+b", {"Content-Type": "application/x-www-form-urlencoded"}).json',
            'app.testar("GET", "/html").cabeçalhos["content-type"], app.testar("GET", "/vazio").status',
            'app.testar("GET", "/criado").status, app.testar("GET", "/criado").cabeçalhos["x-teste"]',
            'app.testar("GET", "/ir").status, app.testar("GET", "/ir").cabeçalhos["location"]',
            'app.testar("GET", "/biscoito", nulo, {"Cookie": "sessao=abc; tema=escuro"}).json',
        )
        self.assertEqual(saida, [
            '{"oi": "Ana Maria", "q": "1"}', "42 404", '{"a": [1]}', '{"x": "1", "y": "a b"}',
            "text/html; charset=utf-8 204", "201 1", "303 /html", '{"sessao": "abc", "tema": "escuro"}',
        ])

    def test_erros_e_middleware(self):
        saida = self.executar_chamadas(
            'app.testar("GET", "/nada").status, app.testar("DELETE", "/html").status',
            'app.testar("DELETE", "/html").cabeçalhos["allow"]',
            'app.testar("GET", "/quebra").status, app.testar("GET", "/quebra").json.código',
            'app.testar("GET", "/admin/painel").status, app.testar("GET", "/html").status',
        )
        self.assertEqual(saida, ["404 405", "GET", "500 G303", "403 200"])

    def test_estaticos_protegidos(self):
        with tempfile.TemporaryDirectory() as pasta:
            os.makedirs(os.path.join(pasta, "publico", "css"))
            for nome, conteudo in [("publico/index.html", "<p>início</p>"), ("publico/css/a.css", "b{}"), ("segredo.txt", "não!")]:
                with open(os.path.join(pasta, nome), "w", encoding="utf-8") as f:
                    f.write(conteudo)
            programa = os.path.join(pasta, "s.galo")
            with open(programa, "w", encoding="utf-8") as f:
                f.write('defina app como criar_servidor()\napp.arquivos("/", "publico")\n'
                        'mostre app.testar("GET", "/").corpo, app.testar("GET", "/css/a.css").cabeçalhos["content-type"]\n'
                        'mostre app.testar("GET", "/../segredo.txt").status, app.testar("GET", "/css/%2e%2e/../segredo.txt").status\n'
                        'mostre app.testar("GET", "/nao.html").status\n')
            r = galo_cli("executar", programa)
            self.assertEqual(r.stdout.splitlines(), ["<p>início</p> text/css; charset=utf-8", "403 403", "404"])

    def test_modo_producao_esconde_detalhes(self):
        with tempfile.TemporaryDirectory() as pasta:
            programa = os.path.join(pasta, "s.galo")
            with open(programa, "w", encoding="utf-8") as f:
                f.write(ROTAS + 'mostre app.testar("GET", "/quebra").corpo')
            env = dict(os.environ, PYTHONPATH=RAIZ, GALO_PRODUCAO="1")
            r = subprocess.run([sys.executable, "-m", "galo", "executar", programa], env=env, capture_output=True,
                               text=True, encoding="utf-8")
            self.assertEqual(r.stdout.strip(), '{"erro": "Erro interno no servidor."}')

    def test_servidor_real_e_cliente_http(self):
        with tempfile.TemporaryDirectory() as pasta:
            programa = os.path.join(pasta, "srv.galo")
            with open(programa, "w", encoding="utf-8") as f:
                f.write(ROTAS + 'defina visitas como 0\napp.get("/conta", função(p)\n    visitas += 1\n    retorne visitas\nfim)\n'
                        'app.get("/parar", função(p)\n    app.parar()\n    retorne "tchau"\nfim)\n'
                        'app.iniciar(inteiro(variável_ambiente("PORTA")))\nmostre "encerrado"\n')
            s = ServidorGalo(programa)
            try:
                self.assertEqual(s.pedir("GET", "/oi/Bia")[2], b'{"oi":"Bia","q":null}')
                self.assertEqual(s.pedir("POST", "/eco", {"x": [1, 2.5]})[2], b'{"x":[1,2.5]}')
                self.assertEqual([s.pedir("GET", "/conta")[2] for _ in range(3)], [b"1", b"2", b"3"])
                status, cab, corpo = s.pedir("GET", "/quebra")
                self.assertEqual(status, 500)
                self.assertEqual(json.loads(corpo)["código"], "G303")
                self.assertEqual(s.pedir("HEAD", "/html")[0], 200)
                self.assertEqual(s.pedir("GET", "/_galo/galo.js")[0], 200)
                cliente = os.path.join(pasta, "cliente.galo")
                with open(cliente, "w", encoding="utf-8") as f:
                    f.write(f'mostre requisitar("http://127.0.0.1:{s.porta}/oi/Caio?q=2").json\n'
                            f'defina r como requisitar("http://127.0.0.1:{s.porta}/eco", {{"método": "POST", "json": [1]}})\n'
                            f'mostre r.status, r.ok, r.json\n'
                            f'mostre requisitar("http://127.0.0.1:{s.porta}/nada").status\n'
                            f'buscar("http://127.0.0.1:{s.porta}/num/5", nulo, função(resp) mostre "buscar:", resp.json fim)\n'
                            f'buscar("http://127.0.0.1:1/x", nulo, função(resp) mostre resp.status, resp.ok fim)\n')
                r = galo_cli("executar", cliente)
                self.assertEqual(r.stdout.splitlines(), ['{"oi": "Caio", "q": "2"}', "200 verdadeiro [1]", "404",
                                                         "buscar: 10", "0 falso"])
                self.assertEqual(s.pedir("GET", "/parar")[2], b"tchau")
                self.assertEqual(s.proc.wait(timeout=10), 0)
                self.assertEqual(s.proc.stdout.read(), "encerrado\n")
                log = s.proc.stderr.read()
                self.assertIn("GET /conta -> 200", log)
                self.assertIn("[GALO] erro em GET /quebra", log)
            finally:
                if s.proc.poll() is None:
                    s.parar()
                else:
                    s.proc.stdout.close()
                    s.proc.stderr.close()

    def test_erros_de_uso(self):
        self.assertEqual(erro_de_execucao('defina app como criar_servidor()\napp.rota("GET", "sem-barra", tamanho)').code, "G322")
        self.assertEqual(erro_de_execucao('defina app como criar_servidor()\napp.arquivos("/", "nao_existe")').code, "G326")
        self.assertEqual(erro_de_execucao('mostre requisitar("ftp://x")').code, "G325")
        self.assertEqual(erro_de_execucao('mostre elemento("#x")').code, "G327")


class TestAplicativoTarefas(unittest.TestCase):
    PASTA = os.path.join(EXEMPLOS, "tarefas")

    def test_testes_escritos_em_galo(self):
        r = galo_cli("executar", os.path.join(self.PASTA, "testes.galo"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("8 testes passaram.", r.stdout)

    def test_servidor_completo(self):
        with tempfile.TemporaryDirectory() as pasta:
            s = ServidorGalo(os.path.join(self.PASTA, "servidor.galo"), {"BANCO": os.path.join(pasta, "t.db")})
            try:
                status, _, corpo = s.pedir("POST", "/api/tarefas", {"título": "Ler a documentação"})
                self.assertEqual(status, 201)
                tarefa = json.loads(corpo)
                self.assertEqual(s.pedir("PATCH", f"/api/tarefas/{tarefa['id']}", {"feita": True})[0], 200)
                pagina = s.pedir("GET", "/")[2].decode()
                self.assertIn('<li class="feita"><span>Ler a documentação</span></li>', pagina)
                self.assertIn("1 tarefa(s), 0 pendente(s)", pagina)
                status, cab, bytecode = s.pedir("GET", "/app.galoc")
                self.assertEqual(status, 200)
                from galo.compiler.bytecode import load_module

                self.assertEqual(load_module(bytecode).source_name, "cliente.galo")
                self.assertEqual(s.pedir("GET", "/estatico/estilo.css")[0], 200)
                self.assertEqual(s.pedir("DELETE", f"/api/tarefas/{tarefa['id']}")[0], 204)
                self.assertEqual(json.loads(s.pedir("GET", "/api/tarefas")[2]), [])
            finally:
                s.parar()


if __name__ == "__main__":
    unittest.main()
