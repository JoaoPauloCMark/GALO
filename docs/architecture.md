# Arquitetura da implementação

A GALO 0.2 é implementada em Python 3 (testada com 3.13; o código evita recursos posteriores ao
3.10), **sem dependências externas**. A linguagem não é traduzida para Python: ela tem gramática,
AST, análise semântica, conjunto de instruções e máquina virtual próprios. Não há uso de `eval`,
`exec` ou substituição textual.

```
 código-fonte (.galo)
        │  galo/compiler/lexer.py        tokens (com posição; interpolações já tokenizadas)
        ▼
     tokens
        │  galo/compiler/parser.py       descida recursiva, uma função por regra da gramática
        ▼
       AST  (galo/compiler/ast.py)
        │  galo/compiler/semantic.py     escopos, nomes, capturas, constantes, tipos, aridade
        ▼
  AST anotada
        │  galo/compiler/codegen.py      instruções de pilha + tabela de posições
        ▼
 Module / CodeObject  ── galo/compiler/bytecode.py ──►  arquivo .galoc (binário, com CRC32)
        │                                               ◄── leitura + verificação
        ▼
 galo/runtime/vm.py  (máquina virtual)  +  galo/runtime/values.py  +  galo/stdlib/*
```

## Módulos

| Caminho | Responsabilidade |
|---------|------------------|
| `galo/errors.py` | Hierarquia de diagnósticos (léxico, sintático, semântico, execução, bytecode, aviso) e formatação no padrão oficial |
| `galo/compiler/tokens.py` | Tipos de token, palavras reservadas e contextuais, forma canônica de nomes (sem acentos) |
| `galo/compiler/lexer.py` | Analisador léxico |
| `galo/compiler/ast.py` | Nós da árvore sintática |
| `galo/compiler/parser.py` | Analisador sintático e heurísticas de mensagens de erro |
| `galo/compiler/typesys.py` | Tipos estáticos (conjuntos de tipos básicos) e regras de operadores |
| `galo/compiler/semantic.py` | Análise semântica (anota a AST) |
| `galo/compiler/codegen.py` | Geração de bytecode |
| `galo/compiler/bytecode.py` | Instruções, objetos de código, formato `.galoc`, verificador e desmontador |
| `galo/runtime/values.py` | Representação de valores e semântica de cada operação |
| `galo/runtime/vm.py` | Máquina virtual |
| `galo/runtime/builtins.py` | Espaço de nomes interno da VM (funções e constantes da biblioteca padrão) |
| `galo/names.py` | Forma canônica de nomes (sem acentos), compartilhada pelo compilador e pelo runtime |
| `galo/stdlib/` | Biblioteca padrão (uma área por arquivo) e o registro `@nativa` |
| `galo/session.py` | Sessão persistente (REPL) e API `run_source` |
| `galo/cli/` | Comando `galo` e o REPL |
| `galo/lsp/server.py` | Servidor Language Server Protocol |
| `galo/web/galo.js` | Máquina virtual para o navegador (JavaScript) e API de página |
| `galo/stdlib/web.py`, `banco.py`, `modelos.py`, `dados_json.py`, `seguranca.py` | Servidor/cliente HTTP, SQLite, modelos HTML, JSON, senhas e codificações |
| `vscode-extension/` | Extensão do VS Code (gramática TextMate, snippets, cliente LSP, comandos e tarefas) |

## Frontend

**Lexer.** Varre o texto uma vez, produzindo tokens com linha, coluna, comprimento e um marcador
"primeiro da linha" (usado para detectar `fim` desalinhado). Dentro de um texto, cada `{...}` é
tokenizado recursivamente, de modo que a interpolação é uma expressão de verdade, com posições
corretas nos erros. Palavras reservadas são reconhecidas pela forma canônica (sem acentos).

**Parser.** Descida recursiva com uma função por nível de precedência. As quebras de linha são
tokens; uma pilha `nl_ignore` decide quando são ignoradas (dentro de parênteses/colchetes/chaves,
exceto no corpo de funções anônimas). O parser contém heurísticas para mensagens melhores:
sugestão de palavra-chave parecida (`enqanto` → `enquanto`), `=` no lugar de `==`, vírgulas
faltando, `fim` desalinhado com a abertura do bloco, `retorna` × `retorne` etc. Erros causados pelo
fim prematuro da entrada são marcados como *incompletos* — o REPL usa isso para pedir mais linhas.

