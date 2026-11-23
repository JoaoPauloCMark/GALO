import unittest

import auxiliar  # noqa: F401
from galo.compiler import ast as A
from galo.compiler import parse_source
from galo.errors import GaloLexError, GaloSyntaxError


def expr(src: str):
    prog = parse_source(f"mostre {src}")
    return prog.body.stmts[0].values[0]


def forma(e) -> str:
    """Representação compacta com parênteses explícitos."""
    if isinstance(e, A.Literal):
        return repr(e.value)
    if isinstance(e, A.Nome):
        return e.name
    if isinstance(e, A.Binario):
        return f"({forma(e.left)} {e.op} {forma(e.right)})"
    if isinstance(e, A.Logico):
        return f"({forma(e.left)} {e.op} {forma(e.right)})"
    if isinstance(e, A.Unario):
        return f"({e.op} {forma(e.operand)})"
    if isinstance(e, A.Comparacao):
        partes = [forma(e.operands[0])]
        for op, x in zip(e.ops, e.operands[1:]):
            partes += [op, forma(x)]
        return "(" + " ".join(partes) + ")"
    if isinstance(e, A.Chamada):
        return f"{forma(e.callee)}({', '.join(forma(a) for a in e.args)})"
    if isinstance(e, A.Indice):
        return f"{forma(e.obj)}[{forma(e.index)}]"
    if isinstance(e, A.Campo):
        return f"{forma(e.obj)}.{e.name}"
    if isinstance(e, A.ListaLit):
        return "[" + ", ".join(forma(x) for x in e.elements) + "]"
    return type(e).__name__


def erro(src: str) -> GaloSyntaxError:
    try:
        parse_source(src)
    except (GaloSyntaxError, GaloLexError) as e:
        return e
    raise AssertionError("era esperado um erro sintático")


class TestPrecedencia(unittest.TestCase):
    def test_aritmetica(self):
        self.assertEqual(forma(expr("1 + 2 * 3")), "(1 + (2 * 3))")
        self.assertEqual(forma(expr("(1 + 2) * 3")), "((1 + 2) * 3)")
        self.assertEqual(forma(expr("10 - 4 - 3")), "((10 - 4) - 3)")
        self.assertEqual(forma(expr("8 / 4 // 2 % 3")), "(((8 / 4) // 2) % 3)")

    def test_potencia(self):
        self.assertEqual(forma(expr("2 ^ 3 ^ 2")), "(2 ^ (3 ^ 2))")
        self.assertEqual(forma(expr("-2 ^ 2")), "(- (2 ^ 2))")
        self.assertEqual(forma(expr("2 ^ -1")), "(2 ^ -1)")
        self.assertEqual(forma(expr("-x ^ 2 * 3")), "((- (x ^ 2)) * 3)")

    def test_literal_negativo_dobrado(self):
        self.assertEqual(forma(expr("-5")), "-5")
        self.assertEqual(forma(expr("- 2.5")), "-2.5")

    def test_logicos(self):
        self.assertEqual(forma(expr("a ou b e c")), "(a ou (b e c))")
        self.assertEqual(forma(expr("não a e b")), "((não a) e b)")
        self.assertEqual(forma(expr("não a == b")), "(não (a == b))")
        self.assertEqual(forma(expr("a < b e c > d ou f")), "(((a < b) e (c > d)) ou f)")

    def test_comparacao_encadeada(self):
        self.assertEqual(forma(expr("0 <= x < 10")), "(0 <= x < 10)")
        self.assertEqual(forma(expr("(a < b) == c")), "((a < b) == c)")

    def test_em(self):
        self.assertEqual(forma(expr("x + 1 em lista")), "((x + 1) em lista)")

    def test_pos_fixos(self):
        self.assertEqual(forma(expr("f(1, 2)[3].nome(4)")), "f(1, 2)[3].nome(4)")
        self.assertEqual(forma(expr("-lista[1]")), "(- lista[1])")


