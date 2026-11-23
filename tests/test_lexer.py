import unittest

import auxiliar  # noqa: F401  (ajusta o sys.path)
from galo.compiler.lexer import tokenize
from galo.compiler.tokens import InterpPart
from galo.errors import GaloLexError


def kinds(src):
    return [t.kind for t in tokenize(src)]


def lex_error(src) -> GaloLexError:
    try:
        tokenize(src)
    except GaloLexError as e:
        return e
    raise AssertionError("era esperado um erro léxico")


class TestTokens(unittest.TestCase):
    def test_palavras_chave_e_nomes(self):
        toks = tokenize("defina idade como 22")
        self.assertEqual([t.kind for t in toks], ["defina", "NOME", "como", "INTEIRO", "NL", "EOF"])
        self.assertEqual(toks[1].text, "idade")
        self.assertEqual(toks[3].value, 22)

    def test_acentos_opcionais_em_palavras_chave(self):
        self.assertEqual(kinds("se x entao")[:3], ["se", "NOME", "então"])
        self.assertEqual(kinds("funcao f() fim")[0], "função")
        self.assertEqual(kinds("enquanto x faca")[2], "faça")
        self.assertEqual(kinds("nao verdadeiro")[0], "não")
        self.assertEqual(kinds("senao")[0], "senão")

    def test_nomes_com_acento_tem_mesma_chave(self):
        a = tokenize("pontuação")[0]
        b = tokenize("pontuacao")[0]
        self.assertEqual(a.kind, "NOME")
        self.assertEqual(a.key, b.key)
        self.assertNotEqual(a.text, b.text)

    def test_maiusculas_diferenciam(self):
        a, b = tokenize("Nome nome")[:2]
        self.assertNotEqual(a.key, b.key)

    def test_numeros(self):
        toks = tokenize("42 3.14 1_000_000 2.5e3 1e-2")
        self.assertEqual([(t.kind, t.value) for t in toks[:5]],
                         [("INTEIRO", 42), ("DECIMAL", 3.14), ("INTEIRO", 1000000),
                          ("DECIMAL", 2500.0), ("DECIMAL", 0.01)])

    def test_inteiros_enormes(self):
        self.assertEqual(tokenize("123456789012345678901234567890")[0].value, 123456789012345678901234567890)

    def test_operadores(self):
        self.assertEqual(kinds("a == b != c <= d >= e < f > g")[1::2][:6], ["==", "!=", "<=", ">=", "<", ">"])
        self.assertEqual(kinds("x += 1 // 2 ^ 3 % 4")[1:9], ["+=", "INTEIRO", "//", "INTEIRO", "^", "INTEIRO", "%", "INTEIRO"])

    def test_comentarios(self):
        self.assertEqual(kinds("x # comentário\ny"), ["NOME", "NL", "NOME", "NL", "EOF"])
        self.assertEqual(kinds("a #[ bloco\n #[ aninhado ]# \n]# b"), ["NOME", "NOME", "NL", "EOF"])

    def test_linhas_vazias_sao_compactadas(self):
        self.assertEqual(kinds("a\n\n\n\nb"), ["NOME", "NL", "NOME", "NL", "EOF"])

    def test_posicoes(self):
        toks = tokenize("defina x como 1\n  mostre x")
        mostre = toks[5]
        self.assertEqual((mostre.kind, mostre.line, mostre.col), ("mostre", 2, 3))
        self.assertTrue(mostre.bol)
        self.assertFalse(toks[6].bol)

    def test_texto_simples_e_escapes(self):
        t = tokenize(r'"a\tb\n\"c\" \\ \{x\} é"')[0]
        self.assertEqual(t.value, ['a\tb\n"c" \\ {x} é'])

    def test_interpolacao(self):
        t = tokenize('"Olá, {nome}! {a + 1}"')[0]
        self.assertEqual(t.kind, "TEXTO")
        self.assertEqual(t.value[0], "Olá, ")
        self.assertIsInstance(t.value[1], InterpPart)
        self.assertEqual([x.kind for x in t.value[1].tokens], ["NOME", "EOF"])
        self.assertEqual([x.kind for x in t.value[3].tokens], ["NOME", "+", "INTEIRO", "EOF"])

    def test_interpolacao_aninhada(self):
        t = tokenize('"{ {"a": 1}["a"] } e {"x{1}"}"')[0]
        self.assertIsInstance(t.value[0], InterpPart)
        self.assertEqual(t.value[1], " e ")

    def test_bom_e_crlf(self):
        self.assertEqual(kinds("﻿a\r\nb"), ["NOME", "NL", "NOME", "NL", "EOF"])


class TestErrosLexicos(unittest.TestCase):
    def test_caractere_invalido(self):
        e = lex_error("defina x como 1 @ 2")
        self.assertEqual(e.code, "G001")
        self.assertEqual((e.line, e.col), (1, 17))

    def test_aspas_tipograficas(self):
        self.assertEqual(lex_error("“oi”").code, "G001")

    def test_texto_nao_fechado(self):
        e = lex_error('mostre "olá\nmostre 1')
        self.assertEqual((e.code, e.line, e.col), ("G002", 1, 8))

    def test_numero_malformado(self):
        self.assertEqual(lex_error("12abc").code, "G003")
        self.assertEqual(lex_error("3. + 1").code, "G003")
        self.assertEqual(lex_error("1__0").code, "G003")

    def test_escape_invalido(self):
        self.assertEqual(lex_error(r'"a\qb"').code, "G004")

    def test_interpolacao_vazia_ou_aberta(self):
        self.assertEqual(lex_error('"a {} b"').code, "G005")
        self.assertEqual(lex_error('"a {x"').code, "G005")

    def test_comentario_de_bloco_aberto(self):
        e = lex_error("#[ sem fim")
        self.assertEqual(e.code, "G006")
        self.assertTrue(e.incomplete)

    def test_operadores_de_outras_linguagens(self):
        self.assertEqual(lex_error("a && b").code, "G007")
        self.assertEqual(lex_error("a || b").code, "G007")
        self.assertEqual(lex_error("!a").code, "G007")


if __name__ == "__main__":
    unittest.main()