**Análise semântica.** Percorre a AST mantendo uma cadeia de escopos (`Scope`) e um contexto por
função (`FuncCtx`). Decisões de projeto:

* *Escopo de bloco com resolução estática.* Cada declaração recebe um *slot* numérico no quadro da
  função; o programa principal é tratado como uma função cujo escopo mais externo é global
  (dicionário por nome, para permitir o REPL) e cujos blocos internos usam slots.
* *Declarações adiantadas.* Ao entrar em um bloco, as funções declaradas nele são registradas antes
  das demais instruções, e os nomes declarados com `defina` mais abaixo ficam em uma lista "ainda
  não definidos" — usá-los antes gera G202 em vez de resolver silenciosamente para um nome externo.
* *Corpos de função analisados no fim do bloco.* Assim, uma função pode usar variáveis declaradas
  depois dela no mesmo bloco (recursão mútua, closures que se referem a valores definidos depois).
* *Closures por células.* Quando uma função interna usa uma variável de uma função externa, o
  símbolo é marcado como *capturado*; o gerador passa a guardá-lo em uma `Cell`, criada **na entrada
  do bloco** onde a variável é declarada (por isso cada volta de um laço tem sua própria variável).
  Capturas em vários níveis são encadeadas pelas funções intermediárias.
* *Inferência conservadora.* Tipos estáticos são conjuntos de tipos possíveis, ou "desconhecido".
  Um erro só é emitido quando **nenhuma** combinação possível é válida; caso contrário, a verificação
  fica para a VM. Isso mantém a linguagem dinâmica sem falsos positivos.

Todos os erros semânticos de um arquivo são coletados e informados juntos, ordenados por posição.

## Bytecode

A VM é uma máquina de pilha. Cada instrução ocupa duas posições de uma lista de inteiros
(`código, argumento`), e cada instrução tem (linha, coluna) na tabela `positions` — é isso que permite
mensagens de erro de execução com a posição exata mesmo sem o código-fonte.

Um `CodeObject` contém: nome, arquivo, parâmetros e seus tipos, tipo de retorno, número de slots
locais (e seus nomes, para mensagens), origem de cada variável capturada, tabela de nomes, constantes
(inclusive outros `CodeObject`s — funções aninhadas) e as instruções.

### Conjunto de instruções