class TestInstrucoes(unittest.TestCase):
    def test_programa_completo(self):
        prog = parse_source('programa "Teste"\ndefina x como 1\nmostre x\n')
        self.assertEqual(prog.name, "Teste")
        self.assertEqual([type(s).__name__ for s in prog.body.stmts], ["Defina", "Mostre"])

    def test_se_senao_se(self):
        prog = parse_source("se a então\n mostre 1\nsenão se b então\n mostre 2\nsenão\n mostre 3\nfim")
        se = prog.body.stmts[0]
        self.assertEqual(len(se.branches), 2)
        self.assertIsNotNone(se.else_block)

    def test_blocos_em_uma_linha(self):
        prog = parse_source("se x > 1 então mostre 1 senão mostre 2 fim")
        self.assertIsInstance(prog.body.stmts[0], A.Se)
        prog = parse_source("defina f como função(x) retorne x * 2 fim")
        self.assertIsInstance(prog.body.stmts[0].value, A.FuncaoAnonima)

    def test_ponto_e_virgula(self):
        prog = parse_source("defina a como 1; defina b como 2; mostre a, b")
        self.assertEqual(len(prog.body.stmts), 3)

    def test_lacos(self):
        prog = parse_source(
            "para i de 1 até 10 passo 2 faça\nfim\npara cada x em l faça\nfim\n"
            "para cada k, v em m faça\nfim\nrepita 3 vezes\nfim\nenquanto c faça\nfim"
        )
        tipos = [type(s).__name__ for s in prog.body.stmts]
        self.assertEqual(tipos, ["ParaIntervalo", "ParaCada", "ParaCada", "Repita", "Enquanto"])
        self.assertIsNotNone(prog.body.stmts[0].step)
        self.assertEqual(prog.body.stmts[2].var2.name, "v")

    def test_palavras_contextuais_podem_ser_nomes(self):
        prog = parse_source("defina passo como 2\ndefina vezes como 3\ndefina de como 1\nmostre passo + vezes + de")
        self.assertEqual(len(prog.body.stmts), 4)

    def test_tipos(self):
        prog = parse_source("função f(a como inteiro, b como texto ou nulo) retorna lista\nfim\n"
                            "defina x do tipo decimal como 1")
        f = prog.body.stmts[0]
        self.assertEqual(f.params[1].type.names, ["texto", "nulo"])
        self.assertEqual(f.ret.names, ["lista"])
        self.assertEqual(prog.body.stmts[1].type.names, ["decimal"])

    def test_quebras_de_linha_dentro_de_colchetes(self):
        prog = parse_source("defina l como [\n  1,\n  2,\n]\ndefina m como {\n \"a\": 1,\n}\nmostre f(\n 1,\n 2\n)")
        self.assertEqual(len(prog.body.stmts), 3)
        self.assertEqual(len(prog.body.stmts[0].value.elements), 2)

    def test_continuacao_apos_operador(self):
        prog = parse_source("defina total como 1 +\n    2 +\n    3")
        self.assertEqual(forma(prog.body.stmts[0].value), "((1 + 2) + 3)")

    def test_funcao_anonima_em_varias_linhas_dentro_de_chamada(self):
        prog = parse_source("mostre mapear(l, função(x)\n    defina y como x * 2\n    retorne y\nfim)")
        call = prog.body.stmts[0].values[0]
        self.assertEqual(len(call.args[1].body.stmts), 2)

    def test_atribuicoes(self):
        prog = parse_source("x = 1\nl[1] += 2\np.nome = \"a\"")
        alvos = [type(s.target).__name__ for s in prog.body.stmts]
        self.assertEqual(alvos, ["Nome", "Indice", "Campo"])
        self.assertEqual(prog.body.stmts[1].op, "+=")


