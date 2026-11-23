# Especificação da linguagem GALO 0.2

A sintaxe formal está em [grammar.md](grammar.md). Este documento define o
**significado** de cada construção. Quando o texto diz que algo "é um erro", o
código do erro aparece entre colchetes; o catálogo completo está em [erros.md](erros.md).

## 1. Princípios

1. **Português legível, mas formal.** Cada construção tem uma única interpretação. Não há
   interpretação de linguagem natural livre nem inferência "esperta" em tempo de execução.
2. **Sem conversões silenciosas.** `"Idade: " + 20` é um erro, não `"Idade: 20"`. Booleanos não
   são números. Condições precisam ser booleanas.
3. **Erros cedo e claros.** O que pode ser provado errado antes da execução é acusado pelo
   compilador; o resto é verificado pela máquina virtual, sempre com posição e sugestão.
4. **Determinismo.** Com a mesma entrada, um programa produz a mesma saída. As únicas fontes de
   não determinismo são explícitas: `leia`, `aleatório*` (controlável com `semente_aleatória`),
   funções de data/hora e o sistema de arquivos.

## 2. Estrutura de um programa

Um programa é uma sequência de instruções, executadas de cima para baixo. A primeira linha pode
ser `programa "Nome"`, que apenas registra o nome do programa (ele é gravado no bytecode).

Blocos começam em `então`, `faça`, `vezes`, `senão`, `tente`, `capture` ou no cabeçalho de uma
função, e terminam em `fim` (ou no próximo `senão`/`capture` do mesmo comando). A indentação é
apenas visual. Um bloco pode ficar em uma linha só: `se x > 0 então mostre x fim`.

## 3. Tipos e valores

| Tipo | Valores | Literais | Observações |
|------|---------|----------|-------------|
| `inteiro` | inteiros de tamanho **ilimitado** | `42`, `-7`, `1_000_000` | `2 ^ 1000` é exato |
| `decimal` | ponto flutuante IEEE 754 de 64 bits | `3.14`, `2.5e3`, `1e-9` | `0.1 + 0.2` é `0.30000000000000004` |
| `número` | `inteiro` ou `decimal` | — | só existe em anotações de tipo |
| `texto` | sequência imutável de caracteres Unicode | `"Olá, {nome}!"`, `'literal'`, `"""várias linhas"""` | posições a partir de 1 |
| `booleano` | `verdadeiro`, `falso` | | **não** é número |
| `nulo` | `nulo` | | ausência de valor |
| `lista` | sequência mutável de valores quaisquer | `[1, "a", [2]]` | posições a partir de 1 |
| `mapa` | associação chave → valor, na ordem de inserção | `{"nome": "Ana", 1: verdadeiro}` | mutável |
| `função` | funções do programa e funções internas | `função(x) retorne x fim` | valores de primeira classe |
| registros | tipos definidos com `registro` (ex.: `Tarefa`) | `Tarefa("x")` | `tipo(t)` é `"Tarefa"` |
| `módulo` | arquivo importado com `importe ... como` | — | acesso com `modulo.nome` |

A função interna `tipo(x)` devolve o nome do tipo como texto.

## 4. Nomes, variáveis e escopos

### 4.1 Nomes

Nomes ignoram acentos e cedilha (`ação` = `acao`), mas diferenciam maiúsculas (`Nome` ≠ `nome`).
Mensagens de erro mostram o nome como foi escrito na declaração.

### 4.2 Declaração e atribuição

* `defina x como valor` cria a variável `x` no escopo atual. Toda variável nasce com valor.
* `constante X como valor` cria um nome que não pode receber outro valor [G206].
* `x = valor` altera uma variável **já declarada**; usar `=` com um nome inexistente é erro [G205].
* `x += v`, `-=`, `*=`, `/=` equivalem a `x = x + v` etc., avaliando o alvo uma única vez
  (em `lista[f()] += 1`, `f()` é chamada uma vez).
* Ordem de avaliação: sempre da esquerda para a direita. Em `alvo = valor`, primeiro o objeto e a
  posição do alvo, depois o valor.

### 4.3 Escopos

O escopo é **léxico e de bloco**:

* Variáveis declaradas no nível do programa são **globais**: visíveis em todo o programa, inclusive
  dentro de funções.
* Cada bloco (`se`, `enquanto`, `para`, `repita`, `tente`, `capture`, corpo de função) cria um escopo
  novo. Variáveis declaradas nele deixam de existir no `fim` do bloco.
