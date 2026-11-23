# Desenvolvimento full stack com GALO

Com GALO você escreve **o servidor, o banco de dados, as páginas e a interface que roda no
navegador** na mesma linguagem. O mesmo compilador gera bytecode (`.galoc`) que é executado por
duas máquinas virtuais com a mesma semântica:

```
 Navegador                                        Servidor (galo executar servidor.galo)
 ┌──────────────────────────────┐   HTTP/JSON    ┌───────────────────────────────────────┐
 │ galo.js  (VM em JavaScript)  │ ◄────────────► │ VM em Python                          │
 │ cliente.galo → /app.galoc    │                │ criar_servidor(): rotas, arquivos,     │
 │ elemento(), buscar(), ...    │                │ modelos HTML, abrir_banco() (SQLite)  │
 └──────────────────────────────┘                └───────────────────────────────────────┘
```

O exemplo completo está em [`examples/tarefas/`](../examples/tarefas):

```bash
galo executar examples/tarefas/testes.galo     # testes da API, sem rede
galo executar examples/tarefas/servidor.galo   # abra http://localhost:8000
```

| Arquivo | Papel |
|---------|-------|
| `modelos.galo` | `registro Tarefa` e `registro RepositorioDeTarefas` (todo o SQL fica aqui) |
| `api.galo` | rotas: página inicial renderizada no servidor + API JSON |
| `servidor.galo` | ponto de entrada: lê a configuração e inicia o servidor |
| `cliente.galo` | interface interativa que roda no navegador |
| `paginas/inicio.html` | modelo HTML da página inicial |
| `publico/estilo.css` | arquivos estáticos |
| `testes.galo` | testes automatizados da API, escritos em GALO |

## 1. Organizando o código em módulos

```galo
importe "modelos.galo" como modelos           # tudo, com prefixo: modelos.Tarefa
importe Tarefa, abrir_repositorio de "modelos" # nomes escolhidos, sem prefixo (".galo" é opcional)
```

* Caminhos são relativos à pasta do arquivo que importa.
* Cada módulo é executado **uma vez**; quem o importa de novo recebe o mesmo módulo (o estado é compartilhado).
* Tudo o que é definido no nível principal é exportado, exceto nomes que começam com `_`.
* O compilador confere os nomes importados, a quantidade de argumentos e os tipos entre módulos.
* `galo compilar` inclui todos os módulos no `.galoc`, que roda sem os arquivos-fonte.

## 2. Modelando dados com registros

```galo
registro Tarefa
    id como inteiro
    título como texto
    feita como booleano = falso
    criada_em como texto = data_hora_iso()    # valor padrão avaliado a cada criação

    função concluir()
        eu.feita = verdadeiro
    fim
fim

defina t como Tarefa(1, "Comprar pão")
defina outra como Tarefa(id: 2, título: "Estudar", feita: verdadeiro)   # argumentos nomeados
t.concluir()
mostre t.feita, tipo(t), para_json(t)
```

Campos com tipo são verificados ao criar e ao alterar (`t.feita = "sim"` é erro G315). Para um
registro curto, use a forma de uma linha: `registro Ponto(x como número, y como número = 0)`.

## 3. Banco de dados

```galo
defina banco como abrir_banco("dados.db")      # ou ":memória:" (temporário, ótimo para testes)
banco.executar('''
    CREATE TABLE IF NOT EXISTS clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        email TEXT UNIQUE
    )
''')
defina id como banco.inserir("INSERT INTO clientes (nome, email) VALUES (?, ?)", ["Ana", "ana@x.com"])
defina todos como banco.consultar("SELECT * FROM clientes ORDER BY nome")      # lista de mapas
defina um como banco.consultar_um("SELECT * FROM clientes WHERE id = :id", {"id": id})   # mapa ou nulo
banco.transação(função()
    banco.executar("UPDATE clientes SET nome = ? WHERE id = ?", ["Ana Maria", id])
fim)
```

| Método | Devolve |
|--------|---------|
| `executar(sql, [parâmetros])` | quantidade de linhas afetadas |
| `executar_script(sql)` | nulo (vários comandos separados por `;`, sem parâmetros) |
| `inserir(sql, [parâmetros])` | id da linha criada |
| `consultar(sql, [parâmetros])` | lista de mapas (coluna → valor) |
| `consultar_um(sql, [parâmetros])` | primeiro mapa ou nulo |
| `transação(função)` | o resultado da função; se ela lançar erro, tudo é desfeito |
| `fechar()` | nulo |

