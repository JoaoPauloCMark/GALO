# GALO 🐓

**GALO** é uma linguagem de programação de propósito geral, Turing-completa, com sintaxe em
português brasileiro. Ela tem gramática formal, compilador para um bytecode próprio (`.galoc`),
duas máquinas virtuais com a mesma semântica — uma em Python (servidor/terminal) e uma em
JavaScript (navegador) —, REPL, servidor de linguagem (LSP) e extensão para o VS Code.

Com a biblioteca padrão dá para construir **sistemas full stack inteiros em GALO**: servidor web com
rotas e JSON, banco de dados SQL, páginas HTML geradas no servidor e interfaces interativas que rodam
no navegador. Veja o [guia full stack](docs/full-stack.md) e o exemplo [`examples/tarefas`](examples/tarefas).

O **site da linguagem** é a prova: [`site/`](site/) é escrito inteiramente em GALO — apresentação,
exemplos executáveis, calculadora, painel ao vivo com gráficos e um “Experimente” em que o servidor
compila e o navegador executa o programa de quem visita (`galo executar site/servidor.galo` e abra
http://localhost:8080).

```galo
programa "Meu Primeiro GALO"

defina nome como "João"
defina idade como 22

mostre "Olá, {nome}!"

se idade >= 18 então
    mostre "Você é maior de idade."
senão
    mostre "Você é menor de idade."
fim

função fatorial(n como inteiro) retorna inteiro
    se n <= 1 então
        retorne 1
    fim
    retorne n * fatorial(n - 1)
fim

mostre fatorial(30)       # 265252859812191058636308480000000 (inteiros não têm limite)
```

## Full stack em 30 segundos

```galo
# servidor.galo
defina banco como abrir_banco("dados.db")
banco.executar("CREATE TABLE IF NOT EXISTS recados (id INTEGER PRIMARY KEY, texto TEXT NOT NULL)")

defina app como criar_servidor()
app.get("/api/recados", função(pedido)
    retorne banco.consultar("SELECT * FROM recados ORDER BY id DESC")
fim)
app.post("/api/recados", função(pedido)
    defina id como banco.inserir("INSERT INTO recados (texto) VALUES (?)", [pedido.json.texto])
    retorne resposta_json({"id": id, "texto": pedido.json.texto}, 201)
fim)
app.cliente("/app.galoc", "cliente.galo")   # este arquivo roda no navegador
app.arquivos("/", "publico")                # publico/index.html carrega /_galo/galo.js e /app.galoc
app.iniciar(8000)
```

```galo
# cliente.galo (no navegador)
buscar("/api/recados", nulo, função(resposta)
    para cada recado em resposta.json faça
        elemento("#lista").adicionar(criar_elemento("li", recado.texto))
    fim
fim)
```

## Instalação

A GALO precisa apenas do **Python 3.10 ou mais recente** (testada com 3.13) e não tem dependências.

**Linux/macOS, sem pip** (instala em `~/.local/bin/galo`):

```bash
./instalar.sh               # instala
./instalar.sh --desinstalar # remove
PREFIXO=/opt/galo ./instalar.sh   # outro destino
```

**Com pip ou pipx** (qualquer sistema, inclusive Windows):

```bash
pipx install .      # ou: pip install .
```

**Arquivo único:** `./instalar.sh --pyz` gera `dist/galo.pyz`, executável diretamente
(`./dist/galo.pyz executar programa.galo`).

**Sem instalar:** `python3 -m galo ...` na pasta do projeto.

**Extensão do VS Code:** `./instalar.sh --vscode` (ou `python3 vscode-extension/empacotar.py` e depois
*Extensões → … → Instalar a partir do VSIX*). Veja [vscode-extension/README.md](vscode-extension/README.md).

## Uso

```bash
galo executar programa.galo [argumentos...]   # compila e executa (atalho: galo programa.galo)
galo compilar programa.galo [-o saida.galoc]  # gera bytecode
galo rodar programa.galoc [argumentos...]     # executa o bytecode, sem precisar do .galo
galo verificar programa.galo [--json]         # procura erros sem executar
galo repl                                     # modo interativo
galo desmontar programa.galo                  # mostra o bytecode gerado
galo --versao
galo ajuda
```

Códigos de saída: `0` sucesso, `1` erro de compilação, `2` erro de execução, `3` erro de arquivo
ou bytecode, `64` uso incorreto, `130` interrompido (ou o valor passado a `sair(n)`).

## A linguagem em uma página

```galo
# Comentário de linha          #[ comentário de bloco ]#
defina x como 10               # variável
constante LIMITE como 100      # constante
defina idade do tipo inteiro como 20   # tipo opcional, verificado
x = x + 1                      # atribuição (x += 1 também vale)

mostre "x vale {x} e o dobro é {x * 2}"     # interpolação
defina nome como leia("Seu nome: ")         # entrada

se x > 5 e não (x == 7) então
    mostre "grande"
senão se x > 0 então
    mostre "pequeno"
senão
    mostre "não positivo"
fim

enquanto x > 0 faça x -= 3 fim
repita 3 vezes mostre "oi" fim
para i de 1 até 10 passo 2 faça mostre i fim
para cada item em [1, 2, 3] faça mostre item fim
para cada chave, valor em {"a": 1} faça mostre chave, valor fim

função somar(a como número, b como número) retorna número
    retorne a + b
fim
defina dobro como função(n) retorne n * 2 fim     # funções são valores
mostre mapear([1, 2, 3], dobro)                   # [2, 4, 6]

função saudar(nome, saudação = "Olá")            # valores padrão
    retorne "{saudação}, {nome}!"
fim
mostre saudar("Ana"), saudar(saudação: "Oi", nome: "Bia")   # argumentos nomeados
mostre se x > 5 então "grande" senão "pequeno"   # se como expressão

registro Ponto(x como número, y como número = 0) # tipos do usuário (com métodos na forma longa)
defina p como Ponto(3, 4)
mostre p.x, p                                     # 3 Ponto(x: 3, y: 4)

defina pessoa como {"nome": "Ana", "idade": 30}
pessoa.cidade = "Recife"                          # mapa.campo = mapa["campo"]
defina jogadores como ["Hulk", "Arana"]
mostre jogadores[1], jogadores[-1]                # posições começam em 1

tente
    mostre 10 / 0
capture erro
    mostre "Falhou: {erro.mensagem} ({erro.código})"
fim
lance "algo deu errado"                           # lança um erro
```

Acentos são opcionais em todos os nomes e palavras-chave (`entao`, `funcao`, `pontuacao`).
Textos com aspas duplas fazem interpolação (`"Oi, {nome}"`); com aspas simples são literais
(`'^\d{5}$'`, `'{{ modelo }}'`); com aspas triplas ocupam várias linhas. Programas maiores se
dividem em arquivos com `importe "modelos.galo" como modelos` ou `importe Tarefa de "modelos"`.

## Erros claros

```text
Erro GALO [G201] — erro semântico
Arquivo: exemplo.galo
Linha: 8, coluna: 8

  8 | mostre pontuacao
    |        ^^^^^^^^^

A variável "pontuacao" não foi definida.

Sugestão:
Declare a variável antes de utilizá-la:
defina pontuacao como 0
```

Os erros são classificados em léxicos (G0xx), sintáticos (G1xx), semânticos (G2xx), de execução
(G3xx), lançados pelo programa (G4xx) e de arquivo/bytecode (G5xx). Catálogo: [docs/erros.md](docs/erros.md).

## Exemplos

[site/](site/) é o site oficial da GALO, escrito em GALO: servidor, banco de dados, páginas, realce de
sintaxe, calculadora, gráficos SVG, simulação ao vivo e o “Experimente” (compilar no servidor com
`compilar_programa`, executar isolado no navegador com `executar_programa`). Veja [site/README.md](site/README.md).

[examples/tarefas/](examples/tarefas/) é um aplicativo full stack completo (gerenciador de tarefas):
módulos, registros, repositório SQLite, API REST, página renderizada no servidor com modelo HTML,
interface interativa no navegador e testes escritos em GALO
(`galo executar examples/tarefas/servidor.galo` e abra http://localhost:8000).

Também em [examples/](examples/): `ola_mundo`, `calculadora` (interativa), `fibonacci`, `fatorial`,
`listas`, `mapas`, `closures`, `erros`, `primos`, `ordenacao` (quicksort e merge sort), `hanoi`,
`jogo_adivinhacao`, `arquivos_e_datas` e as demonstrações de universalidade
`maquina_turing` (simulador genérico de máquinas de Turing) e `brainfuck` (interpretador completo).

## Documentação

| Documento | Conteúdo |
|-----------|----------|
| [docs/full-stack.md](docs/full-stack.md) | Guia de desenvolvimento full stack: módulos, registros, banco, servidor, navegador, segurança, testes |
| [docs/grammar.md](docs/grammar.md) | Gramática formal em EBNF, léxico e precedência |
| [docs/language-spec.md](docs/language-spec.md) | Semântica: tipos, coerções, escopos, funções, erros |
| [docs/turing.md](docs/turing.md) | Por que a GALO é Turing-completa; teoria × limites práticos |
| [docs/architecture.md](docs/architecture.md) | Compilador, bytecode (instruções e formato `.galoc`), VM, trade-offs |
| [docs/biblioteca-padrao.md](docs/biblioteca-padrao.md) | As 125 funções internas (e onde cada uma existe) |
| [docs/erros.md](docs/erros.md) | Catálogo de erros e avisos |

## Estrutura

```text
galo/
  compiler/   lexer.py  parser.py  ast.py  semantic.py  typesys.py  codegen.py  bytecode.py
  runtime/    vm.py  values.py  builtins.py
  stdlib/     texto, matemática, coleções, conversão, JSON, arquivos, tempo, sistema, segurança,
              banco (SQLite), web (servidor/cliente HTTP), modelos HTML, página (navegador)
  cli/        main.py (comando galo)  repl.py
  lsp/        server.py (Language Server Protocol)
  web/        galo.js (máquina virtual para o navegador)
  errors.py   session.py   names.py
vscode-extension/   gramática, snippets, autoindentação, cliente LSP, comandos e tarefas
examples/   programas de exemplo
site/       o site da linguagem, escrito em GALO (servidor, páginas, interface, testes)
tests/      testes automatizados (unittest) e saídas esperadas
docs/       documentação
```

## Testes

```bash
python3 -m unittest discover -s tests
```

A suíte cobre tokenização, parsing e precedência, escopos, aritmética, condicionais, laços, funções
e recursão, closures, listas e mapas, registros, módulos, valores padrão e argumentos nomeados,
tratamento de erros (inclusive código inválido e casos extremos), biblioteca padrão, JSON, banco de
dados, modelos HTML, servidor web (sem rede e com servidor real), compilação/leitura/verificação de
bytecode, execução de `.galoc` sem o fonte, REPL, CLI, LSP, programas completos comparados com saídas
esperadas e os testes de universalidade.

Quando as ferramentas estão instaladas, a suíte também testa em programas **reais** (cada teste é
pulado se a ferramenta não existir):

| Ferramenta | O que é verificado |
|------------|--------------------|
| `gjs` | a VM do navegador executa os mesmos programas que a VM Python, com saídas idênticas; API de página com DOM simulado |
| Google Chrome / Chromium | exemplos e programas de conformidade (inclusive matemática) no navegador; o aplicativo de tarefas usado com teclado, mouse e diálogos de confirmação reais (modo headless, perfil temporário) |
| Microsoft Edge | o mesmo que no Chrome; detectado no `PATH` ou pela variável `GALO_EDGE` (`tests/navegador_real/baixar_edge.py` baixa e confere o pacote oficial numa pasta, sem instalar) |
| Firefox | os mesmos programas de conformidade (modo headless, perfil temporário) |
| WebKitGTK (motor do Safari: WebKit + JavaScriptCore) | conformidade e o aplicativo de tarefas com cliques e teclas nativos, numa janela fora da tela (precisa de `gcc` e dos cabeçalhos do WebKitGTK 4.1) |
| `pip` (baixado do PyPI se faltar) | `pip install .` num ambiente virtual novo, wheel, instalação editável e desinstalação; também `instalar.sh` e `galo.pyz` (pastas temporárias; `GALO_SEM_REDE=1` pula a parte que usa a rede) |
| VS Code ou Cursor | a extensão dentro do editor: ativação, diagnósticos do LSP, autocompletar, snippets, *hover*, autoindentação, realce de sintaxe, comandos, tarefas com o painel Problemas e instalação do `.vsix` (perfil temporário; uma janela do editor abre durante o teste) |

Há ainda testes de robustez com sementes fixas: milhares de programas mutilados e sequências
aleatórias (o compilador nunca pode falhar com erro interno), bytecode corrompido, operadores entre
todos os pares de tipos, 1.800 expressões aritméticas e 2.400 chamadas de funções matemáticas
aleatórias comparadas entre as duas VMs. As funções matemáticas (`seno`, `logaritmo`, potências
fracionárias...) são corretamente arredondadas pela própria GALO e conferidas contra uma referência
de 60 dígitos: dão os mesmos bits no Python, no Chrome, no Edge, no Firefox e no WebKit.

## Limitações desta versão (0.2)

* Não há tipos genéricos (`lista de Tarefa`), herança entre registros nem `async/await` (o navegador
  usa funções de retorno em `buscar`).
* O servidor web executa um pedido GALO por vez por processo (≈1.200–1.400 pedidos/s medidos em rotas
  simples); não há HTTPS, WebSockets nem *upload* multipart embutidos; o banco é SQLite.
* O parser reporta o primeiro erro de sintaxe de cada arquivo (os erros semânticos são todos listados).
* A VM em Python faz ~3 milhões de instruções/s; a do navegador foi ~5× mais rápida no mesmo teste.

## Licença

MIT — veja [LICENSE](LICENSE).
