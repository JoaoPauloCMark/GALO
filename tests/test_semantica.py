import unittest

from auxiliar import avisos, codigos, erros_de_compilacao, executar


class TestNomesEEscopos(unittest.TestCase):
    def test_variavel_indefinida_com_mensagem_oficial(self):
        (e,) = erros_de_compilacao("defina x como 1\nmostre pontuacao")
        self.assertEqual(e.code, "G201")
        self.assertEqual((e.line, e.col), (2, 8))
        self.assertEqual(e.message, 'A variável "pontuacao" não foi definida.')
        self.assertIn("defina pontuacao como 0", e.suggestion)

    def test_sugere_nome_parecido(self):
        (e,) = erros_de_compilacao("defina contador como 1\nmostre contdor")
        self.assertIn("contador", e.suggestion)
        (e,) = erros_de_compilacao("mostre tamaho([1])")
        self.assertIn("tamanho", e.suggestion)

    def test_acentos_nao_diferenciam_nomes(self):
        self.assertEqual(executar("defina pontuação como 7\nmostre pontuacao"), "7\n")
        self.assertEqual(executar("mostre maiusculas(\"a\"), maiúsculas(\"b\")"), "A B\n")

    def test_uso_antes_da_definicao(self):
        self.assertEqual(codigos("mostre x\ndefina x como 1"), ["G202"])
        self.assertEqual(codigos("defina x como x + 1"), ["G202"])

    def test_escopo_de_bloco(self):
        fonte = "se verdadeiro então\n    defina interno como 1\nfim\nmostre interno"
        self.assertEqual(codigos(fonte), ["G201"])
        self.assertEqual(codigos("para i de 1 até 3 faça\nfim\nmostre i"), ["G201"])

    def test_redefinicao_no_mesmo_escopo(self):
        self.assertEqual(codigos("defina a como 1\ndefina a como 2"), ["G203"])
        self.assertEqual(codigos("função f()\nfim\ndefina f como 1"), ["G203"])

    def test_ocultacao_proibida_dentro_da_mesma_funcao(self):
        fonte = "defina total como 0\npara cada x em [1] faça\n    defina total como x\nfim"
        self.assertEqual(codigos(fonte), ["G204"])

    def test_ocultacao_permitida_entre_funcoes(self):
        fonte = "defina x como 1\nfunção f(x)\n    retorne x * 10\nfim\nmostre f(2), x"
        self.assertEqual(executar(fonte), "20 1\n")

    def test_atribuicao_sem_declaracao(self):
        self.assertEqual(codigos("x = 5"), ["G205"])

    def test_constante_e_funcao_nao_podem_ser_alteradas(self):
        self.assertEqual(codigos("constante LIMITE como 10\nLIMITE = 11"), ["G206"])
        self.assertEqual(codigos("função f()\nfim\nf = 1"), ["G207"])
        self.assertEqual(codigos("tamanho = 1"), ["G207"])

    def test_retorne_fora_de_funcao(self):
        self.assertEqual(codigos("retorne 1"), ["G208"])

    def test_pare_continue_fora_de_laco(self):
        self.assertEqual(codigos("pare"), ["G209"])
        self.assertEqual(codigos("enquanto verdadeiro faça\n    função f()\n        pare\n    fim\n    pare\nfim"), ["G209"])

    def test_parametro_duplicado(self):
        self.assertEqual(codigos("função f(a, a)\nfim"), ["G216"])

    def test_funcoes_podem_ser_usadas_antes_de_definidas(self):
        fonte = "mostre dobro(4)\nfunção dobro(n)\n    retorne n * 2\nfim"
        self.assertEqual(executar(fonte), "8\n")

    def test_varios_erros_sao_reportados_juntos(self):
        self.assertEqual(codigos("mostre a\nmostre b\nx = 1"), ["G201", "G201", "G205"])


class TestVerificacoesDeTipo(unittest.TestCase):
    def test_operacoes_invalidas_com_literais(self):
        self.assertEqual(codigos('defina a como "x" + 2'), ["G212"])
        self.assertEqual(codigos('defina y como 1\ndefina a como "x" - y'), ["G212"])
        self.assertEqual(codigos('mostre -"texto"'), ["G212"])
        self.assertEqual(codigos('mostre 1 < "a"'), ["G212"])
        self.assertEqual(codigos('mostre 1 em 5'), ["G212"])

    def test_condicoes_precisam_ser_booleanas(self):
        self.assertEqual(codigos("se 1 então\nfim"), ["G215"])
        self.assertEqual(codigos('enquanto "sim" faça\nfim'), ["G215"])
        self.assertEqual(codigos("mostre 1 e verdadeiro"), ["G215"])
        self.assertEqual(codigos("mostre não 3"), ["G215"])

    def test_aridade(self):
        self.assertEqual(codigos("função f(a, b)\nfim\nf(1)"), ["G210"])
        self.assertEqual(codigos("tamanho(1, 2)"), ["G210"])
        self.assertEqual(codigos("aleatório(1)"), ["G210"])

    def test_tipos_anotados(self):
        self.assertEqual(codigos('defina idade do tipo inteiro como "vinte"'), ["G213"])
        self.assertEqual(codigos('defina idade do tipo inteiro como 20\nidade = "x"'), ["G213"])
        self.assertEqual(codigos('função f(n como inteiro)\nfim\nf("a")'), ["G213"])
        self.assertEqual(codigos('função f() retorna inteiro\n    retorne "a"\nfim'), ["G214"])
        self.assertEqual(codigos("defina x do tipo inteiri como 1"), ["G211"])

    def test_tipo_decimal_aceita_inteiro(self):
        self.assertEqual(codigos("defina x do tipo decimal como 1"), [])
        self.assertEqual(executar("defina x do tipo decimal como 1\nmostre x"), "1.0\n")

    def test_chamar_valor_que_nao_e_funcao(self):
        self.assertEqual(codigos("constante N como 3\nN()"), ["G217"])

    def test_indexacao_invalida(self):
        self.assertEqual(codigos("mostre 5[1]"), ["G219"])
        self.assertEqual(codigos('defina t como "abc"\nt[1] = "x"'), [])
        self.assertEqual(codigos('constante T como "abc"\nT[1] = "x"'), ["G219"])

    def test_inferencia_e_conservadora(self):
        # Tipos desconhecidos (parâmetros sem anotação) não geram erro estático.
        self.assertEqual(codigos("função f(a, b)\n    retorne a + b\nfim\nmostre f(1, 2)"), [])


class TestAvisos(unittest.TestCase):
    def test_nome_que_esconde_funcao_interna(self):
        self.assertEqual(avisos('defina texto como "abc"\nmostre texto'), ["A201"])

    def test_codigo_inalcancavel(self):
        self.assertEqual(avisos("função f()\n    retorne 1\n    mostre 2\nfim"), ["A202"])

    def test_funcao_pode_terminar_sem_retornar(self):
        self.assertEqual(avisos("função f(x) retorna inteiro\n    se x então\n        retorne 1\n    fim\nfim"), ["A203"])
        self.assertEqual(avisos("função f(x) retorna inteiro\n    se x então\n        retorne 1\n    senão\n        retorne 2\n    fim\nfim"), [])

    def test_chave_duplicada(self):
        self.assertEqual(avisos('mostre {"a": 1, "a": 2}'), ["A204"])


if __name__ == "__main__":
    unittest.main()