**Sempre passe valores como parâmetros** (`?` com uma lista, ou `:nome` com um mapa), nunca
montando o SQL com interpolação: isso impede injeção de SQL. Booleanos são gravados como 1/0;
listas e mapas podem ser guardados como texto com `para_json`. Erros do SQLite são traduzidos
(G324): *"a tabela 'x' não existe"*, *"já existe um registro com o mesmo valor em clientes.email"*.

## 4. O servidor web

```galo
defina app como criar_servidor()

app.get("/api/clientes/<id:inteiro>", função(pedido)
    defina c como banco.consultar_um("SELECT * FROM clientes WHERE id = ?", [pedido.parâmetros.id])
    se c == nulo então
        retorne resposta_json({"erro": "Cliente não encontrado."}, 404)
    fim
    retorne c                       # mapas, listas e registros viram JSON
fim)

app.arquivos("/estatico", "publico")          # serve a pasta publico/
app.iniciar(8000)                             # bloqueia até Ctrl+C ou app.parar()
```

**Rotas:** `app.get/post/put/patch/delete(caminho, função)` ou `app.rota(método, caminho, função)`.
Partes variáveis do caminho: `<nome>` (texto), `<id:inteiro>` (convertido para inteiro; se não for
número, a rota não corresponde) e `<resto:caminho>` (aceita `/`). Uma rota que existe com outro método
responde 405; um caminho desconhecido, 404.

**O pedido** é um mapa com: `método`, `caminho`, `parâmetros` (do caminho), `consulta` (da URL, após
`?`), `cabeçalhos` (nomes em minúsculas), `corpo` (texto), `json` (o corpo já convertido, quando é
JSON), `formulário` (campos de formulários HTML) e `cookies`.

**A resposta** é o que a função devolve:

| Valor devolvido | Resposta HTTP |
|-----------------|---------------|
| texto | 200, HTML |
| mapa, lista, registro, número, booleano | 200, JSON |
| nulo | 204, sem corpo |
| `resposta(corpo, [status], [cabeçalhos])` | completa (texto → HTML; demais → JSON) |
| `resposta_json(valor, [status], [cabeçalhos])` | JSON com o status escolhido |
| `resposta_html(texto, [status], [cabeçalhos])` | HTML com o status escolhido |
| `redirecionar(endereço, [status])` | 303 (ou o status informado) com `Location` |

**Antes de toda rota:** `app.antes(função(pedido) ... fim)` — se a função devolver algo diferente de
nulo, isso vira a resposta e a rota não é executada (autenticação, por exemplo).

**Erros:** se uma rota lança um erro não capturado, o servidor registra a mensagem no terminal e
responde 500 com `{"erro": ..., "código": ..., "linha": ...}`. Com a variável de ambiente
`GALO_PRODUCAO=1`, a resposta diz apenas "Erro interno no servidor." (os detalhes ficam no log).

**Execução:** o servidor atende várias conexões ao mesmo tempo, mas executa o código GALO de **um
pedido por vez** (as variáveis globais nunca são acessadas simultaneamente). Por segurança,
`iniciar` escuta apenas em `127.0.0.1`; use `app.iniciar(8000, "0.0.0.0")` para aceitar conexões de
outras máquinas (de preferência atrás de um proxy com HTTPS, como nginx ou Caddy).

## 5. Páginas geradas no servidor

```galo
app.get("/", função(pedido)
    retorne renderizar("paginas/inicio.html", {"titulo": "Loja", "produtos": produtos, "tem_produtos": verdadeiro})
fim)
```

```html
<h1>{{ titulo }}</h1>
{% se tem_produtos %}
<ul>{% para cada p em produtos %}<li>{{ p.nome }} — R$ {{ p.preço }}</li>{% fim %}</ul>
{% senão %}<p>Nada por aqui.</p>{% fim %}
{% inclua "rodape.html" %}
```

`{{ x }}` **escapa HTML** (um título `<script>` aparece como texto, não executa); `{{{ x }}}` insere
sem escape (só para HTML confiável). As condições de `{% se %}` devem ser booleanos — calcule-as em
GALO e passe nos dados. Para modelos curtos, `modelo(texto, dados)` faz o mesmo com um texto. Use
aspas simples (`'...'` ou `'''...'''`) para escrever modelos dentro do código: textos com aspas
simples não fazem interpolação, então `{{ }}` chega intacto ao modelo.