| Código | Instrução | Argumento | Efeito |
|------:|-----------|-----------|--------|
| 0 | `NOP` | — | não faz nada |
| 1 | `CONST` | índice de constante | empilha consts[arg] |
| 2 | `POP` | — | descarta o topo da pilha |
| 3 | `DUP` | — | duplica o topo |
| 4 | `LOAD_LOCAL` | variável local | empilha locals[arg] |
| 5 | `STORE_LOCAL` | variável local | locals[arg] = desempilha |
| 6 | `LOAD_CELL` | variável local | empilha locals[arg].valor (variável capturada) |
| 7 | `STORE_CELL` | variável local | locals[arg].valor = desempilha |
| 8 | `MAKE_CELL` | variável local | locals[arg] = nova caixa vazia |
| 9 | `BOX_LOCAL` | variável local | locals[arg] = caixa(locals[arg]) (parâmetro capturado) |
| 10 | `LOAD_FREE` | variável capturada | empilha células_capturadas[arg].valor |
| 11 | `STORE_FREE` | variável capturada | células_capturadas[arg].valor = desempilha |
| 12 | `LOAD_GLOBAL` | índice de nome | empilha globais[names[arg]] (ou função interna) |
| 13 | `STORE_GLOBAL` | índice de nome | globais[names[arg]] = desempilha (precisa existir) |
| 14 | `DEFINE_GLOBAL` | índice de nome | globais[names[arg]] = desempilha |
| 15 | `ADD` | — | soma (`+`) |
| 16 | `SUB` | — | subtração |
| 17 | `MUL` | — | multiplicação |
| 18 | `DIV` | — | divisão (`/`, sempre decimal) |
| 19 | `IDIV` | — | divisão inteira (`//`) |
| 20 | `MOD` | — | resto (`%`) |
| 21 | `POW` | — | potência (`^`) |
| 22 | `NEG` | — | troca o sinal |
| 23 | `POS` | — | `+` unário |
| 24 | `NOT` | — | `não` |
| 25 | `EQ` | — | `==` |
| 26 | `NE` | — | `!=` |
| 27 | `LT` | — | `<` |
| 28 | `LE` | — | `<=` |
| 29 | `GT` | — | `>` |
| 30 | `GE` | — | `>=` |
| 31 | `IN` | — | `em` |
| 32 | `JUMP` | destino do desvio | desvia para arg |
| 33 | `JUMP_IF_FALSE` | destino do desvio | desempilha booleano; desvia se falso |
| 34 | `JUMP_IF_FALSE_KEEP` | destino do desvio | operador 'e': se falso, mantém e desvia; senão, descarta |
| 35 | `JUMP_IF_TRUE_KEEP` | destino do desvio | operador 'ou' |
| 36 | `CHECK_BOOL` | opção | topo deve ser booleano (arg: 1 = operando de 'e', 2 = de 'ou') |
| 37 | `BUILD_LIST` | quantidade | cria lista com arg elementos |
| 38 | `BUILD_MAP` | quantidade | cria mapa com arg pares |
| 39 | `BUILD_STRING` | quantidade | concatena arg partes (interpolação) |
| 40 | `INDEX` | — | obj[i] |
| 41 | `STORE_INDEX` | — | obj[i] = v |
| 42 | `GET_FIELD` | índice de nome | obj.names[arg] |
| 43 | `SET_FIELD` | índice de nome | obj.names[arg] = v |
| 44 | `CALL` | quantidade | chama função com arg argumentos |
| 45 | `RETURN` | opção | arg: 1 = retorno implícito (fim da função) |
| 46 | `MAKE_FUNCTION` | constante (código) | cria closure de consts[arg] |
| 47 | `PRINT` | quantidade | mostra arg valores |
| 48 | `PRINT_REPL` | — | mostra o valor de uma expressão digitada no REPL |
| 49 | `ITER_PREPARE` | opção | transforma coleção em iterador (arg: 1 = duas variáveis) |
| 50 | `RANGE_PREPARE` | opção | início, fim[, passo] -> iterador (arg: 1 = com passo) |
| 51 | `REPEAT_PREPARE` | — | quantidade -> iterador |
| 52 | `FOR_ITER` | destino do desvio | próximo valor do iterador, ou desvia para arg ao terminar |
| 53 | `FOR_ITER2` | destino do desvio | idem, empilhando dois valores |
| 54 | `SETUP_TRY` | destino do desvio | registra tratador de erros em arg |
| 55 | `POP_TRY` | — | remove o tratador de erros mais recente |
| 56 | `RAISE` | — | lança o valor do topo como erro |
| 57 | `CHECK_TYPE` | constante (tipo) | verifica o tipo do topo com consts[arg] (TypeCheck) |
| 58 | `IMPORT_MODULE` | índice do módulo | executa (uma vez) o módulo modules[arg] e empilha o valor do módulo |
| 59 | `MAKE_RECORD_TYPE` | constante (registro) | construtor + métodos -> tipo de registro (consts[arg]: RecordInfo) |
| 60 | `NEW_RECORD` | quantidade | tipo, v1..vN -> instância com arg campos |
| 61 | `CALL_KW` | constante (chamada) | chamada com argumentos nomeados (consts[arg]: CallInfo) |
| 62 | `ARG_MISSING` | variável local | empilha verdadeiro se o parâmetro locals[arg] não foi informado |

### Formato `.galoc`

```
"GALOC\0"                  6 bytes (assinatura)
versão do formato           u16 little-endian (atual: 2)
conteúdo:
    versão da GALO, nome do programa, arquivo de origem   (textos)
    objeto de código principal                            (recursivo)
    quantidade de módulos; para cada um: nome, objeto de código, nomes exportados
CRC32 do conteúdo           u32 little-endian
```

Cada parâmetro de um objeto de código registra nome, tipo e se tem valor padrão. Constantes
especiais: `Y` (verificação de tipo), `R` (descrição de registro: nome, campos com tipos, métodos) e
`K` (chamada com argumentos nomeados: quantidade de posicionais e nomes).

Textos são gravados como tamanho (varint LEB128) + UTF-8; inteiros do programa têm tamanho
arbitrário (sinal + magnitude); decimais usam IEEE 754 de 64 bits. O formato **não** usa `pickle`
nem nenhuma serialização do Python: é independente da linguagem de implementação e poderia ser lido
por uma VM escrita em C ou Rust.