* A variável de um `para`/`para cada` pertence ao corpo do laço e é **uma nova variável a cada
  volta**: funções criadas dentro do laço lembram o valor daquela volta.
* Usar um nome antes da sua declaração no mesmo bloco é erro [G202]. Um nome que não existe em
  nenhum escopo é erro [G201].
* Declarar duas vezes o mesmo nome no mesmo escopo é erro [G203].
* **Regra anti-ocultação:** dentro de uma mesma função (ou do programa principal), um bloco interno
  não pode declarar um nome que já está visível de um bloco externo [G204]. Isso evita o erro
  clássico de "criar outra variável sem querer" dentro de um laço. Parâmetros e variáveis de uma
  função **podem** ter o mesmo nome de globais.
* Funções declaradas com `função nome(...)` ficam disponíveis em todo o bloco onde aparecem, mesmo
  antes da linha da declaração (permite recursão mútua). O nome de uma função é constante [G207].
* Uma função pode usar uma global declarada mais abaixo no programa; se for chamada antes de a
  global receber valor, ocorre o erro de execução [G301].

## 5. Operadores

### 5.1 Aritméticos

| Operação | `inteiro ∘ inteiro` | com `decimal` | Outros tipos |
|----------|--------------------|---------------|--------------|
| `a + b` | inteiro | decimal | `texto + texto` concatena; `lista + lista` cria nova lista |
| `a - b`, `a * b` | inteiro | decimal | `texto * inteiro` e `inteiro * texto` repetem o texto |
| `a / b` | **sempre decimal** (`7 / 2` = `3.5`, `6 / 2` = `3.0`) | decimal | — |
| `a // b` | inteiro, arredondado para baixo (`-7 // 2` = `-4`) | decimal arredondado para baixo | — |
| `a % b` | resto com o sinal do divisor (`-7 % 3` = `2`) | decimal | — |
| `a ^ b` | inteiro se `b ≥ 0`; decimal se `b < 0` | decimal | — |
| `-a`, `+a` | | | só números |

* Divisão, `//`, `%` por zero e `0 ^ negativo` são erros [G303].
* Combinações não listadas são erros [G302] (ou [G212] quando o compilador já sabe os tipos).
* `^` com resultado inteiro gigantesco (mais de ~67 milhões de bits) é recusado [G317]; potência de
  base negativa com expoente fracionário não é real [G302].
* Decimais seguem IEEE 754. Uma operação entre valores finitos cujo resultado exceda ~1.8e308 é
  erro [G317]; resultados pequenos demais viram zero.
* **Resultados exatos e reproduzíveis:** a divisão de inteiros (`/`) e a potência com expoente
  inteiro (`2.5 ^ 3`, `10 ^ -30`) são calculadas com a fração exata e arredondadas uma única vez para
  o decimal mais próximo; `//` e `%` entre decimais aplicam o piso ao quociente exato (`6e2 // 0.1`
  é `5999.0`, porque `0.1` vale um pouco mais que um décimo). Por isso o mesmo programa dá o mesmo
  resultado em qualquer plataforma, inclusive no navegador.
* **Funções matemáticas corretamente arredondadas:** `seno`, `cosseno`, `tangente`, `logaritmo` (com
  ou sem base) e as potências com expoente fracionário (`2 ^ 0.5`, `8 ^ (1 / 3)`) não usam a
  biblioteca matemática do sistema: a própria GALO calcula o valor com precisão suficiente para
  devolver o decimal mais próximo do resultado exato. Assim elas dão os mesmos bits em qualquer
  sistema e navegador, e resultados exatos saem exatos: `logaritmo(1000, 10)` é `3.0` e
  `2.25 ^ 0.5` é `1.5`. A redução do ângulo é exata mesmo para argumentos enormes (`seno(1e22)` é
  `-0.8522008497671888`). `raiz` usa a raiz quadrada do IEEE 754, que já é corretamente arredondada.
  Valores infinitos ou indefinidos são recusados [G322].
* `aleatório`, `aleatório_entre` e `semente_aleatória` usam o gerador xoshiro128\*\* (semente
  expandida por splitmix32), implementado igualmente nas duas VMs: a mesma semente produz a mesma
  sequência no servidor e no navegador. O gerador não é criptográfico; para senhas e sessões use
  `token_aleatório()`.

### 5.2 Comparações