## 6. A interface no navegador

O servidor compila e entrega o programa do navegador:

```galo
app.cliente("/app.galoc", "cliente.galo")      # recompila sozinho quando o arquivo muda
```

```html
<script src="/_galo/galo.js"></script>                   <!-- a VM, servida pelo próprio servidor -->
<script type="application/galo" src="/app.galoc"></script> <!-- executado quando a página carrega -->
```

```galo
# cliente.galo
defina lista como elemento("#tarefas")
elemento("#formulario").ao("envio", função()
    defina campo como elemento("#titulo")
    buscar("/api/tarefas", {"método": "POST", "json": {"título": campo.valor}}, função(resposta)
        se resposta.ok então
            lista.adicionar(criar_elemento("li", resposta.json.título))
            campo.valor = ""
        senão
            alerta(resposta.json.erro)
        fim
    fim)
fim)
```

| Função | O que faz |
|--------|-----------|
| `elemento(seletor)`, `elementos(seletor)` | encontram elementos com seletores CSS (`"#id"`, `".classe"`, `"li"`) |
| `criar_elemento(etiqueta, [texto])` | cria um elemento novo |
| `buscar(endereço, opções, função)` | requisição HTTP sem travar a página; a função recebe `{status, ok, corpo, cabeçalhos, json}` |
| `depois(ms, f)`, `a_cada(ms, f)`, `cancelar_temporizador(id)` | temporizadores |
| `armazenar(chave, valor)`, `recuperar(chave, [padrão])`, `esquecer(chave)` | dados que sobrevivem ao recarregar a página |
| `alerta(m)`, `confirmar(m)`, `navegar(url)`, `endereço_atual()` | interação com o navegador |

Um **Elemento** tem as propriedades `texto`, `html`, `valor`, `marcado`, `etiqueta` e `filhos`, e os
métodos `ao(evento, função)`, `adicionar(filho ou texto)`, `remover()`, `limpar()`, `atributo(nome)`,
`definir_atributo(nome, valor)`, `remover_atributo(nome)`, `adicionar_classe`, `remover_classe`,
`alternar_classe`, `tem_classe`, `procurar(seletor)`, `procurar_todos(seletor)`, `focar()` e
`estilo(propriedade, valor)`. Eventos podem ser escritos em português — `"clique"`, `"envio"`,
`"mudança"`, `"entrada"`, `"tecla"`, `"foco"` — ou com o nome do DOM (`"click"`, `"keyup"`...). No
evento de envio de formulário o recarregamento da página é cancelado automaticamente. A função do
evento pode não ter parâmetros, ou receber um mapa com `tipo`, `alvo`, `tecla`, `valor` e as teclas
modificadoras `ctrl`, `shift`, `alt` e `meta` (booleanos): `se ev.tecla == "Enter" e ev.ctrl então ...`.

`texto` é sempre seguro para dados do usuário; `html` interpreta HTML e não deve receber dados do
usuário sem `escapar_html`.

Se o programa do navegador tiver um erro de execução, a mensagem completa (código, linha e rastro)
aparece no console e numa caixa vermelha na própria página. Erros de compilação de `cliente.galo`
aparecem no terminal do servidor e na resposta de `/app.galoc`.

**O que muda entre servidor e navegador:** a linguagem e quase toda a biblioteca são idênticas (há
testes que executam os mesmos programas na VM Python e no Chrome, no Firefox e no `gjs`, e comparam
as saídas byte a byte). Arquivos, banco de dados,
servidor web, `requisitar`, `hash_senha`, `modelo`/`renderizar`, `espere` e `variável_ambiente` só
existem no servidor; as funções de página só existem no navegador. Chamar uma função do lugar errado
dá o erro G327. `buscar` existe nos dois: no servidor a função é chamada na hora; no navegador,
quando a resposta chega. A referência completa indica onde cada função existe:
[biblioteca-padrao.md](biblioteca-padrao.md).

### 6.1 GALO dentro da GALO: compilar no servidor, executar no navegador

Para deixar quem visita a página escrever e rodar programas (um “playground”), o servidor compila
e o navegador executa — o código de quem visita nunca roda no servidor:

```galo
# servidor
app.post("/api/compilar", função(pedido)
    retorne compilar_programa(pedido.json.código)    # {ok, bytecode, erros, avisos}; não executa nada
fim)
```

