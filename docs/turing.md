# Por que a GALO é Turing-completa

Uma linguagem é **Turing-completa** quando consegue computar qualquer função que uma máquina de
Turing computa. A forma usual de provar isso é mostrar que a linguagem **simula** um modelo
universal já conhecido. Fazemos isso de duas maneiras independentes, ambas implementadas e
testadas: um simulador genérico de máquinas de Turing e um interpretador de Brainfuck.

## 1. Os ingredientes necessários

| Ingrediente | Como a GALO oferece | Onde está |
|-------------|---------------------|-----------|
| Memória ilimitada (em princípio) | listas e mapas crescem sem limite pré-definido (`adicionar`, `mapa[chave] = v`); inteiros têm precisão arbitrária | `galo/runtime/values.py` |
| Leitura e escrita da memória | `lista[i]`, `lista[i] = v`, `mapa[k]`, `mapa[k] = v` | instruções `INDEX`/`STORE_INDEX` da VM |
| Desvio condicional | `se … então … senão … fim` | `JUMP_IF_FALSE` |
| Repetição sem limite conhecido de antemão | `enquanto condição faça … fim` | `JUMP` para trás |
| Recursão geral | funções que chamam a si mesmas, inclusive de forma não primitiva (Ackermann) | pilha de quadros própria da VM |

O `enquanto` sozinho já basta para a universalidade (junto com memória ilimitada), sem depender
de recursão: é a construção que permite um número de passos que **não** é conhecido antes da
execução — e, portanto, permite também programas que nunca terminam, como exige a teoria
(problema da parada).

## 2. Simulação direta de uma máquina de Turing

Uma máquina de Turing é uma tupla (Q, Γ, b, δ, q₀, F): estados, alfabeto da fita, símbolo branco,
função de transição δ: Q × Γ → Γ × {E, D, N} × Q, estado inicial e estados finais.
A correspondência com GALO é direta ([`examples/maquina_turing.galo`](../examples/maquina_turing.galo)):

| Máquina de Turing | GALO |
|-------------------|------|
| fita infinita nos dois sentidos | `mapa` de posição (inteiro, inclusive negativo) → símbolo; posições ausentes valem `"_"` (branco) |
| cabeça de leitura | variável inteira `cabeca` |
| estado atual | variável texto `estado` |
| função de transição δ | `mapa` de `"estado,símbolo"` → `[escrever, mover, próximo]` |
| passo de computação | uma volta de `enquanto estado != "PARE" faça … fim` |

Como o mapa só guarda as células já visitadas, a fita usa memória proporcional ao que a máquina
realmente percorre, e pode crescer indefinidamente para qualquer lado. O laço não tem número de
voltas fixado: ele termina se, e somente se, a máquina simulada para.

O programa executa três máquinas, cujos resultados são conferidos pelos testes:

* incremento binário (`1011 + 1 = 1100`);
* o "castor atarefado" de 3 estados: 6 uns em 14 passos;
* o castor atarefado de 4 estados: 13 uns em 107 passos (os valores conhecidos Σ(4) = 13 e S(4) = 107).

Os testes ([`tests/test_universalidade.py`](../tests/test_universalidade.py)) também executam uma
máquina que **duplica um número unário** (1ⁿ → 1²ⁿ), cuja fita cresce com a entrada, para n = 1, 5 e 40.

## 3. Segunda prova: um interpretador de Brainfuck

Brainfuck é uma linguagem mínima (8 instruções) sabidamente Turing-completa. O arquivo
[`examples/brainfuck.galo`](../examples/brainfuck.galo) é um interpretador completo escrito em GALO:
a memória é uma `lista` que cresce sempre que o ponteiro passa do fim (ou do início), e os pares
de colchetes são resolvidos com uma pilha. Ele executa o clássico "Hello World!" e um programa que
lê a entrada e a devolve invertida. Um teste move o ponteiro por 3 000 células para exercitar a
expansão da memória.

Se a GALO interpreta qualquer programa Brainfuck, então computa tudo o que Brainfuck computa —
ou seja, tudo o que é computável.

## 4. Teoria versus prática

A completude de Turing é uma propriedade do **modelo**: ela pressupõe memória e tempo ilimitados.
Nenhum computador real tem isso, e a GALO é honesta sobre onde estão os limites:

| Recurso | Na linguagem (modelo) | Na implementação atual |
|---------|----------------------|------------------------|
| Tamanho de listas, mapas e textos | ilimitado | limitado pela memória RAM; esgotá-la gera o erro G320 |
| Tamanho de inteiros | ilimitado | limitado pela memória; `^` recusa resultados acima de ~67 milhões de bits (G317) para não travar a máquina |
| Voltas de um laço | ilimitadas | ilimitadas (só o tempo limita) |
| Profundidade de recursão | ilimitada | 100 000 chamadas aninhadas por padrão, configurável com `--limite-pilha` (G311). A VM não usa a pilha do Python para chamadas entre funções GALO, então o limite real é a memória |
| Decimais | números reais | IEEE 754 de 64 bits (precisão e alcance finitos); para computação exata use inteiros |
| Velocidade | — | a VM é escrita em Python: cerca de 3 milhões de instruções de bytecode por segundo |

Esses limites são do mesmo tipo dos de qualquer linguagem real (C, Python ou Java também esgotam
memória). Eles não afetam a universalidade: para qualquer computação que termina, existe uma
máquina com memória suficiente para executá-la, e o programa GALO não precisa ser alterado para isso.