class TestErrosSintaticos(unittest.TestCase):
    def test_falta_entao(self):
        e = erro("se x > 5\n mostre 1\nfim")
        self.assertEqual((e.code, e.line, e.col), ("G102", 1, 9))
        self.assertIn("então", e.message)

    def test_entao_trocado_por_faca(self):
        self.assertIn("'então'", erro("se x faça\nfim").message)
        self.assertIn("'faça'", erro("enquanto x então\nfim").message)

    def test_bloco_nao_fechado(self):
        e = erro("função f()\n    se verdadeiro então\n        mostre 1\nfim")
        self.assertEqual(e.code, "G103")
        self.assertTrue(e.incomplete)
        self.assertIn("linha 2", e.suggestion)

    def test_fim_sobrando(self):
        self.assertEqual(erro("mostre 1\nfim").code, "G104")

    def test_comando_com_erro_de_digitacao_nao_vira_variavel_indefinida(self):
        e = erro("defina contador como 1\nenqanto contador < 5 faça\nfim")
        self.assertEqual(e.code, "G106")
        self.assertIn("enquanto", e.suggestion)
        e = erro('mostra "oi"')
        self.assertEqual(e.code, "G106")
        self.assertIn("mostre", e.suggestion)

    def test_expressao_sem_efeito(self):
        self.assertEqual(erro("x").code, "G107")
        self.assertEqual(erro("1 + 2").code, "G107")
        self.assertEqual(erro("x == 5").code, "G107")

    def test_alvo_invalido(self):
        self.assertEqual(erro("1 + x = 3").code, "G108")
        self.assertEqual(erro("f() = 3").code, "G108")

    def test_igual_simples_em_condicao(self):
        self.assertEqual(erro("se x = 1 então\nfim").code, "G109")

    def test_senao_e_capture_fora_de_lugar(self):
        self.assertEqual(erro("senão").code, "G110")
        self.assertEqual(erro("se a então\nsenão\nsenão\nfim").code, "G110")
        e = erro("se a então\n  enquanto b faça\nsenão\nfim\nfim")
        self.assertIn("enquanto", e.message)

    def test_programa_no_meio(self):
        self.assertEqual(erro('mostre 1\nprograma "x"').code, "G111")

    def test_retorna_e_retorne(self):
        self.assertEqual(erro("função f()\n retorna 1\nfim").code, "G112")
        self.assertEqual(erro("função f() retorne inteiro\nfim").code, "G112")
        self.assertEqual(erro("função f() retorne texto ou nulo\n    retorne 1\nfim").code, "G112")

    def test_funcao_de_uma_linha_comecando_com_retorne(self):
        prog = parse_source("função dobro(n) retorne n * 2 fim\nregistro R\n    a\n    função m() retorne eu.a fim\nfim")
        self.assertEqual(type(prog.body.stmts[0].body.stmts[0]).__name__, "Retorne")
        self.assertEqual(type(prog.body.stmts[1].methods[0].body.stmts[0]).__name__, "Retorne")

    def test_palavra_reservada_como_variavel_do_erro(self):
        e = erro("tente\n    mostre 1\ncapture e\n    mostre 2\nfim")
        self.assertIn("palavra reservada", e.message)
        self.assertIn("capture erro", e.suggestion)

    def test_tente_sem_capture(self):
        self.assertIn("capture", erro("tente\n mostre 1\nfim").message)

    def test_declaracao_com_igual(self):
        e = erro("defina x = 5")
        self.assertEqual(e.code, "G102")
        self.assertIn("como", e.message)

    def test_palavra_reservada_como_nome(self):
        self.assertIn("reservada", erro("defina fim como 1").message)

    def test_virgula_faltando(self):
        self.assertIn("vírgula", erro("mostre f(1 2)").suggestion)
        self.assertIn("vírgula", erro("defina l como [1 2]").suggestion)
        self.assertIn("vírgula", erro('mostre "a" "b"').suggestion)

    def test_expressao_incompleta_marca_incompleto(self):
        self.assertTrue(erro("defina x como 1 +").incomplete)
        self.assertTrue(erro("mostre f(1,").incomplete)


if __name__ == "__main__":
    unittest.main()
