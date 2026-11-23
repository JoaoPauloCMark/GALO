import os
import tempfile
import unittest

from auxiliar import erro_de_execucao, executar


def valor(expr: str) -> str:
    return executar(f"mostre {expr}").rstrip("\n")


class TestTexto(unittest.TestCase):
    def test_funcoes_de_texto(self):
        self.assertEqual(valor('maiúsculas("galo"), minúsculas("GALO"), aparar("  x  ")'), "GALO galo x")
        self.assertEqual(valor('dividir("a b  c"), dividir("a,b", ","), dividir("ab", "")'), '["a", "b", "c"] ["a", "b"] ["a", "b"]')
        self.assertEqual(valor('juntar(["a", 1, verdadeiro], "-")'), "a-1-verdadeiro")
        self.assertEqual(valor('substituir("banana", "a", "o")'), "bonono")
        self.assertEqual(valor('começa_com("galo", "ga"), termina_com("galo", "lo"), contém("galo", "al")'),
                         "verdadeiro verdadeiro verdadeiro")
        self.assertEqual(valor('posição("galo", "l"), posição("galo", "x"), posição([5, 6], 6)'), "3 nulo 2")
        self.assertEqual(valor('fatia("galinha", 1, 4), fatia("galinha", -3), fatia([1, 2, 3], 2, 9)'), 'gali nha [2, 3]')
        self.assertEqual(valor('caracteres("oi"), código("A"), caractere(97), repetir("ab", 2), inverter("galo")'),
                         '["o", "i"] 65 a abab olag')
        self.assertEqual(valor('formatar(3.14159, 2), formatar(2.5, 0), formatar(1, 3)'), "3.14 3 1.000")
        self.assertEqual(valor('é_número("42"), é_número("3,5"), é_número("abc")'), "verdadeiro verdadeiro falso")
        self.assertEqual(valor('tamanho("ação"), tamanho([1, 2]), tamanho({"a": 1})'), "4 2 1")

    def test_erros_de_argumento(self):
        self.assertEqual(erro_de_execucao('mostre maiúsculas(1)').code, "G322")
        self.assertEqual(erro_de_execucao('mostre código("ab")').code, "G322")
        self.assertEqual(erro_de_execucao('mostre tamanho(5)').code, "G322")


class TestMatematica(unittest.TestCase):
    def test_funcoes(self):
        self.assertEqual(valor("absoluto(-3), raiz(16), raiz(2)"), "3 4.0 1.4142135623730951")
        self.assertEqual(valor("arredondar(2.5), arredondar(-2.5), arredondar(3.14159, 2), arredondar(7)"), "3 -3 3.14 7")
        self.assertEqual(valor("piso(2.7), teto(2.1), piso(-2.5)"), "2 3 -3")
        self.assertEqual(valor("mínimo(3, 1, 2), máximo([4, 9, 2]), mínimo(\"b\", \"a\")"), "1 9 a")
        self.assertEqual(valor("soma([1, 2, 3.5]), média([1, 2, 3, 4]), potência(2, 10)"), "6.5 2.5 1024")
        self.assertEqual(valor("arredondar(seno(pi / 2), 6), arredondar(cosseno(0)), logaritmo(100, 10)"), "1.0 1 2.0")

    def test_aleatorio_reproduzivel(self):
        fonte = "semente_aleatória(42)\ndefina a como aleatório_entre(1, 1000)\nsemente_aleatória(42)\nmostre a == aleatório_entre(1, 1000)"
        self.assertEqual(executar(fonte), "verdadeiro\n")
        saida = executar("defina x como aleatório()\nmostre x >= 0 e x < 1")
        self.assertEqual(saida, "verdadeiro\n")

    def test_erros(self):
        self.assertEqual(erro_de_execucao("mostre raiz(-1)").code, "G322")
        self.assertEqual(erro_de_execucao("mostre mínimo([])").code, "G322")
        self.assertEqual(erro_de_execucao("mostre logaritmo(0)").code, "G322")
        self.assertEqual(erro_de_execucao('mostre soma([1, "a"])').code, "G322")
        self.assertEqual(erro_de_execucao("mostre aleatório_entre(5, 1)").code, "G322")


