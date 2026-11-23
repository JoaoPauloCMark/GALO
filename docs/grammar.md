# Gramática formal da GALO

Esta é a gramática oficial da GALO 0.2, em EBNF (ISO 14977 simplificada):
`{ x }` repete zero ou mais vezes, `[ x ]` é opcional, `|` separa alternativas e
textos entre aspas simples são símbolos terminais. Cada regra sintática
corresponde a um método `parse_*` em [`galo/compiler/parser.py`](../galo/compiler/parser.py).

## 1. Léxico

O código-fonte é texto Unicode em UTF-8, normalizado para NFC antes da análise
(assim `é` digitado como um único caractere ou como `e` + acento combinante é a mesma coisa).
Quebras de linha `\r\n` e `\r` viram `\n`; um BOM inicial é ignorado.

```ebnf
letra          = ? caractere Unicode da categoria L (letras, inclusive acentuadas) ? | '_' ;
dígito         = '0' | '1' | '2' | '3' | '4' | '5' | '6' | '7' | '8' | '9' ;
nome           = letra , { letra | dígito } ;          (* que não seja palavra reservada *)

inteiro        = dígitos ;
decimal        = dígitos , '.' , dígitos , [ expoente ] | dígitos , expoente ;
dígitos        = dígito , { [ '_' ] , dígito } ;        (* 1_000_000 *)
expoente       = ( 'e' | 'E' ) , [ '+' | '-' ] , dígito , { dígito } ;

texto          = texto-interpolado | texto-multilinha | texto-literal | texto-literal-multilinha ;
texto-interpolado = '"' , { caractere-de-texto | escape | interpolação } , '"' ;
texto-multilinha  = '"""' , { qualquer-caractere | escape | interpolação } , '"""' ;
texto-literal     = "'" , { ? qualquer caractere exceto "'" e quebra de linha ? | "\'" } , "'" ;
texto-literal-multilinha = "'''" , { ? qualquer caractere ? | "\'" } , "'''" ;
caractere-de-texto = ? qualquer caractere exceto '"', '\', '{' e quebra de linha ? ;
escape         = '\' , ( 'n' | 't' | 'r' | '0' | '"' | "'" | '\' | '{' | '}' )
               | '\u' , hex , hex , hex , hex ;
interpolação   = '{' , expressão , '}' ;               (* na mesma linha *)

comentário     = '#' , { ? qualquer caractere exceto quebra de linha ? }
               | '#[' , { ? qualquer coisa, inclusive outro comentário de bloco ? } , ']#' ;
```

Regras léxicas importantes:

* **Nomes ignoram acentos e cedilha**: `pontuação` e `pontuacao` são o mesmo nome; o mesmo vale
  para palavras reservadas (`então`/`entao`, `função`/`funcao`, `faça`/`faca`, `não`/`nao`,
  `senão`/`senao`, `até`/`ate`). Maiúsculas e minúsculas **são** diferentes.
* Um número não pode ser seguido imediatamente de letras (`12abc` é erro G003) e o ponto decimal
  exige dígitos dos dois lados (`3.` e `.5` são erros).
* Textos entre aspas duplas aceitam interpolação `{expressão}` e escapes (`\n`, `\t`, `\"`...).
  Para escrever chaves literais neles, use `\{` e `\}`.
* Textos entre **aspas simples** são literais: nada é especial, exceto `\'` (a própria aspa).
  São ideais para expressões regulares (`'^\d{5}$'`), JSON e modelos HTML (`'{{ nome }}'`).
* Textos entre aspas triplas (`"""` ou `'''`) podem ocupar várias linhas. A quebra de linha logo
  após as aspas de abertura é ignorada, e o recuo comum é removido — a posição das aspas de
  fechamento define o recuo. Uma linha final só com espaços antes das aspas de fechamento não faz parte do texto.

### Palavras reservadas

```
programa defina constante como mostre se então senão fim enquanto faça repita
para em função retorna retorne pare continue tente capture lance e ou não
verdadeiro falso nulo importe registro eu
```

