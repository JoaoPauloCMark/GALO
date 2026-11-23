"""Recursos da linguagem acrescentados na versão 0.2: módulos, registros, valores
padrão, argumentos nomeados, `se` como expressão e textos multilinha/literais."""

import io
import os
import tempfile
import unittest

from auxiliar import codigos, erro_de_execucao, executar, galo_cli
from galo.compiler import compile_source
from galo.compiler.bytecode import dump_module, load_module
from galo.errors import CompilationError
from galo.runtime.vm import VM


def escrever(pasta, nome, conteudo):
    caminho = os.path.join(pasta, nome)
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(conteudo)
    return caminho


class TestTextos(unittest.TestCase):
    def test_multilinha_remove_recuo_comum(self):
        fonte = 'função f(x)\n    retorne """\n        <p>{x}</p>\n          fim\n        """\nfim\nescreva(f(1))'
        self.assertEqual(executar(fonte), "<p>1</p>\n  fim\n")

    def test_multilinha_em_uma_linha_e_escapes(self):
        self.assertEqual(executar('mostre """a "b" {1 + 1}\\tc"""'), 'a "b" 2\tc\n')

    def test_aspas_simples_sao_literais(self):
        self.assertEqual(executar("mostre '{nao} interpola \\' ok'"), "{nao} interpola ' ok\n")
        self.assertEqual(executar("escreva('''\n    {{ x }}\n    ''')"), "{{ x }}\n")
        self.assertEqual(executar("mostre corresponde(\"12345\", '^[0-9]{5}$')"), "verdadeiro\n")

    def test_multilinha_nao_fechado(self):
        self.assertEqual(codigos('mostre """abc\n'), ["G002"])


class TestExpressaoSe(unittest.TestCase):
    def test_valor_condicional(self):
        self.assertEqual(executar('defina n como 7\nmostre se n % 2 == 0 então "par" senão "ímpar"'), "ímpar\n")
        self.assertEqual(executar('mostre "{se verdadeiro então 1 senão 2}"'), "1\n")

    def test_avalia_so_um_lado(self):
        self.assertEqual(executar("função x()\n    retorne 1 / 0\nfim\nmostre se falso então x() senão 9"), "9\n")

    def test_exige_senao_e_booleano(self):
        self.assertEqual(codigos("mostre se verdadeiro então 1"), ["G102"])
        self.assertEqual(codigos("mostre se 1 então 1 senão 2"), ["G215"])


class TestParametros(unittest.TestCase):
    def test_valores_padrao_e_nomeados(self):
        fonte = ('função saudar(nome, saudação = "Olá", fim_ = "!")\n    retorne "{saudação}, {nome}{fim_}"\nfim\n'
                 'mostre saudar("Ana")\nmostre saudar("Bia", fim_: "?")\nmostre saudar(saudação: "Oi", nome: "Caio")')
        self.assertEqual(executar(fonte), "Olá, Ana!\nOlá, Bia?\nOi, Caio!\n")

    def test_padrao_avaliado_a_cada_chamada_e_usa_parametros_anteriores(self):
        fonte = ("função f(a, b = a * 2, lista = [])\n    adicionar(lista, a)\n    retorne [b, tamanho(lista)]\nfim\n"
                 "mostre f(1), f(2), f(3, 0)")
        self.assertEqual(executar(fonte), "[2, 1] [4, 1] [0, 1]\n")

    def test_padrao_capturado_por_closure(self):
        fonte = "função f(x = 5)\n    retorne função() retorne x fim\nfim\nmostre f()(), f(2)()"
        self.assertEqual(executar(fonte), "5 2\n")

    def test_padrao_com_tipo(self):
        self.assertEqual(executar("função f(x como decimal = 1)\n    retorne x\nfim\nmostre f()"), "1.0\n")
        self.assertEqual(codigos('função f(x como inteiro = "a")\nfim'), ["G213"])

    def test_erros_estaticos(self):
        self.assertEqual(codigos("função f(a = 1, b)\nfim"), ["G223"])
        self.assertEqual(codigos("função f(a, b = 1)\nfim\nf()"), ["G210"])
        self.assertEqual(codigos("função f(a)\nfim\nf(b: 1)"), ["G210", "G223"])
        self.assertEqual(codigos("função f(a)\nfim\nf(1, a: 2)"), ["G223"])
        self.assertEqual(codigos("mostre tamanho(valor: [1])"), ["G223"])
        self.assertEqual(codigos('mostre f(a: 1, 2)'), ["G102"])

    def test_erros_em_execucao(self):
        self.assertEqual(erro_de_execucao("defina f como função(a) retorne a fim\nf(b: 1)").code, "G307")
        self.assertEqual(erro_de_execucao("defina f como função(a, b = 1) retorne a fim\nf(b: 2)").code, "G307")
        self.assertEqual(erro_de_execucao("defina f como tamanho\nf(valor: 1)").code, "G307")


