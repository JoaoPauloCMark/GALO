import unittest

from auxiliar import erro_de_execucao, executar


def valor(expr: str) -> str:
    return executar(f"mostre {expr}").rstrip("\n")


class TestAritmetica(unittest.TestCase):
    def test_operacoes_basicas(self):
        self.assertEqual(valor("1 + 2 * 3"), "7")
        self.assertEqual(valor("(1 + 2) * 3"), "9")
        self.assertEqual(valor("10 - 4 - 3"), "3")
        self.assertEqual(valor("2 ^ 3 ^ 2"), "512")
        self.assertEqual(valor("-2 ^ 2"), "-4")

    def test_divisoes(self):
        self.assertEqual(valor("7 / 2"), "3.5")
        self.assertEqual(valor("6 / 2"), "3.0")
        self.assertEqual(valor("7 // 2"), "3")
        self.assertEqual(valor("-7 // 2"), "-4")
        self.assertEqual(valor("7 % 3"), "1")
        self.assertEqual(valor("-7 % 3"), "2")
        self.assertEqual(valor("7.5 // 2"), "3.0")

    def test_inteiros_e_decimais(self):
        self.assertEqual(valor("1 + 2.5"), "3.5")
        self.assertEqual(valor("0.1 + 0.2"), "0.30000000000000004")
        self.assertEqual(valor("2 ^ -1"), "0.5")
        self.assertEqual(valor("2 ^ 0.5"), "1.4142135623730951")

    def test_inteiros_sem_limite(self):
        self.assertEqual(valor("2 ^ 200"), str(2 ** 200))
        self.assertEqual(valor("12345678901234567890 * 98765432109876543210"),
                         str(12345678901234567890 * 98765432109876543210))

    def test_erros_aritmeticos(self):
        self.assertEqual(erro_de_execucao("defina z como 0\nmostre 1 / z").code, "G303")
        self.assertEqual(erro_de_execucao("defina z como 0\nmostre 1 % z").code, "G303")
        self.assertEqual(erro_de_execucao("defina z como 0\nmostre 1 // z").code, "G303")
        self.assertEqual(erro_de_execucao("defina z como 0\nmostre z ^ -1").code, "G303")
        self.assertEqual(erro_de_execucao("defina b como 10\nmostre b ^ 10 ^ 10").code, "G317")
        self.assertEqual(erro_de_execucao("defina b como -8.0\nmostre b ^ 0.5").code, "G302")

    def test_erro_de_tipo_em_execucao(self):
        e = erro_de_execucao('função f(a, b)\n    retorne a + b\nfim\nmostre f("x", 1)')
        self.assertEqual(e.code, "G302")
        self.assertEqual(e.line, 2)
        self.assertIn("interpolação", e.suggestion)
        self.assertEqual([t[0] for t in e.trace], ["<programa>", "f"])

    def test_booleanos_nao_sao_numeros(self):
        self.assertEqual(erro_de_execucao("função f(x)\n    retorne x + 1\nfim\nmostre f(verdadeiro)").code, "G302")