* `==` e `!=` aceitam quaisquer valores. Valores de tipos diferentes são sempre diferentes, com uma
  exceção: inteiros e decimais são comparados numericamente (`1 == 1.0`). Assim, `1 == verdadeiro`
  é `falso` e `1 == "1"` é `falso`. Listas e mapas são comparados pelo conteúdo, recursivamente.
  Funções são iguais apenas a si mesmas.
* `<`, `<=`, `>`, `>=` comparam números com números e textos com textos (ordem dos códigos Unicode).
  Outras combinações são erro [G302].
* Comparações podem ser encadeadas: `0 <= nota <= 10` significa `0 <= nota e nota <= 10`, avaliando
  `nota` uma única vez.
* `x em coleção`: pertence à lista (pela igualdade acima); é trecho do texto (`x` precisa ser texto);
  é chave do mapa.

### 5.3 Lógicos

`e`, `ou` e `não` exigem booleanos [G310/G215] e devolvem booleanos. `e` e `ou` são de curto-circuito:
o lado direito só é avaliado se necessário.

### 5.4 Condições

As condições de `se` e `enquanto` precisam ser booleanas [G215 em compilação, G310 em execução].
Não existe "valor verdadeiro implícito": em vez de `se lista então`, escreva `se tamanho(lista) > 0 então`.

## 6. Conversões e coerções

A única conversão implícita é **inteiro → decimal**: em operações aritméticas mistas e quando um
inteiro é atribuído a algo anotado como `decimal` (o valor passa a ser `2.0`). Todas as outras
conversões são explícitas: `texto(x)`, `inteiro(x)` (trunca decimais em direção a zero),
`decimal(x)`, `número(texto)` e `booleano(texto)`. `número` e `decimal` aceitam vírgula como
separador decimal quando o texto não contém ponto (`"3,5"` → `3.5`). Conversões impossíveis são
erros [G312].

## 7. Controle de fluxo

* `se c então … senão se d então … senão … fim`: executa o primeiro bloco cuja condição é verdadeira.
* `enquanto c faça … fim`: avalia `c` antes de cada volta; o número de voltas não precisa ser
  conhecido de antemão.
* `repita n vezes … fim`: `n` é avaliado uma vez e precisa ser inteiro; `n ≤ 0` executa zero vezes.
* `para i de a até b [passo p] faça … fim`:
  * `a`, `b` e `p` são avaliados uma vez, antes do laço; o fim `b` é **inclusivo**.
  * Sem `passo`, conta para cima se `a ≤ b` e para baixo se `a > b` (`para i de 10 até 1` conta 10, 9, …, 1).
  * Com `passo`, a direção é a do sinal do passo; se ela não leva de `a` a `b`, o laço não executa.
    Passo zero é erro [G316].
  * Com decimais, o valor da volta `k` é `a + k·p` (sem acúmulo de erro) e o fim aceita uma folga de
    `|p|·10⁻⁹`.
  * Alterar `i` dentro do corpo não afeta as próximas voltas.
* `para cada x em coleção faça … fim` percorre os elementos de uma lista, os caracteres de um texto ou
  as chaves de um mapa. A coleção é **copiada** no início: alterá-la durante o laço não muda as voltas.
  Com duas variáveis, `para cada i, x em lista` dá a posição (a partir de 1) e o elemento;
  `para cada c, v em mapa` dá chave e valor.
* `pare` sai do laço mais interno; `continue` vai para a próxima volta. Fora de laços, são erros [G209].

### 7.1 Expressão condicional

`se c então a senão b` é uma **expressão**: avalia `c` (que precisa ser booleana) e depois apenas
um dos lados. Ex.: `defina situação como se nota >= 6 então "aprovado" senão "reprovado"`.

## 8. Funções

```galo
função somar(a como número, b como número) retorna número
    retorne a + b
fim
```

* Os argumentos são avaliados da esquerda para a direita e passados **por valor**; listas e mapas são
  valores de referência (a função pode alterar a lista recebida, mas não a variável de quem chamou).
* A quantidade de argumentos deve ser exata [G210 em compilação, G307 em execução].
* `retorne v` encerra a função devolvendo `v`; `retorne` sozinho ou o fim do corpo devolvem `nulo`.
  `retorne` fora de funções é erro [G208].
* Funções são valores: podem ser guardadas em variáveis, listas e mapas, passadas como argumento e
  devolvidas. `função(x) retorne x * 2 fim` cria uma função sem nome.
* **Closures:** uma função lembra as variáveis do escopo onde foi criada (não uma cópia: a própria
  variável). Duas closures criadas pela mesma chamada compartilham as variáveis.
