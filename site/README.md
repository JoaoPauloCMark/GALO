# Site da linguagem GALO — escrito em GALO

O site oficial da GALO: página de apresentação, exemplos executáveis, uma calculadora, um
“Experimente” para escrever e rodar programas no navegador e um painel ao vivo. **Servidor,
banco de dados, páginas, realce de sintaxe, calculadora, gráficos e interface são programas
GALO** — só o HTML dos modelos, o CSS e as imagens não são.

```bash
galo executar site/servidor.galo        # abra http://localhost:8080
galo executar site/testes.galo          # testes do site, sem rede (banco em memória)
```

**Sem banco de dados:** o servidor não guarda nada. Links compartilhados levam o programa no
próprio endereço (`/experimente#codigo=...`) e os “Seus números” do painel ficam no navegador de
cada pessoa (localStorage).

Variáveis de ambiente: `PORT` ou `PORTA` (padrão `8080`), `HOST` (padrão `127.0.0.1`; na web use
`0.0.0.0`) e `GALO_PRODUCAO=1` (erros internos sem detalhes para quem visita).

## Páginas

| Endereço | O que tem |
|----------|-----------|
| `/` | Apresentação: uma janela que digita e **executa** programas sozinha, recursos, um erro real do compilador, 12 exemplos executáveis, calculadora, mini painel e instalação |
| `/experimente` | Editor com realce de sintaxe e números de linha, execução (Ctrl+Enter), entradas para `leia()`, erros com a linha marcada, exemplos e links para compartilhar. `?exemplo=tabuada` abre um exemplo; `#codigo=...` abre um programa compartilhado |
| `/painel` | Cafeteria ao vivo (simulação: pedidos, fila, máquina de espresso, grãos) e “Seus números” (execuções, erros mais comuns e palavras-chave de quem está usando, guardados no navegador) |

## Como o “Experimente” funciona

```
navegador                                   servidor GALO
─────────                                   ─────────────
POST /api/compilar {código} ─────────────►  compilar_programa(código)   (só compila, nunca executa;
                                            ◄── {ok, bytecode, erros}     importe é recusado)
executar_programa(bytecode, {entradas},
    ao_concluir)  → roda num Web Worker, isolado da página: a página não trava e um programa
                    que passa de 5 s é interrompido (G330)
armazenar("galo-estatisticas", ...)          “Seus números”, só no navegador
```

O código de quem visita o site **nunca é executado no servidor**.

## Arquivos

| Arquivo | Papel |
|---------|-------|
| `servidor.galo` | ponto de entrada: lê a configuração, pré-compila os programas do navegador e inicia o servidor |
| `app.galo` | rotas das páginas e da API (`/api/compilar` e `/api/exemplos`) |
| `exemplos.galo` | lê os programas de `exemplos/` e os metadados dos comentários (`# título: ...`) |
| `compartilhado/realce.galo` | realce de sintaxe da GALO — usado no servidor e no navegador |
| `compartilhado/calculadora.galo` | analisador de expressões da calculadora (inteiros sem limite) |
| `compartilhado/graficos.galo` | gráficos SVG: linha, barras, rosca e “faísca” |
| `compartilhado/cafeteria.galo` | a simulação da cafeteria |
| `compartilhado/link.galo` | links de compartilhamento com o programa dentro do endereço |
| `compartilhado/estatisticas.galo` | “Seus números”: contagens guardadas no navegador |
| `cliente/*.galo` | o que roda no navegador em cada página (`comum.galo` é compartilhado) |
| `exemplos/*.galo` | os programas da galeria — para incluir um, basta criar o arquivo |
| `paginas/*.html` | modelos HTML (`partes/` tem o cabeçalho e o rodapé) |
| `publico/` | CSS, mascote e ícone |
| `Dockerfile` | imagem para publicar o site |
| `testes.galo` | 72 verificações: módulos compartilhados, páginas, API, compartilhamento, segurança |

Os módulos de `compartilhado/` rodam nas duas máquinas virtuais com o mesmo resultado: o programa
`tests/conformidade/site.galo` confere isso no gjs, no Chrome, no Edge, no Firefox e no WebKit.
O fluxo completo do site (cliques e teclas reais) é testado em `tests/test_site.py`.

## Publicando na web

O site precisa só de Python 3.10+ (sem dependências) e não grava nada em disco, então funciona em
qualquer hospedagem que rode um processo Python ou um contêiner (Render, Railway, Fly.io, uma VPS...).

**Com contêiner** — na raiz do projeto:

```bash
docker build -f site/Dockerfile -t galo-site .
docker run -p 8080:8080 galo-site
```

Nos serviços que constroem a partir do repositório, indique `site/Dockerfile` como Dockerfile e a
raiz do projeto como contexto. A porta vem da variável `PORT`, que esses serviços definem sozinhos.

**Sem contêiner** — o comando de início é:

```bash
HOST=0.0.0.0 GALO_PRODUCAO=1 python -m galo executar site/servidor.galo
```

Coloque o site atrás de HTTPS (os serviços acima já fazem isso). O servidor executa um pedido de
cada vez; como o navegador é quem executa os programas, o trabalho do servidor é pouco (páginas e
compilação). Se o site ficar muito movimentado, rode mais de uma instância — como não há estado,
qualquer instância atende qualquer pessoa.

## Adicionando um exemplo

Crie `exemplos/13-meu-exemplo.galo`:

```galo
# título: Meu exemplo
# emoji: 🌟
# descrição: O que ele mostra, em uma frase.
# entradas: Ana | 42
mostre "olá"
```

O número no começo do nome define a ordem; `entradas` (opcional) são as respostas de `leia()`.