REGISTRO = """
registro Conta
    titular como texto
    saldo como decimal = 0
    histórico = []

    função depositar(valor como número)
        se valor <= 0 então
            lance "Depósito deve ser positivo"
        fim
        eu.saldo += valor
        adicionar(eu.histórico, valor)
        retorne eu
    fim

    função resumo() retorna texto
        retorne "{eu.titular}: {formatar(eu.saldo, 2)}"
    fim
fim
"""


class TestRegistros(unittest.TestCase):
    def test_campos_metodos_e_eu(self):
        fonte = REGISTRO + 'defina c como Conta("Ana")\nc.depositar(10).depositar(5)\nmostre c.resumo(), c.histórico, tipo(c)'
        self.assertEqual(executar(fonte), "Ana: 15.00 [10, 5] Conta\n")

    def test_padrao_mutavel_nao_e_compartilhado(self):
        fonte = REGISTRO + 'defina a como Conta("A")\ndefina b como Conta("B")\na.depositar(1)\nmostre b.histórico'
        self.assertEqual(executar(fonte), "[]\n")

    def test_exibicao_igualdade_e_json(self):
        fonte = ('registro Ponto(x, y = 0)\nmostre Ponto(1), Ponto(1) == Ponto(1, 0), Ponto(1) == Ponto(2)\n'
                 'mostre para_json(Ponto(1, 2)), [Ponto(y: 3, x: 4)]')
        self.assertEqual(executar(fonte), 'Ponto(x: 1, y: 0) verdadeiro falso\n{"x":1,"y":2} [Ponto(x: 4, y: 3)]\n')

    def test_registros_como_tipos(self):
        fonte = ("registro P(x como inteiro)\nfunção dobro(p como P) retorna P\n    retorne P(p.x * 2)\nfim\n"
                 "mostre dobro(P(4)).x")
        self.assertEqual(executar(fonte), "8\n")
        self.assertEqual(codigos("registro P(x)\nfunção f(p como P)\nfim\nf(1)"), ["G213"])
        self.assertEqual(erro_de_execucao("registro P(x)\nfunção f(p como P)\nfim\ndefina v como 1\nf(v)").code, "G308")

    def test_metodo_como_valor(self):
        fonte = REGISTRO + 'defina c como Conta("Ana")\ndefina dep como c.depositar\ndep(3)\nmostre c.saldo'
        self.assertEqual(executar(fonte), "3.0\n")

    def test_verificacoes_estaticas(self):
        self.assertEqual(codigos(REGISTRO + 'defina c do tipo Conta como Conta("x")\nmostre c.sald'), ["G222"])
        self.assertEqual(codigos(REGISTRO + 'defina c do tipo Conta como Conta("x")\nc.saldo = "muito"'), ["G213"])
        self.assertEqual(codigos(REGISTRO + 'constante c como Conta("x")\nc.depositar = 1'), ["G222"])
        self.assertEqual(codigos(REGISTRO + 'defina c como Conta(1)'), ["G213"])
        self.assertEqual(codigos(REGISTRO + 'defina c como Conta()'), ["G210"])
        self.assertEqual(codigos(REGISTRO + 'defina c como Conta("x", saldos: 1)'), ["G223"])
        self.assertEqual(codigos("registro R\n    função m()\n        mostre eu.nada\n    fim\nfim"), ["G222"])
        self.assertEqual(codigos("mostre eu"), ["G225"])
        self.assertEqual(codigos("função f()\n    registro R(a)\nfim"), ["G224"])
        self.assertEqual(codigos("registro texto(a)"), ["G226"])
        self.assertEqual(codigos("registro R(a, a)"), ["G216"])
        self.assertEqual(codigos("registro R\n    a\n    função a()\n    fim\nfim"), ["G216"])

    def test_verificacoes_em_execucao(self):
        base = REGISTRO + 'defina c como Conta("Ana")\ndefina alvo como c\n'
        self.assertEqual(erro_de_execucao(base + "mostre alvo.sald").code, "G305")
        self.assertEqual(erro_de_execucao(base + 'defina v como "x"\nalvo.saldo = v').code, "G315")
        self.assertEqual(erro_de_execucao(base + "alvo.depositar(-1)").code, "G400")

    def test_registro_no_repl(self):
        from galo.session import Session

        out = io.StringIO()
        s = Session(out=out)
        s.execute("registro P(x)")
        s.execute("defina p como P(3)")
        s.execute("p.x")
        self.assertEqual(out.getvalue(), "3\n")