Atenção: `e` é o operador lógico e, portanto, não pode ser nome de variável (use `erro`, `elem`, `evento`...).

### Palavras contextuais

Têm significado especial apenas em certas posições e **podem** ser usadas como nomes:
`cada`, `de`, `até`, `passo`, `vezes`, `do`, `tipo`. Os nomes de tipos (`inteiro`,
`decimal`, `número`, `texto`, `booleano`, `lista`, `mapa`, `qualquer`) também não são
reservados: em posição de tipo indicam o tipo; em expressões são nomes comuns (por
exemplo, a função de conversão `texto(x)`).

### Símbolos

```
+  -  *  /  //  %  ^  ==  !=  <  <=  >  >=  =  +=  -=  *=  /=
(  )  [  ]  {  }  ,  :  .  ;
```

### Fim de instrução

As quebras de linha são significativas: uma instrução termina no fim da linha, em `;`,
no fim do arquivo ou imediatamente antes de `fim`, `senão` ou `capture`.
Quebras de linha são ignoradas:

* dentro de `( )`, `[ ]` e `{ }` (exceto no corpo de uma função anônima, que volta a usar linhas);
* logo depois de um operador binário (`+`, `e`, `==`, ...), permitindo continuar a expressão na linha seguinte.

A indentação **não** tem significado: blocos são delimitados por palavras (`fim`).

## 2. Sintaxe

```ebnf
programa       = { fim-de-linha } , [ 'programa' , texto , fim-instr ] , bloco ;
                 (* 'importe' e 'registro' só podem aparecer no bloco principal do arquivo *)

bloco          = { fim-de-linha } , { instrução , fim-instr , { fim-de-linha } } ;
fim-instr      = fim-de-linha | ';' | ? antes de 'fim', 'senão', 'capture' ou do fim do arquivo ? ;
fim-de-linha   = NL | ';' ;

instrução      = importação | definição-de-registro
               | declaração | definição-de-função | condicional | laço-enquanto
               | laço-repita | laço-para | laço-para-cada | tentativa
               | mostre | retorne | 'pare' | 'continue' | lance
               | atribuição | chamada ;

importação     = 'importe' , texto , 'como' , nome
               | 'importe' , nome , { ',' , nome } , 'de' , texto ;

definição-de-registro
               = 'registro' , nome , parâmetros                                   (* forma curta *)
               | 'registro' , nome , fim-de-linha ,
                 { ( parâmetro | definição-de-função ) , fim-instr } , 'fim' ;    (* campos e métodos *)

declaração     = ( 'defina' | 'constante' ) , nome , [ 'do' , 'tipo' , tipo ] , 'como' , expressão ;

definição-de-função
               = 'função' , nome , parâmetros , [ 'retorna' , tipo ] , bloco , 'fim' ;
parâmetros     = '(' , [ parâmetro , { ',' , parâmetro } ] , ')' ;
parâmetro      = nome , [ 'como' , tipo ] , [ '=' , expressão ] ;   (* com padrão: só depois dos sem padrão *)
tipo           = nome-de-tipo , { 'ou' , nome-de-tipo } ;
nome-de-tipo   = 'inteiro' | 'decimal' | 'número' | 'texto' | 'booleano' | 'lista'
               | 'mapa' | 'função' | 'nulo' | 'qualquer' | nome-de-registro ;

condicional    = 'se' , expressão , 'então' , bloco ,
                 { 'senão' , 'se' , expressão , 'então' , bloco } ,     (* 'senão se' na mesma linha *)
                 [ 'senão' , bloco ] , 'fim' ;

laço-enquanto  = 'enquanto' , expressão , 'faça' , bloco , 'fim' ;
laço-repita    = 'repita' , expressão , 'vezes' , bloco , 'fim' ;
laço-para      = 'para' , nome , 'de' , expressão , 'até' , expressão ,
                 [ 'passo' , expressão ] , 'faça' , bloco , 'fim' ;
laço-para-cada = 'para' , 'cada' , nome , [ ',' , nome ] , 'em' , expressão , 'faça' , bloco , 'fim' ;

tentativa      = 'tente' , bloco , 'capture' , [ nome ] , bloco , 'fim' ;

mostre         = 'mostre' , [ expressão , { ',' , expressão } ] ;
retorne        = 'retorne' , [ expressão ] ;
lance          = 'lance' , expressão ;

atribuição     = alvo , ( '=' | '+=' | '-=' | '*=' | '/=' ) , expressão ;
alvo           = nome | pós-fixa , '[' , expressão , ']' | pós-fixa , '.' , nome ;
chamada        = pós-fixa , '(' , [ argumentos ] , ')' ;          (* única expressão aceita como instrução *)
```