class TestColecoes(unittest.TestCase):
    def test_listas(self):
        fonte = ("defina l como [3, 1, 2]\ninserir(l, 1, 0)\nmostre l\nmostre remover(l, 2), l\n"
                 "mostre remover_valor(l, 2), l\nmostre ordenar([3, 1, 2.5]), ordenar([\"b\", \"a\"])\n"
                 "mostre inverter([1, 2]), intervalo(1, 5), intervalo(10, 0, -5), nova_lista(3, 0)\n"
                 "mostre primeiro(l), último(l), contar([1, 2, 1], 1), vazio([]), vazio(l)")
        self.assertEqual(executar(fonte), "[0, 3, 1, 2]\n3 [0, 1, 2]\nverdadeiro [0, 1]\n"
                                          "[1, 2.5, 3] [\"a\", \"b\"]\n[2, 1] [1, 2, 3, 4, 5] [10, 5, 0] [0, 0, 0]\n"
                                          "0 1 2 verdadeiro falso\n")

    def test_nova_lista_nao_compartilha_elementos(self):
        self.assertEqual(executar("defina m como nova_lista(2, [])\nadicionar(m[1], 9)\nmostre m"), "[[9], []]\n")

    def test_funcoes_de_ordem_superior(self):
        fonte = ("defina l como [1, 2, 3, 4]\nmostre mapear(l, função(x) retorne x * x fim)\n"
                 "mostre filtrar(l, função(x) retorne x > 2 fim)\n"
                 "mostre reduzir(l, função(a, x) retorne a + x fim, 0)\n"
                 "mostre algum(l, função(x) retorne x > 3 fim), todos(l, função(x) retorne x > 3 fim)\n"
                 "mostre ordenar_por([\"ccc\", \"a\", \"bb\"], tamanho)")
        self.assertEqual(executar(fonte), "[1, 4, 9, 16]\n[3, 4]\n10\nverdadeiro falso\n[\"a\", \"bb\", \"ccc\"]\n")

    def test_mapas(self):
        fonte = ('defina m como {"a": 1, "b": 2}\nmostre chaves(m), valores(m), pares(m)\n'
                 'mostre obter(m, "a"), obter(m, "z"), obter(m, "z", 0), obter([5], 1), obter([5], 2, "x")\n'
                 'mostre remover_chave(m, "a"), remover_chave(m, "z"), m\nlimpar(m)\nmostre m')
        self.assertEqual(executar(fonte), '["a", "b"] [1, 2] [["a", 1], ["b", 2]]\n1 nulo 0 5 x\n1 nulo {"b": 2}\n{}\n')

    def test_erros(self):
        self.assertEqual(erro_de_execucao('mostre ordenar([1, "a"])').code, "G322")
        self.assertEqual(erro_de_execucao("mostre primeiro([])").code, "G304")
        self.assertEqual(erro_de_execucao("defina l como []\ninserir(l, 5, 1)").code, "G304")
        self.assertEqual(erro_de_execucao("mostre filtrar([1], função(x) retorne 1 fim)").code, "G310")


class TestConversao(unittest.TestCase):
    def test_conversoes(self):
        self.assertEqual(valor('inteiro("42"), inteiro(3.9), inteiro(-3.9), inteiro(verdadeiro)'), "42 3 -3 1")
        self.assertEqual(valor('decimal("3.5"), decimal("3,5"), decimal(2)'), "3.5 3.5 2.0")
        self.assertEqual(valor('número("10"), número("2.5"), número(" 7 ")'), "10 2.5 7")
        self.assertEqual(valor('texto(12) + texto(verdadeiro), booleano("falso")'), "12verdadeiro falso")
        self.assertEqual(valor('tipo(1), tipo(1.0), tipo("a"), tipo([]), tipo({}), tipo(nulo), tipo(tipo), tipo(falso)'),
                         "inteiro decimal texto lista mapa nulo função booleano")

    def test_conversoes_invalidas(self):
        for expr in ['inteiro("3.5")', 'inteiro("abc")', 'decimal("x")', 'número("")', 'booleano("sim")', "booleano(1)"]:
            with self.subTest(expr=expr):
                self.assertEqual(erro_de_execucao(f"mostre {expr}").code, "G312")


class TestArquivosETempo(unittest.TestCase):
    def test_arquivos(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = os.path.join(pasta, "notas.txt").replace("\\", "/")
            fonte = (f'defina c como "{caminho}"\nescrever_arquivo(c, "linha 1\\n")\nanexar_arquivo(c, "linha 2")\n'
                     f'mostre ler_arquivo(c)\nmostre ler_linhas(c), arquivo_existe(c)\n'
                     f'mostre listar_arquivos("{pasta}")\napagar_arquivo(c)\nmostre arquivo_existe(c)')
            self.assertEqual(executar(fonte), 'linha 1\nlinha 2\n["linha 1", "linha 2"] verdadeiro\n["notas.txt"]\nfalso\n')

    def test_arquivo_inexistente(self):
        e = erro_de_execucao('mostre ler_arquivo("/caminho/que/nao/existe.txt")')
        self.assertEqual(e.code, "G313")
        self.assertIn("não foi encontrado", e.message)

    def test_tempo(self):
        fonte = ("defina a como agora()\nmostre tipo(a.ano), a.mes >= 1 e a.mês <= 12, tipo(a.dia_da_semana)\n"
                 "mostre tamanho(data_atual()), tamanho(hora_atual()), tipo(tempo())\nespere(0)")
        self.assertEqual(executar(fonte), "inteiro verdadeiro texto\n10 8 decimal\n")


if __name__ == "__main__":
    unittest.main()