class TestComparacoesETexto(unittest.TestCase):
    def test_igualdade(self):
        self.assertEqual(valor("1 == 1.0"), "verdadeiro")
        self.assertEqual(valor("1 == verdadeiro"), "falso")
        self.assertEqual(valor('1 == "1"'), "falso")
        self.assertEqual(valor("[1, [2, 3]] == [1, [2, 3]]"), "verdadeiro")
        self.assertEqual(valor('{"a": 1} == {"a": 1.0}'), "verdadeiro")
        self.assertEqual(valor("nulo == nulo"), "verdadeiro")
        self.assertEqual(valor("[1, 2] != [2, 1]"), "verdadeiro")

    def test_ordem(self):
        self.assertEqual(valor('"abacate" < "banana"'), "verdadeiro")
        self.assertEqual(valor("1 < 2 <= 2 < 3"), "verdadeiro")
        self.assertEqual(valor("3 > 2 > 5"), "falso")

    def test_comparacao_encadeada_avalia_uma_vez(self):
        fonte = ("defina n como 0\nfunção f()\n    n += 1\n    retorne 5\nfim\n"
                 "mostre 1 < f() < 10, n")
        self.assertEqual(executar(fonte), "verdadeiro 1\n")

    def test_comparar_tipos_diferentes_e_erro(self):
        self.assertEqual(erro_de_execucao('defina a como "1"\nmostre a < 2').code, "G302")

    def test_logica_curto_circuito(self):
        fonte = "função explode()\n    retorne 1 / 0\nfim\nmostre falso e explode() > 0, verdadeiro ou explode() > 0"
        self.assertEqual(executar(fonte), "falso verdadeiro\n")

    def test_operadores_logicos_exigem_booleanos(self):
        self.assertEqual(erro_de_execucao("defina x como 1\nmostre x e verdadeiro").code, "G310")
        self.assertEqual(erro_de_execucao("defina x como 1\nse x então\nfim").code, "G310")

    def test_textos(self):
        self.assertEqual(valor('"GA" + "LO"'), "GALO")
        self.assertEqual(valor('"-" * 5'), "-----")
        self.assertEqual(valor('"galo"[1] + "galo"[-1]'), "go")
        self.assertEqual(valor('"lo" em "galo"'), "verdadeiro")
        self.assertEqual(executar('defina n como "Ana"\nmostre "Oi, {n}! {1 + 1} {[1, "a"]}"'), 'Oi, Ana! 2 [1, "a"]\n')

    def test_exibicao(self):
        self.assertEqual(valor('[1, 2.5, "a", verdadeiro, nulo, {"k": falso}]'),
                         '[1, 2.5, "a", verdadeiro, nulo, {"k": falso}]')


class TestControleDeFluxo(unittest.TestCase):
    def test_se_senao_se(self):
        fonte = ("para cada n em [5, 15, 25] faça\n    se n < 10 então\n        mostre \"pequeno\"\n"
                 "    senão se n < 20 então\n        mostre \"médio\"\n    senão\n        mostre \"grande\"\n    fim\nfim")
        self.assertEqual(executar(fonte), "pequeno\nmédio\ngrande\n")

    def test_enquanto(self):
        self.assertEqual(executar("defina i como 0\nenquanto i < 3 faça\n    i += 1\nfim\nmostre i"), "3\n")

    def test_para_intervalo(self):
        self.assertEqual(executar("para i de 1 até 3 faça\n    escreva(i)\nfim"), "123")
        self.assertEqual(executar("para i de 3 até 1 faça\n    escreva(i)\nfim"), "321")
        self.assertEqual(executar("para i de 0 até 10 passo 5 faça\n    escreva(i, \"\")\nfim"), "0 5 10 ")
        self.assertEqual(executar("para i de 1 até 10 passo -1 faça\n    escreva(i)\nfim"), "")
        self.assertEqual(executar("para x de 0 até 1 passo 0.25 faça\n    escreva(x, \"\")\nfim"), "0.0 0.25 0.5 0.75 1.0 ")

    def test_passo_zero(self):
        self.assertEqual(erro_de_execucao("defina p como 0\npara i de 1 até 2 passo p faça\nfim").code, "G316")

    def test_para_cada(self):
        self.assertEqual(executar('para cada c em "abc" faça\n    escreva(c + "-")\nfim'), "a-b-c-")
        self.assertEqual(executar('para cada k, v em {"a": 1, "b": 2} faça\n    escreva(k, v, "")\nfim'), "a 1 b 2 ")
        self.assertEqual(executar('para cada i, x em ["x", "y"] faça\n    escreva(i, x, "")\nfim'), "1 x 2 y ")
        self.assertEqual(executar('para cada k em {"a": 1, "b": 2} faça\n    escreva(k)\nfim'), "ab")

    def test_para_cada_percorre_copia(self):
        fonte = "defina l como [1, 2]\npara cada x em l faça\n    adicionar(l, x)\nfim\nmostre l"
        self.assertEqual(executar(fonte), "[1, 2, 1, 2]\n")

    def test_para_cada_em_valor_invalido(self):
        self.assertEqual(erro_de_execucao("defina n como 5\npara cada x em n faça\nfim").code, "G314")

    def test_repita(self):
        self.assertEqual(executar("repita 3 vezes\n    escreva(\"*\")\nfim"), "***")
        self.assertEqual(executar("defina n como -1\nrepita n vezes\n    escreva(\"*\")\nfim"), "")

    def test_pare_e_continue(self):
        fonte = ("para i de 1 até 10 faça\n    se i % 2 == 0 então continue fim\n"
                 "    se i > 7 então pare fim\n    escreva(i)\nfim")
        self.assertEqual(executar(fonte), "1357")
        fonte = "defina i como 0\nenquanto verdadeiro faça\n    i += 1\n    se i == 4 então pare fim\nfim\nmostre i"
        self.assertEqual(executar(fonte), "4\n")

    def test_lacos_aninhados_com_pare(self):
        fonte = ("para cada a em [1, 2, 3] faça\n    para cada b em [1, 2, 3] faça\n"
                 "        se b > a então pare fim\n        escreva(a * b, \"\")\n    fim\nfim")
        self.assertEqual(executar(fonte), "1 2 4 3 6 9 ")

    def test_variavel_do_laco_e_nova_a_cada_volta(self):
        fonte = ("defina fs como []\npara i de 1 até 3 faça\n    adicionar(fs, função() retorne i fim)\nfim\n"
                 "mostre mapear(fs, função(f) retorne f() fim)")
        self.assertEqual(executar(fonte), "[1, 2, 3]\n")