Ao carregar, a GALO confere assinatura, versão (G503) e CRC32 (G502) e então executa um
**verificador** que garante, antes de rodar qualquer instrução, que: todo código de operação existe;
todo índice de constante, variável local, variável capturada e nome está dentro dos limites; todo
desvio aponta para o início de uma instrução; capturas referenciam variáveis existentes da função
que cria a closure; e todo código termina com um retorno. Um arquivo adulterado é recusado em vez de
derrubar a VM.

## Módulos, registros e chamadas

* **Módulos.** O `ModuleLoader` (`galo/compiler/__init__.py`) resolve o caminho em relação ao arquivo
  que importa, detecta ciclos (pilha de arquivos em compilação), compila cada módulo uma vez e guarda
  seus símbolos exportados — por isso o analisador consegue verificar nomes, aridade e tipos através
  de módulos. Todos os módulos entram no mesmo `Module`/`.galoc`. Na execução, `IMPORT_MODULE` roda o
  código do módulo na primeira vez (com um dicionário de globais próprio) e devolve um `GaloModulo`.
  Cada quadro e cada closure carrega o dicionário de globais do seu módulo.
* **Registros.** `registro` gera um construtor (uma função cujos parâmetros são os campos, com os
  mesmos mecanismos de tipo e valor padrão das funções; o corpo é `NEW_RECORD`) e uma função por método,
  com o parâmetro implícito `eu`. `MAKE_RECORD_TYPE` junta tudo num `GaloTipoRegistro`. Ler um método
  de uma instância cria um `MetodoLigado`, que ao ser chamado põe a instância como primeiro argumento.
* **Valores padrão e argumentos nomeados.** Parâmetros não informados recebem a marca `UNSET`; o
  prólogo da função testa cada um com `ARG_MISSING` e avalia o valor padrão. `CALL_KW` associa os
  argumentos nomeados aos parâmetros pela forma canônica do nome.

## Máquina virtual

* **Quadros explícitos.** Chamar uma função GALO empilha um `Frame` em uma lista; o laço principal
  apenas troca o quadro corrente. A recursão da GALO não consome a pilha do Python — o limite é
  configurável (`max_frames`, padrão 100 000) e, quando atingido, gera G311 com o rastro de chamadas
  (as primeiras e últimas entradas).
* **Despacho.** Um único laço com `if/elif` ordenado pela frequência das instruções, variáveis locais
  em cache e caminhos rápidos para inteiros em `+`, `-`, `*` e comparações.
* **Valores.** Inteiros, decimais, textos, listas e `nulo` usam os tipos nativos do Python
  correspondentes; mapas usam `GaloMapa`, que normaliza as chaves para que `verdadeiro` e `1` não
  colidam. Toda operação verifica tipos com `type(v) is ...` (nunca `isinstance`), pois em Python
  `True` é um inteiro. Nenhum objeto Python arbitrário fica acessível ao programa: não há acesso a
  atributos, módulos ou funções do Python a partir da GALO.
* **Erros.** Uma exceção `GaloRuntimeError` recebe posição e rastro na primeira vez que passa pelo
  laço; depois a VM procura, do quadro atual para baixo, o tratador mais recente registrado por
  `SETUP_TRY` (com a altura da pilha de operandos salva), descarta os quadros intermediários e salta
  para o `capture`. Exceções do Python que representam falhas do programa (divisão por zero,
  estouro numérico, memória, recursão em estruturas profundas) são convertidas em erros GALO;
  qualquer outra é tratada como **falha interna** e nunca é mascarada como erro do usuário.
* **Funções internas que chamam funções GALO** (`mapear`, `filtrar`, `ordenar_por`...) usam
  `VM.call_value`, que executa um laço aninhado até aquele quadro retornar. Um erro não capturado
  dentro do callback atravessa a função interna e continua sendo tratado normalmente.

## A VM do navegador (`galo/web/galo.js`)

