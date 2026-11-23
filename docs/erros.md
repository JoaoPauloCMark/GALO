# Catálogo de erros e avisos

Todo diagnóstico da GALO segue o formato:

```text
Erro GALO [G201] — erro semântico
Arquivo: exemplo.galo
Linha: 8, coluna: 5

  8 |     mostre pontuacao
    |            ^^^^^^^^^

A variável "pontuacao" não foi definida.

Sugestão:
Declare a variável antes de utilizá-la:
defina pontuacao como 0
```

Erros de execução incluem ainda o **rastro de chamadas**. Com `--formato-curto` (usado pelos
editores) cada diagnóstico ocupa uma linha: `arquivo:linha:coluna: erro [G201]: mensagem`.

A categoria é decidida pela fase que detecta o problema: um erro de digitação em uma palavra-chave
(`enqanto`) é um **erro sintático** (G106), nunca uma "variável não definida".

## G0xx — erros léxicos (caracteres e palavras)

| Código | Situação |
|--------|----------|
| G001 | Caractere inválido (inclui aspas simples e aspas tipográficas “ ”) |
| G002 | Texto não fechado na mesma linha |
| G003 | Número malformado (`12abc`, `3.`, `1__0`) |
| G004 | Sequência de escape inválida dentro de texto (`\q`) |
| G005 | Interpolação `{...}` vazia, não fechada ou com comentário |
| G006 | Comentário de bloco `#[` sem `]#` |
| G007 | Operador de outra linguagem (`&&`, `\|\|`, `!`) |

## G1xx — erros sintáticos (estrutura)

| Código | Situação |
|--------|----------|
| G101 | Algo inesperado depois do fim de uma instrução (falta operador, vírgula ou quebra de linha) |
| G102 | Palavra ou símbolo esperado não encontrado (`então`, `faça`, `como`, `)`, `]`, ...) |
| G103 | Bloco aberto não foi fechado com `fim` (indica o bloco provável quando o `fim` está desalinhado) |
| G104 | `fim` que não fecha nenhum bloco |
| G105 | Expressão esperada (valor faltando) |
| G106 | Comando desconhecido, provavelmente erro de digitação de uma palavra-chave |
| G107 | Expressão usada como instrução sem efeito (`x`, `1 + 2`, `x == 5`) |
| G108 | Lado esquerdo de `=` não pode receber valor |
| G109 | `=` usado onde se esperava comparação (`==`) |
| G110 | `senão` ou `capture` fora de lugar |
| G111 | `programa` fora da primeira linha |
| G112 | Confusão entre `retorna` (tipo no cabeçalho) e `retorne` (instrução) |

## G2xx — erros semânticos (verificados antes da execução)

| Código | Situação |
|--------|----------|
| G201 | Variável ou função não definida (com sugestão de nome parecido) |
| G202 | Nome usado antes da sua definição no mesmo bloco |
| G203 | Nome definido duas vezes no mesmo escopo |
| G204 | Bloco interno tenta criar um nome que já existe na mesma função |
| G205 | Atribuição (`=`) a uma variável nunca declarada |
| G206 | Atribuição a uma constante |
| G207 | Atribuição a uma função (do programa ou interna) |
| G208 | `retorne` fora de uma função |
| G209 | `pare` ou `continue` fora de um laço |
| G210 | Quantidade de argumentos incorreta |
| G211 | Nome de tipo desconhecido |
| G212 | Operação impossível entre tipos conhecidos (`"a" + 1`, `1 < "b"`, percorrer um número...) |
| G213 | Valor incompatível com o tipo anotado (variável, argumento, quantidade do `repita`, valores do `para`) |
| G214 | `retorne` incompatível com o tipo de retorno da função |
| G215 | Condição ou operando lógico que não é booleano |
| G216 | Parâmetro ou variável de laço repetidos |
| G217 | Chamada de um valor que não é função |
| G219 | Acesso por posição ou campo em valor que não permite (`5[1]`, texto alterado por posição) |
| G220 | Módulo não encontrado, ilegível, ou importação circular |
| G221 | O módulo não exporta o nome pedido (inclusive nomes privados, iniciados com `_`) |
| G222 | Campo ou método inexistente em um registro (quando o tipo é conhecido na compilação) |
| G223 | Parâmetro/campo obrigatório depois de um com padrão; argumento nomeado desconhecido ou repetido |
| G224 | `importe` ou `registro` fora do nível principal do arquivo |
| G225 | `eu` usado fora de um método de registro |
| G226 | Registro com o nome de um tipo da linguagem (`texto`, `lista`...) |

## G3xx — erros de execução (detectados pela máquina virtual)

| Código | Situação |
|--------|----------|
| G301 | Global usada (ou alterada) antes de receber valor |
| G302 | Operação inválida para os tipos dos valores |
| G303 | Divisão por zero (`/`, `//`, `%`, `0 ^ negativo`) |
| G304 | Posição fora dos limites (ou posição 0) |
| G305 | Chave ou campo inexistente em mapa |
| G306 | Chamada de um valor que não é função |
| G307 | Quantidade de argumentos incorreta |
| G308 | Argumento incompatível com o tipo anotado do parâmetro |
| G309 | Retorno incompatível com o tipo anotado (inclusive terminar sem `retorne`) |
| G310 | Condição ou operando lógico não booleano |
| G311 | Estouro de pilha (recursão profunda demais) |
| G312 | Conversão de tipo impossível (`inteiro("abc")`) |
| G313 | Erro de arquivo (não encontrado, sem permissão, não é UTF-8) |
| G314 | `para cada` sobre valor que não é coleção |
| G315 | Variável anotada recebeu valor de outro tipo |
| G316 | Passo zero em laço `para` |
| G317 | Número grande demais |
| G318 | Variável capturada usada antes de receber valor |
| G320 | Memória insuficiente |
| G321 | Valor que não pode ser chave de mapa (lista, mapa, função) |
| G322 | Argumento inválido para uma função interna |
| G323 | JSON inválido, ou valor que não pode ser convertido em JSON |
| G324 | Erro no banco de dados (mensagens do SQLite traduzidas) |
| G325 | Erro de rede ao fazer uma requisição HTTP (`requisitar`) |
| G326 | Erro do servidor web (porta em uso, pasta inexistente, valor de rota inválido) |
| G327 | Função usada fora da plataforma em que existe (página no servidor, arquivos no navegador) |
| G328 | Erro em um modelo HTML (`modelo`, `renderizar`) |
| G329 | Verificação feita com `afirmar` falhou |
| G330 | Programa executado com `executar_programa` passou do tempo limite e foi interrompido |
| G331 | Programa executado com `executar_programa` escreveu mais de 1 MB de saída |

## G4xx — erros do programa

| Código | Situação |
|--------|----------|
| G400 | Erro lançado com `lance` e não capturado |

## G5xx — arquivos e bytecode

| Código | Situação |
|--------|----------|
| G501 | Arquivo de código-fonte não encontrado, ilegível ou fora de UTF-8 |
| G502 | Arquivo `.galoc` inválido, corrompido (CRC32) ou com bytecode mal formado |
| G503 | Arquivo `.galoc` de outra versão do formato |

## A2xx — avisos (não impedem a execução)

| Código | Situação |
|--------|----------|
| A201 | Nome global esconde uma função interna (`defina texto como ...`) |
| A202 | Código inalcançável depois de `retorne`, `pare`, `continue` ou `lance` |
| A203 | Função com tipo de retorno pode terminar sem `retorne` |
| A204 | Chave repetida em um mapa literal |