* A recursão é ilimitada em princípio; na prática o padrão é 100 000 chamadas aninhadas
  (`--limite-pilha` muda o valor). Ultrapassá-lo é o erro [G311], com o rastro de chamadas.

### 8.1 Valores padrão e argumentos nomeados

```galo
função saudar(nome como texto, saudação = "Olá", pontuação = "!")
    retorne "{saudação}, {nome}{pontuação}"
fim
saudar("Ana")                          # Olá, Ana!
saudar("Bia", pontuação: "?")          # Olá, Bia?
saudar(saudação: "Oi", nome: "Caio")   # Oi, Caio!
```

* O valor padrão é uma expressão avaliada **a cada chamada** em que o argumento falta (por isso
  `lista = []` cria uma lista nova a cada vez) e pode usar parâmetros anteriores: `fim = início + 10`.
* Parâmetros sem padrão não podem vir depois de parâmetros com padrão [G223].
* Argumentos nomeados (`nome: valor`) vêm depois dos posicionais; nomes desconhecidos, repetidos ou
  que já receberam valor pela posição são erros [G223/G307]. Faltar um argumento obrigatório é [G210/G307].
* Funções internas aceitam apenas argumentos posicionais.

## 8A. Registros (tipos definidos pelo usuário)

```galo
registro Conta
    titular como texto
    saldo como decimal = 0
    histórico = []

    função depositar(valor como número)
        eu.saldo += valor
        adicionar(eu.histórico, valor)
        retorne eu
    fim
fim

defina c como Conta("Ana")           # ou Conta(titular: "Ana", saldo: 10)
c.depositar(10).depositar(5)
mostre c.saldo, tipo(c)              # 15.0 Conta
```

* Um registro define campos (com tipo e valor padrão opcionais, como parâmetros) e métodos. O nome
  do registro é uma função que cria instâncias: os argumentos seguem a ordem dos campos.
* Forma curta: `registro Ponto(x como número, y como número = 0)`.
* Dentro de um método, `eu` é a instância que recebeu a chamada. `eu` fora de métodos é erro [G225].
* Só os campos declarados existem: ler ou alterar outro nome é erro [G222 na compilação quando o tipo é
  conhecido, G305 na execução]. Campos com tipo são verificados ao criar e ao alterar [G213/G315].
* Instâncias são valores de referência (como listas). `==` compara tipo e campos. São exibidas como
  `Conta(titular: "Ana", saldo: 15.0, histórico: [10, 5])` e viram objetos em `para_json`.
* Nomes de registros podem ser usados como tipos: `função f(c como Conta) retorna Conta`.
* `obj.método` sem chamar devolve um método ligado (uma função que já sabe quem é `eu`).
* Registros só podem ser definidos no nível principal do arquivo [G224] e não podem ter o nome de um
  tipo da linguagem [G226].

## 8B. Módulos

```galo
importe "biblioteca/datas.galo" como datas       # datas.formatar(...)
importe Tarefa, criar_tarefa de "modelos"         # nomes diretos (".galo" é opcional)
```

* O caminho é relativo à pasta do arquivo que importa. Arquivo inexistente ou importação circular é
  erro [G220]; `importe` fora do nível principal é erro [G224].
* Um módulo é compilado e executado **uma única vez** por programa, na primeira importação; as
  demais recebem o mesmo módulo (variáveis globais do módulo são compartilhadas).
* Cada módulo tem suas próprias variáveis globais. São exportados todos os nomes do nível principal,
  exceto os que começam com `_` e os que o próprio módulo importou. Pedir um nome não exportado é
  erro [G221 na compilação, G305 na execução].
* `importe a de "m"` copia o **valor** de `a` no momento da importação (como uma constante do
  importador); para ver alterações posteriores de uma variável do módulo, use `m.a` com `importe ... como`.
* O compilador verifica quantidade e tipos dos argumentos também em chamadas a funções e registros
  importados.
* `galo compilar` inclui todos os módulos no `.galoc`.

## 9. Anotações de tipo (opcionais)

Podem anotar variáveis (`defina idade do tipo inteiro como 0`), constantes, parâmetros
(`n como inteiro`) e retornos (`retorna texto ou nulo`). Tipos podem ser unidos com `ou`; `número`
equivale a `inteiro ou decimal`; `qualquer` desliga a verificação.

* O **compilador** acusa incompatibilidades que consegue provar (literal de tipo errado, chamada a
  função declarada com argumento de tipo errado, `retorne` incompatível) [G213, G214].