Uma segunda implementação da máquina virtual, em JavaScript puro (sem dependências), executa o
mesmo `.galoc`: lê o formato binário (com CRC32), reproduz o despacho de todas as instruções, a pilha
de quadros, closures, registros, módulos, tratamento de erros e a biblioteca padrão. Para manter a
semântica idêntica: inteiros são `BigInt` (precisão arbitrária); decimais são `number` exibidos com o
mesmo algoritmo do Python (`1e+16`, `0.30000000000000004`, `-0.0`); textos são indexados por
caracteres Unicode (não por unidades UTF-16); mapas normalizam chaves como na VM Python; o JSON tem
um analisador próprio que distingue `1` (inteiro) de `1.0` (decimal); divisões de inteiros e
potências com expoente inteiro usam aritmética racional exata (`BigInt`) com um único arredondamento,
e `//`/`%` entre decimais reproduzem o algoritmo do CPython — assim os resultados não dependem da
biblioteca matemática de cada navegador.

**Funções matemáticas** (`galo/runtime/matematica_exata.py` e a cópia fiel em `galo.js`): seno,
cosseno, tangente, logaritmo e potência fracionária são calculados em ponto fixo binário com
inteiros de precisão arbitrária. Cada cálculo devolve um intervalo que contém o valor exato (π por
Machin, ln 2 por atanh, séries de Taylor com limite de erro somado termo a termo); se as duas pontas
arredondam para o mesmo decimal, ele é a resposta; senão o cálculo é refeito com o dobro de bits
(estratégia de Ziv, de 96 até 6.144 bits). A redução de ângulo usa π com tantos bits quanto o
tamanho do argumento, então `seno(1e300)` também é exato. Casos em que o resultado é exatamente
representável (`logaritmo(8, 2)`, `16 ^ 0.25`) são reconhecidos por verificação com racionais. Toda
divisão usa operandos não negativos, porque o `BigInt` trunca e o Python arredonda para baixo — com
isso as duas VMs seguem os mesmos passos e chegam aos mesmos bits. Custo típico: 7–20 µs por chamada
na VM Python. O gerador de números aleatórios (xoshiro128\*\* com splitmix32) também é o mesmo nas
duas VMs.

Verificação: os mesmos programas rodam nas duas VMs (no `gjs`, no Chrome e no Firefox) e as saídas
precisam ser idênticas; as tabelas de instruções são comparadas; toda função interna existe nas duas
VMs ou é marcada como exclusiva do servidor; expressões aritméticas aleatórias são comparadas entre as
VMs (testes diferenciais); a API de página é testada com um DOM simulado e, no Chrome, no Edge e no
WebKit, com eventos de teclado e mouse reais (protocolo DevTools para Chrome e Edge, cliente em
`tests/navegador_real/cdp.py`; eventos GDK nativos para o WebKitGTK, em
`tests/navegador_real/webkit_driver.c`).

## Testes em programas reais

| Arquivo | Verifica |
|---------|----------|
| `tests/test_navegador.py` | VM JavaScript no `gjs`: conformidade, DOM simulado, frontend do exemplo |
| `tests/test_navegador_real.py` | Chrome, Edge, Firefox e WebKitGTK (motor do Safari), sem janela na tela: conformidade (inclusive matemática), caixa de erro na página, fluxo completo do aplicativo de tarefas com teclado, mouse e diálogos reais |
| `tests/test_matematica.py` | arredondamento correto de seno, cosseno, tangente, logaritmo e potência contra uma referência independente (módulo `decimal`, 60+ dígitos); casos exatos; gerador aleatório (vetor conhecido do xoshiro128\*\*) |
| `tests/test_site.py` | o site em `site/` (escrito em GALO): testes em GALO, `compilar_programa`/`executar_programa` e o fluxo completo com mouse e teclado reais no Chrome, no Edge e no WebKit |
| `tests/test_instalacao.py` | `pip install` num ambiente virtual novo, wheel, instalação editável, `instalar.sh` e `galo.pyz` (em pastas temporárias) |
| `tests/test_editor_real.py` + `tests/editor/teste_extensao.js` | a extensão num VS Code/Cursor real (host de extensões isolado) |
| `tests/test_robustez.py` | *fuzzing* do compilador e do leitor de bytecode; testes diferenciais entre as VMs (aritmética e funções matemáticas) |

## Servidor web

`criar_servidor()` usa `ThreadingHTTPServer` da biblioteca padrão do Python: cada conexão tem sua
*thread*, mas o despacho para o código GALO acontece sob uma trava — a VM nunca é usada por duas
*threads* ao mesmo tempo, e a *thread* principal fica bloqueada em `iniciar()` enquanto isso. As
rotas são expressões regulares geradas dos padrões (`<id:inteiro>`). Arquivos estáticos passam por
`realpath` e são recusados se saírem da pasta. `app.testar` chama o mesmo despacho sem rede.
`app.cliente` compila o programa do navegador sob demanda e o recompila quando o arquivo (ou um de
seus módulos) muda. O banco de dados usa `sqlite3` em modo *autocommit*, com transações explícitas
em `transação()`.