### Expressões (da menor para a maior precedência)

```ebnf
expressão      = ou ;
ou             = e , { 'ou' , e } ;
e              = negação , { 'e' , negação } ;
negação        = 'não' , negação | comparação ;
comparação     = soma , { operador-comp , soma } ;              (* encadeável: 0 <= x < 10 *)
operador-comp  = '==' | '!=' | '<' | '<=' | '>' | '>=' | 'em' ;
soma           = produto , { ( '+' | '-' ) , produto } ;
produto        = unário , { ( '*' | '/' | '//' | '%' ) , unário } ;
unário         = ( '-' | '+' ) , unário | potência ;
potência       = pós-fixa , [ '^' , unário ] ;                  (* associativa à direita *)
pós-fixa       = primária , { '(' , [ argumentos ] , ')' | '[' , expressão , ']' | '.' , nome } ;
argumentos     = expressão , { ',' , expressão } , { ',' , argumento-nomeado }
               | argumento-nomeado , { ',' , argumento-nomeado } ;
argumento-nomeado = nome , ':' , expressão ;
primária       = inteiro | decimal | texto | 'verdadeiro' | 'falso' | 'nulo' | nome | 'eu'
               | '(' , expressão , ')' | lista | mapa | função-anônima | se-expressão ;
se-expressão   = 'se' , expressão , 'então' , expressão , 'senão' , expressão ;
lista          = '[' , [ expressão , { ',' , expressão } , [ ',' ] ] , ']' ;
mapa           = '{' , [ par , { ',' , par } , [ ',' ] ] , '}' ;
par            = expressão , ':' , expressão ;
função-anônima = 'função' , parâmetros , [ 'retorna' , tipo ] , bloco , 'fim' ;
```

Tabela de precedência resultante:

| Nível | Operadores | Associatividade |
|------:|-----------|-----------------|
| 1 (menor) | `ou` | esquerda |
| 2 | `e` | esquerda |
| 3 | `não` | prefixo |
| 4 | `==` `!=` `<` `<=` `>` `>=` `em` | encadeamento (`a < b < c` = `a < b e b < c`, com `b` avaliado uma vez) |
| 5 | `+` `-` | esquerda |
| 6 | `*` `/` `//` `%` | esquerda |
| 7 | `-` `+` unários | prefixo |
| 8 | `^` | direita (`2^3^2` = `2^9`; `-2^2` = `-4`) |
| 9 (maior) | chamada `f()`, índice `x[i]`, campo `x.c` | esquerda |

## 3. Desambiguações

* `senão se` na **mesma linha** sempre inicia uma alternativa do mesmo `se`. Para abrir um
  `se` aninhado dentro do `senão`, coloque o `se` na linha seguinte.
* Depois de `para`, a palavra `cada` seguida de um nome sempre inicia um `para cada`.
* Em `capture nome`, um nome logo depois de `capture` (na mesma linha) é a variável do erro.
* Só chamadas de função podem ser usadas sozinhas como instrução; `x + 1` sozinho é erro G107
  (no REPL, expressões soltas são aceitas e mostram seu valor).
* `{` em posição de expressão sempre inicia um mapa (não existem blocos com chaves).
* `se` no início de uma instrução é o comando condicional (com blocos e `fim`); em qualquer outra
  posição é a expressão `se c então a senão b`, cujo `senão` consome o resto da expressão
  (use parênteses para combiná-la com outros operadores).
* Em uma chamada, `nome:` seguido de expressão é um argumento nomeado; argumentos posicionais vêm antes.