```galo
# navegador
buscar("/api/compilar", {"método": "POST", "json": {"código": campo.valor}}, função(r)
    se não r.json.ok então
        mostre r.json.erros[1].texto                   # mensagem completa, com linha e sugestão
        retorne
    fim
    executar_programa(r.json.bytecode, {"entradas": ["Ana"], "limite_segundos": 5}, função(res)
        saída.texto = res.saída                         # res: {saída, erro, tempo, interrompido}
    fim)
fim)
```

`compilar_programa` recusa `importe` (compilar nunca lê arquivos do servidor). `executar_programa`
roda o programa num Web Worker, numa VM separada: a página não trava, o programa não enxerga as
variáveis nem a página de quem o executa, e é interrompido se passar do tempo (G330) ou escrever
mais de 1 MB (G331). O site em [`site/`](../site/) usa exatamente isso no “Experimente”.

## 7. Segurança

* **Senhas:** guarde só `hash_senha(senha)` e confira com `verificar_senha(senha, hash)` (PBKDF2-SHA256 com sal).
* **Sessões:** gere identificadores com `token_aleatório()` e envie como cookie `HttpOnly`:

```galo
defina sessoes como {}

app.post("/entrar", função(pedido)
    defina usuario como banco.consultar_um("SELECT * FROM usuarios WHERE email = ?", [pedido.json.email])
    se usuario == nulo ou não verificar_senha(pedido.json.senha, usuario.senha) então
        retorne resposta_json({"erro": "E-mail ou senha inválidos."}, 401)
    fim
    defina token como token_aleatório()
    sessoes[token] = usuario.email
    retorne resposta_json({"ok": verdadeiro}, 200, {"Set-Cookie": "sessao={token}; HttpOnly; SameSite=Lax; Path=/"})
fim)

app.antes(função(pedido)
    se começa_com(pedido.caminho, "/api") e não (obter(pedido.cookies, "sessao", "") em sessoes) então
        retorne resposta_json({"erro": "Faça login primeiro."}, 401)
    fim
    retorne nulo
fim)
```

* **SQL:** sempre com parâmetros (`?` / `:nome`).
* **HTML:** `{{ }}` nos modelos e `.texto` no navegador escapam automaticamente; use `escapar_html` ao montar HTML à mão.
* **Arquivos estáticos:** caminhos como `/../segredo.txt` são recusados (403).
* **Configuração e segredos:** leia com `variável_ambiente("NOME", padrão)` em vez de escrevê-los no código.

## 8. Testes

`app.testar(método, caminho, [corpo], [cabeçalhos])` executa um pedido **sem rede** e devolve
`{status, ok, corpo, cabeçalhos, json}`. Junto com `afirmar(condição, mensagem)` e um banco
`":memória:"`, dá para testar a aplicação inteira em GALO — veja
[`examples/tarefas/testes.galo`](../examples/tarefas/testes.galo):

```galo
defina app como criar_app(abrir_repositorio(":memória:"))
defina r como app.testar("POST", "/api/tarefas", {"título": "Comprar pão"})
afirmar(r.status == 201, "criar deveria devolver 201, devolveu {r.status}")
```

## 9. Colocando no ar

1. Instale a GALO no servidor (`./instalar.sh` ou `pip install .`).
2. Configure por variáveis de ambiente (porta, caminho do banco) e defina `GALO_PRODUCAO=1`.
3. Inicie com `galo executar servidor.galo` sob um gerenciador de processos (systemd, Docker...).
4. Coloque um proxy reverso com HTTPS na frente e use `app.iniciar(porta, "0.0.0.0")` só se o proxy
   estiver em outra máquina.

## 10. Limites desta versão

* Um processo executa um pedido de cada vez: adequado para aplicações pequenas e médias (medimos
  cerca de 1.200 a 1.400 pedidos por segundo em rotas simples com SQLite, um pedido por conexão),
  não para alto volume. Para escalar, rode vários processos
  atrás de um balanceador (com um banco compartilhado adequado).
* Banco de dados: apenas SQLite (embutido). Não há HTTPS embutido (use um proxy), nem WebSockets,
  nem envio de arquivos (*upload* multipart).
* `buscar` no navegador usa funções de retorno (*callbacks*); não há `async/await` na linguagem.
* Sessões, cookies e CORS são montados com cabeçalhos (sem utilitários dedicados).