class TestFuncoes(unittest.TestCase):
    def test_retorno_e_nulo_implicito(self):
        fonte = "função f()\n    mostre \"oi\"\nfim\nmostre f()"
        self.assertEqual(executar(fonte), "oi\nnulo\n")

    def test_recursao(self):
        fonte = ("função fatorial(n como inteiro) retorna inteiro\n    se n <= 1 então\n        retorne 1\n"
                 "    fim\n    retorne n * fatorial(n - 1)\nfim\nmostre fatorial(5), fatorial(20)")
        self.assertEqual(executar(fonte), "120 2432902008176640000\n")

    def test_recursao_mutua(self):
        fonte = ("função par(n)\n    se n == 0 então retorne verdadeiro fim\n    retorne ímpar(n - 1)\nfim\n"
                 "função ímpar(n)\n    se n == 0 então retorne falso fim\n    retorne par(n - 1)\nfim\n"
                 "mostre par(100), ímpar(7)")
        self.assertEqual(executar(fonte), "verdadeiro verdadeiro\n")

    def test_recursao_profunda_nao_usa_pilha_do_python(self):
        fonte = "função conta(n)\n    se n == 0 então retorne 0 fim\n    retorne 1 + conta(n - 1)\nfim\nmostre conta(50000)"
        self.assertEqual(executar(fonte), "50000\n")

    def test_estouro_de_pilha(self):
        e = erro_de_execucao("função f(n)\n    retorne f(n + 1)\nfim\nf(1)", max_frames=500)
        self.assertEqual(e.code, "G311")
        self.assertEqual(len(e.trace), 500)

    def test_closures(self):
        fonte = ("função contador()\n    defina n como 0\n    retorne função()\n        n += 1\n        retorne n\n"
                 "    fim\nfim\ndefina a como contador()\ndefina b como contador()\na()\na()\nb()\nmostre a(), b()")
        self.assertEqual(executar(fonte), "3 2\n")

    def test_closure_de_varios_niveis(self):
        fonte = ("função f(x)\n    retorne função(y)\n        retorne função(z)\n            retorne x + y + z\n"
                 "        fim\n    fim\nfim\nmostre f(1)(10)(100)")
        self.assertEqual(executar(fonte), "111\n")

    def test_funcao_que_usa_variavel_definida_depois(self):
        fonte = "função f()\n    retorne limite * 2\nfim\ndefina limite como 21\nmostre f()"
        self.assertEqual(executar(fonte), "42\n")
        e = erro_de_execucao("função f()\n    retorne limite\nfim\nmostre f()\ndefina limite como 1")
        self.assertEqual(e.code, "G301")

    def test_closure_usada_antes_da_variavel(self):
        fonte = "função externa()\n    função g()\n        retorne y\n    fim\n    mostre g()\n    defina y como 1\nfim\nexterna()"
        self.assertEqual(erro_de_execucao(fonte).code, "G318")

    def test_funcoes_como_valores(self):
        fonte = ("função aplicar(f, x)\n    retorne f(x)\nfim\n"
                 "mostre aplicar(função(n) retorne n * n fim, 7), aplicar(tamanho, \"galo\")")
        self.assertEqual(executar(fonte), "49 4\n")

    def test_chamar_nao_funcao_em_execucao(self):
        self.assertEqual(erro_de_execucao("defina f como 3\nf()").code, "G306")

    def test_aridade_em_execucao(self):
        e = erro_de_execucao("defina f como função(a) retorne a fim\nmostre f(1, 2)")
        self.assertEqual(e.code, "G307")

    def test_tipos_de_parametro_e_retorno(self):
        self.assertEqual(erro_de_execucao("função f(n como inteiro)\nfim\ndefina x como \"a\"\nf(x)").code, "G308")
        self.assertEqual(erro_de_execucao("função f(x) retorna inteiro\n    retorne x\nfim\nf(\"a\")").code, "G309")
        self.assertEqual(erro_de_execucao("função f(x) retorna inteiro\n    se x então retorne 1 fim\nfim\nf(falso)").code, "G309")
        self.assertEqual(executar("função f(x como decimal) retorna decimal\n    retorne x\nfim\nmostre f(2)"), "2.0\n")
        self.assertEqual(executar("função f(x como texto ou nulo)\n    retorne x\nfim\nmostre f(nulo)"), "nulo\n")

    def test_variavel_tipada_em_execucao(self):
        fonte = "defina idade do tipo inteiro como 1\nfunção ruim()\n    retorne \"x\"\nfim\nidade = ruim()"
        self.assertEqual(erro_de_execucao(fonte).code, "G315")


