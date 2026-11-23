"""Testes que exercitam os ingredientes da completude de Turing:
memória que cresce sob demanda e laços/recursão sem limite fixado de antemão."""

import unittest

from auxiliar import executar, ler_exemplo

SIMULADOR = """
função simular(regras, estado, entrada)
    defina fita como {}
    para cada i, s em entrada faça
        fita[i - 1] = s
    fim
    defina cabeca como 0
    defina passos como 0
    defina menor como 0
    defina maior como 0
    enquanto estado != "PARE" faça
        defina acao como regras["{estado},{obter(fita, cabeca, "_")}"]
        fita[cabeca] = acao[1]
        se acao[2] == "D" então cabeca += 1 senão se acao[2] == "E" então cabeca -= 1 fim
        menor = mínimo(menor, cabeca)
        maior = máximo(maior, cabeca)
        estado = acao[3]
        passos += 1
    fim
    defina celulas como []
    para p de menor até maior faça
        adicionar(celulas, obter(fita, p, "_"))
    fim
    retorne [juntar(celulas), passos]
fim
"""

# Máquina que duplica um número unário: 1^n  ->  1^(2n).
# Estados: marca um 1 como X, vai até o fim e escreve dois Y; repete; depois troca Y por 1.
DUPLICADOR = """
defina regras como {
    "q0,1": ["X", "D", "q1"], "q0,Y": ["Y", "D", "q4"], "q0,_": ["_", "N", "PARE"],
    "q1,1": ["1", "D", "q1"], "q1,Y": ["Y", "D", "q1"], "q1,_": ["Y", "D", "q2"],
    "q2,_": ["Y", "E", "q3"],
    "q3,1": ["1", "E", "q3"], "q3,Y": ["Y", "E", "q3"], "q3,X": ["X", "D", "q0"],
    "q4,Y": ["Y", "D", "q4"], "q4,_": ["_", "E", "q5"],
    "q5,Y": ["1", "E", "q5"], "q5,X": ["_", "E", "q5"], "q5,_": ["_", "D", "PARE"]
}
"""


class TestUniversalidade(unittest.TestCase):
    def test_simulador_de_maquina_de_turing(self):
        saida = executar(ler_exemplo("maquina_turing.galo"))
        self.assertIn("1011 + 1 = 1100", saida)
        self.assertIn("6 uns em 14 passos", saida)
        self.assertIn("13 uns em 107 passos", saida)

    def test_maquina_que_cresce_a_fita(self):
        for n in (1, 5, 40):
            with self.subTest(n=n):
                fonte = SIMULADOR + DUPLICADOR + f'defina r como simular(regras, "q0", repetir("1", {n}))\nmostre r[1]\n'
                saida = executar(fonte).strip()
                self.assertEqual(saida.strip("_"), "1" * (2 * n))

    def test_interpretador_brainfuck(self):
        saida = executar(ler_exemplo("brainfuck.galo"))
        self.assertEqual(saida, "Hello World!\nOLAG\n")

    def test_brainfuck_com_fita_longa(self):
        fonte = ler_exemplo("brainfuck.galo").split("defina ola como")[0]
        # Avança 3000 células, escreve 'A' (65) e volta ao início escrevendo 'B' (66).
        programa = ">" * 3000 + "+" * 65 + "." + "<" * 3000 + "+" * 66 + "."
        saida = executar(fonte + f'mostre executar_bf("{programa}", "")')
        self.assertEqual(saida, "AB\n")

    def test_memoria_expansivel(self):
        fonte = ("defina l como []\npara i de 1 até 200000 faça\n    adicionar(l, i)\nfim\n"
                 "defina m como {}\npara i de 1 até 50000 faça\n    m[i] = i * i\nfim\n"
                 "mostre tamanho(l), l[-1], tamanho(m), m[50000]")
        self.assertEqual(executar(fonte), "200000 200000 50000 2500000000\n")

    def test_laco_sem_limite_conhecido(self):
        # Conjectura de Collatz: o número de passos não é conhecido de antemão.
        fonte = ("função collatz(n)\n    defina passos como 0\n    enquanto n != 1 faça\n"
                 "        se n % 2 == 0 então n = n // 2 senão n = 3 * n + 1 fim\n        passos += 1\n"
                 "    fim\n    retorne passos\nfim\nmostre collatz(27), collatz(97), collatz(871)")
        self.assertEqual(executar(fonte), "111 118 178\n")

    def test_recursao_nao_primitiva(self):
        # A função de Ackermann não é primitiva recursiva: exige recursão geral.
        fonte = ("função ack(m, n)\n    se m == 0 então retorne n + 1 fim\n"
                 "    se n == 0 então retorne ack(m - 1, 1) fim\n    retorne ack(m - 1, ack(m, n - 1))\nfim\n"
                 "mostre ack(2, 3), ack(3, 3)")
        self.assertEqual(executar(fonte), "9 61\n")


if __name__ == "__main__":
    unittest.main()