## Biblioteca padrão

Cada função interna é uma função Python decorada com `@nativa("nome", retorna="tipo")`. O decorador
calcula a aridade a partir da assinatura, registra o nome canônico (por isso `maiúsculas` e
`maiusculas` funcionam) e guarda a documentação e o tipo de retorno — usados pelo analisador
semântico (verificação de aridade e inferência), pelo LSP (autocompletar e hover), pela gramática do
VS Code (gerada por `vscode-extension/gerar_gramatica.py`) e pela referência em
[biblioteca-padrao.md](biblioteca-padrao.md) (gerada por `docs/gerar_referencia.py`).

## Ferramentas

* **CLI** (`galo/cli/main.py`): `executar`, `compilar`, `rodar`, `verificar` (com `--json` e
  `--formato-curto`), `desmontar`, `tokens`, `ast`, `repl`, `lsp`, `--versao`, `ajuda`. Códigos de
  saída: 0 sucesso, 1 erro de compilação, 2 erro de execução, 3 arquivo/bytecode, 64 uso, 130 interrupção.
* **REPL** (`galo/cli/repl.py` + `galo/session.py`): cada entrada é compilada com a tabela de símbolos
  globais acumulada e executada na mesma VM; histórico em `~/.galo_historico`.
* **LSP** (`galo/lsp/server.py`): JSON-RPC sobre stdio, com sincronização completa de documentos,
  diagnósticos (convertendo colunas para UTF-16, como o protocolo exige), autocompletar e hover.
* **Instalação**: `pyproject.toml` (pip/pipx criam o executável `galo`), `instalar.sh` (sem pip: copia
  o pacote, pré-compila e cria um lançador em `~/.local/bin`) e `instalar.sh --pyz` (arquivo único).

## Principais trade-offs

| Decisão | Alternativa | Motivo |
|---------|-------------|--------|
| Posições a partir de 1 | a partir de 0 | corresponde à linguagem natural ("primeiro elemento") e combina com `para i de 1 até tamanho(lista)` |
| Sem verdade implícita (`se lista então` é erro) | conversão para booleano | elimina uma classe de bugs e torna as condições explícitas |
| `texto + número` é erro | conversão automática | evita ambiguidades (`"1" + 1` é `"11"` ou `2`?); a interpolação resolve o caso comum |
| Nomes sem distinção de acentos | nomes exatos | teclados sem acentos e erros de digitação não viram "variável não definida" |
| Escopo de bloco + proibição de ocultar nomes na mesma função | escopo de função (como Python) | erros de escopo aparecem na compilação, não como valores errados |
| `/` sempre decimal, `//` divisão inteira | `/` inteiro entre inteiros | `7 / 2 = 3.5` é o que se espera na matemática |
| Decimais IEEE 754 | decimal exato | desempenho e funções matemáticas; `formatar` e `arredondar` usam arredondamento comercial |
| VM em Python | VM em C | portabilidade e clareza na primeira versão; o formato `.galoc` permite outra VM no futuro |
| Despacho com `if/elif` | tabela de funções | em CPython, chamadas de função por instrução custam mais que algumas comparações |

## Limitações conhecidas desta versão

* Não há tipos genéricos (`lista de Tarefa`) nem herança entre registros.
* O parser informa o **primeiro** erro sintático (não há recuperação para listar vários); erros
  semânticos, por outro lado, são todos listados.
* Variáveis sem anotação não carregam tipo estático; a verificação de campos de registros em
  compilação vale para constantes, parâmetros/variáveis anotados e `eu`.
* O servidor web executa um pedido GALO por vez por processo; não há HTTPS, WebSockets nem *upload*
  multipart embutidos. O único banco de dados é o SQLite.
* Desempenho típico de um interpretador em Python (~3 milhões de instruções por segundo). A VM em
  JavaScript foi cerca de 5 vezes mais rápida num teste com recursão e laços (gjs/SpiderMonkey),
  mesmo usando `BigInt` para todos os inteiros.