class TestColecoes(unittest.TestCase):
    def test_listas(self):
        fonte = ("defina l como [10, 20, 30]\nl[2] = 25\nadicionar(l, 40)\nl[1] += 1\n"
                 "mostre l, l[-1], tamanho(l)")
        self.assertEqual(executar(fonte), "[11, 25, 30, 40] 40 4\n")

    def test_listas_sao_compartilhadas_por_referencia(self):
        self.assertEqual(executar("defina a como [1]\ndefina b como a\nadicionar(b, 2)\nmostre a"), "[1, 2]\n")
        self.assertEqual(executar("defina a como [1]\ndefina b como copiar(a)\nadicionar(b, 2)\nmostre a"), "[1]\n")

    def test_indices_invalidos(self):
        e = erro_de_execucao("defina l como [1, 2]\nmostre l[3]")
        self.assertEqual(e.code, "G304")
        self.assertIn("a lista tem 2 elementos", e.message)
        self.assertIn("primeira posição é 1", erro_de_execucao("defina l como [1]\nmostre l[0]").message)
        self.assertEqual(erro_de_execucao('defina l como [1]\nmostre l["a"]').code, "G302")

    def test_mapas(self):
        fonte = ('defina m como {"a": 1}\nm["b"] = 2\nm.c = 3\nm.a += 10\n'
                 'mostre m, m.b, "c" em m, tamanho(m)')
        self.assertEqual(executar(fonte), '{"a": 11, "b": 2, "c": 3} 2 verdadeiro 3\n')

    def test_chaves_de_tipos_diferentes(self):
        fonte = 'defina m como {}\nm[1] = "um"\nm[verdadeiro] = "v"\nm["1"] = "texto"\nmostre m[1], m[verdadeiro], m["1"], tamanho(m)'
        self.assertEqual(executar(fonte), "um v texto 3\n")

    def test_campo_ignora_acentos(self):
        self.assertEqual(executar('defina d como {"mês": 11}\nmostre d.mes, d.mês'), "11 11\n")

    def test_erros_de_mapa(self):
        self.assertEqual(erro_de_execucao('defina m como {}\nmostre m["x"]').code, "G305")
        self.assertEqual(erro_de_execucao('defina m como {}\nmostre m.x').code, "G305")
        self.assertEqual(erro_de_execucao('defina m como {}\nm[[1]] = 2').code, "G321")
        self.assertEqual(erro_de_execucao('defina l como [1]\nmostre l.x').code, "G302")

    def test_estruturas_aninhadas(self):
        fonte = 'defina dados como {"lista": [1, {"x": [5]}]}\ndados.lista[2].x[1] = 6\nmostre dados'
        self.assertEqual(executar(fonte), '{"lista": [1, {"x": [6]}]}\n')

    def test_lista_que_contem_a_si_mesma(self):
        self.assertEqual(executar("defina l como [1]\nadicionar(l, l)\nmostre l"), "[1, [...]]\n")