class TestModulos(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.pasta = self._tmp.name
        escrever(self.pasta, "lib/util.galo",
                 'registro Item(nome como texto, preço como número = 0)\n'
                 'defina contador como 0\n'
                 'função contar()\n    contador += 1\n    retorne contador\nfim\n'
                 'função _segredo()\n    retorne 42\nfim\n'
                 'mostre "carregando util"\n')
        escrever(self.pasta, "lib/outro.galo", 'importe contar de "util.galo"\nfunção contar_duas()\n    contar()\n    retorne contar()\nfim\n')

    def tearDown(self):
        self._tmp.cleanup()

    def rodar(self, fonte):
        principal = escrever(self.pasta, "principal.galo", fonte)
        r = galo_cli("executar", principal)
        return r

    def test_importar_como_e_por_nome(self):
        r = self.rodar('importe "lib/util.galo" como util\nimporte Item, contar de "lib/util"\n'
                       'mostre util.contar(), contar(), util.Item("a"), Item(preço: 2, nome: "b"), tipo(util)')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, 'carregando util\n1 2 Item(nome: "a", preço: 0) Item(nome: "b", preço: 2) módulo\n')

    def test_modulo_executa_uma_vez_e_estado_e_compartilhado(self):
        r = self.rodar('importe "lib/util.galo" como u\nimporte contar_duas de "lib/outro.galo"\nmostre u.contar(), contar_duas()')
        self.assertEqual(r.stdout, "carregando util\n1 3\n")

    def test_nomes_privados_e_inexistentes(self):
        self.assertIn("[G221]", self.rodar('importe _segredo de "lib/util.galo"').stderr)
        r = self.rodar('importe "lib/util.galo" como u\nmostre u.contr()')
        self.assertIn("[G221]", r.stderr)
        self.assertIn("contar", r.stderr)

    def test_verificacao_estatica_atravessa_modulos(self):
        r = self.rodar('importe Item de "lib/util.galo"\nmostre Item(nome: 1)')
        self.assertIn("[G213]", r.stderr)
        r = self.rodar('importe "lib/util.galo" como u\nmostre u.contar(1)')
        self.assertIn("[G210]", r.stderr)

    def test_erros_de_importacao(self):
        self.assertIn("[G220]", self.rodar('importe "nao_existe.galo" como x').stderr)
        escrever(self.pasta, "a.galo", 'importe "b.galo" como b\n')
        escrever(self.pasta, "b.galo", 'importe "a.galo" como a\n')
        r = galo_cli("executar", os.path.join(self.pasta, "a.galo"))
        self.assertIn("Importação circular: a.galo → b.galo → a.galo", r.stderr)
        self.assertIn("[G224]", self.rodar('se verdadeiro então\n    importe "lib/util.galo" como u\nfim').stderr)

    def test_erro_dentro_do_modulo_mostra_o_arquivo_certo(self):
        escrever(self.pasta, "lib/ruim.galo", "defina x como 1\nmostre indefinida\n")
        r = self.rodar('importe "lib/ruim.galo" como r')
        self.assertIn("Arquivo: lib/ruim.galo", r.stderr)
        self.assertIn("2 | mostre indefinida", r.stderr)

    def test_erro_de_execucao_em_modulo(self):
        escrever(self.pasta, "lib/falha.galo", "função dividir(a, b)\n    retorne a / b\nfim\n")
        r = self.rodar('importe dividir de "lib/falha.galo"\nmostre dividir(1, 0)')
        self.assertEqual(r.returncode, 2)
        self.assertIn("Arquivo: lib/falha.galo", r.stderr)
        self.assertIn("retorne a / b", r.stderr)

    def test_galoc_inclui_os_modulos(self):
        principal = escrever(self.pasta, "principal.galo", 'importe contar_duas de "lib/outro.galo"\nmostre contar_duas()')
        with open(principal, encoding="utf-8") as f:
            resultado = compile_source(f.read(), principal)
        modulo = load_module(dump_module(resultado.module))
        self.assertEqual(sorted(m.name for m in modulo.modules), ["lib/outro.galo", "lib/util.galo"])
        out = io.StringIO()
        VM(out=out).run(modulo)
        self.assertEqual(out.getvalue(), "carregando util\n2\n")

    def test_caminhos_relativos_partem_do_programa(self):
        escrever(self.pasta, "dados.txt", "conteúdo")
        principal = escrever(self.pasta, "le.galo", 'mostre ler_arquivo("dados.txt")')
        r = galo_cli("executar", principal, cwd=tempfile.gettempdir())
        self.assertEqual(r.stdout, "conteúdo\n")


class TestBytecodeV2(unittest.TestCase):
    def test_ida_e_volta_com_recursos_novos(self):
        fonte = (REGISTRO + 'função f(a, b = 2)\n    retorne a + b\nfim\n'
                 'defina c como Conta("Ana")\nc.depositar(4)\nmostre c.resumo(), f(1), f(b: 5, a: 1), se c.saldo > 1 então "x" senão "y"')
        modulo = compile_source(fonte).module
        out1, out2 = io.StringIO(), io.StringIO()
        VM(out=out1).run(modulo)
        VM(out=out2).run(load_module(dump_module(modulo)))
        self.assertEqual(out1.getvalue(), out2.getvalue())
        self.assertEqual(out1.getvalue(), "Ana: 4.00 3 6 x\n")


if __name__ == "__main__":
    unittest.main()