* A **máquina virtual** verifica toda atribuição a variável anotada [G315], todo argumento de
  parâmetro anotado [G308] e todo retorno de função anotada [G309].
* Uma variável anotada mantém o tipo para sempre; variáveis não anotadas podem mudar de tipo.

## 10. Coleções

### 10.1 Listas e textos

* Posições começam em **1**; posições negativas contam do fim (`l[-1]` é o último). A posição 0 não
  existe [G304]. Posições fora dos limites são erros [G304] — inclusive ao escrever: para crescer a
  lista use `adicionar` ou `inserir`.
* Textos são imutáveis: `t[1] = "x"` é erro [G219/G302]. `t[i]` devolve um texto de 1 caractere.
* Atribuir uma lista a outra variável não a copia; use `copiar(lista)`.

### 10.2 Mapas

* Chaves podem ser textos, números, booleanos ou `nulo` [G321]. `1` e `1.0` são a mesma chave;
  `1` e `verdadeiro` são chaves diferentes.
* `mapa[chave]` com chave inexistente é erro [G305]; use `chave em mapa` ou `obter(mapa, chave, padrão)`.
* `mapa.campo` é o mesmo que `mapa["campo"]`. Como acontece com os nomes, a busca de campos ignora
  acentos quando não há uma chave exatamente igual (`data.mes` encontra a chave `"mês"`).
* A ordem de inserção é preservada na exibição e nos laços.

## 11. Erros e tratamento

Há quatro categorias de erro, sempre com código, posição e, quando possível, sugestão:
**léxico** (G0xx), **sintático** (G1xx), **semântico** (G2xx, antes da execução) e **de execução**
(G3xx). Erros de compilação impedem o programa de começar. Avisos (A2xx) não impedem.

```galo
tente
    defina n como número(leia("Número: "))
capture erro
    mostre "Inválido: {erro.mensagem} (código {erro.código}, linha {erro.linha})"
fim
```

* `lance valor` interrompe a execução com um erro do programa [G400]. Se `valor` for um mapa, ele
  próprio é entregue ao `capture` (permitindo campos extras); caso contrário, o `capture` recebe um
  mapa `{"mensagem": ..., "código": "G400", "linha": ..., "valor": valor}`.
* Erros de execução da linguagem também podem ser capturados; a variável recebe um mapa com
  `mensagem`, `código` e `linha`.
* O erro sobe pelas chamadas até encontrar o `tente` mais próximo; se não houver, o programa termina
  com a mensagem e o rastro de chamadas (código de saída 2).
* A variável do `capture` é opcional (`capture` sozinho apenas ignora o erro).

## 12. Entrada e saída

* `mostre a, b, c` escreve os valores separados por espaço e pula de linha. `mostre` sozinho pula uma linha.
* `escreva(a, b)` faz o mesmo sem pular de linha. `leia([mensagem])` lê uma linha (sem o `\n`) e
  devolve `nulo` quando a entrada acabou.
* **Exibição:** textos aparecem sem aspas no nível de cima e com aspas dentro de coleções
  (`["Ana", 1]`); booleanos como `verdadeiro`/`falso`; decimais na forma mais curta que representa o
  valor exatamente (`3.5`, `1e-09`, `infinito`); listas que contêm a si mesmas aparecem como `[...]`.
  A interpolação `"{x}"` usa a mesma regra de `mostre`.
* **Caminhos relativos** usados por arquivos, banco de dados e modelos partem da **pasta do programa
  principal** (no REPL, da pasta atual), e não da pasta em que o terminal está.

## 13. Modo interativo (REPL)

O REPL compila e executa cada entrada na mesma sessão: variáveis, constantes e funções globais
continuam existindo. Diferenças em relação a um arquivo:

* expressões soltas mostram o valor (`2 + 3` mostra `5`; textos aparecem entre aspas);
* um nome global pode ser redefinido com `defina`/`função` (útil para experimentar), mas constantes
  continuam protegidas contra `=`;
* uma definição cuja execução falhou não fica registrada.

## 14. Limites práticos

A linguagem não impõe limites ao tamanho de inteiros, textos, listas ou mapas, nem ao número de
voltas de um laço. Os limites práticos são da máquina: memória disponível [G320], profundidade de
chamadas (`--limite-pilha`, padrão 100 000) [G311] e o tamanho máximo de resultados de `^` [G317].
Veja [turing.md](turing.md) para a discussão entre o modelo teórico e esses limites.