class TestErrosTratados(unittest.TestCase):
    def test_capture_erro_da_linguagem(self):
        fonte = "tente\n    mostre 1 / 0\ncapture erro\n    mostre erro.código, erro.linha\nfim"
        self.assertEqual(executar(fonte), "G303 2\n")

    def test_lance_texto_e_mapa(self):
        fonte = ('tente\n    lance "falhou"\ncapture erro\n    mostre erro.mensagem, erro.código\nfim\n'
                 'tente\n    lance {"mensagem": "x", "dado": 42}\ncapture erro\n    mostre erro.dado\nfim')
        self.assertEqual(executar(fonte), "falhou G400\n42\n")

    def test_erro_atravessa_chamadas(self):
        fonte = ("função c()\n    lance \"profundo\"\nfim\nfunção b()\n    c()\n    mostre \"não chega\"\nfim\n"
                 "tente\n    b()\ncapture falha\n    mostre \"ok:\", falha.mensagem\nfim\nmostre \"continua\"")
        self.assertEqual(executar(fonte), "ok: profundo\ncontinua\n")

    def test_relancar_e_aninhar(self):
        fonte = ("tente\n    tente\n        lance \"a\"\n    capture x\n        lance \"b: \" + x.mensagem\n    fim\n"
                 "capture y\n    mostre y.mensagem\nfim")
        self.assertEqual(executar(fonte), "b: a\n")

    def test_pare_dentro_de_tente(self):
        fonte = ("para i de 1 até 5 faça\n    tente\n        se i == 3 então pare fim\n        escreva(i)\n"
                 "    capture\n    fim\nfim\ntente\n    lance \"depois\"\ncapture erro\n    mostre \"\", erro.mensagem\nfim")
        self.assertEqual(executar(fonte), "12 depois\n")

    def test_erro_em_funcao_interna_com_callback(self):
        fonte = ("tente\n    mostre mapear([1, 0], função(x) retorne 1 / x fim)\ncapture erro\n"
                 "    mostre erro.código\nfim\nmostre mapear([1, 2], função(x) retorne x + 1 fim)")
        self.assertEqual(executar(fonte), "G303\n[2, 3]\n")

    def test_erro_nao_capturado(self):
        e = erro_de_execucao('lance "socorro"')
        self.assertEqual((e.code, e.message, e.line), ("G400", "socorro", 1))


class TestEntrada(unittest.TestCase):
    def test_leia(self):
        fonte = 'defina nome como leia("Nome: ")\nmostre "Oi, {nome}"\nmostre leia()'
        self.assertEqual(executar(fonte, entradas=["Ana"]), "Nome: Oi, Ana\nnulo\n")

    def test_argumentos(self):
        self.assertEqual(executar("mostre argumentos()", args=["a", "b"]), '["a", "b"]\n')


if __name__ == "__main__":
    unittest.main()
