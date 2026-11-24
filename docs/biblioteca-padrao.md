# Biblioteca padrão da GALO

> Arquivo gerado por `docs/gerar_referencia.py` a partir das funções registradas na
> implementação. Não edite à mão.

Todos os nomes podem ser escritos com ou sem acentos (`maiúsculas` ou `maiusculas`).
Argumentos entre colchetes são opcionais. Posições de listas e textos começam em 1.
A instrução `mostre` não é uma função: veja a [especificação](language-spec.md).
São 126 funções internas e 1 constante(s).
Funções marcadas com *(só no servidor)* não existem na VM do navegador; as da seção
*Página* só existem no navegador. Todo o resto funciona igual nos dois lugares.

## Entrada e saída

### `escreva(valores...)` → `nulo`

Escreve os valores separados por espaço, sem pular de linha.

### `leia([mensagem])` → `texto ou nulo`

Lê uma linha digitada no terminal e devolve o texto (sem a quebra de linha). Se a mensagem for informada, ela é mostrada antes da leitura. Devolve nulo quando não há mais entrada disponível.

## Texto

### `aparar(texto)` → `texto`

Remove espaços e quebras de linha do início e do fim do texto.

### `caractere(código)` → `texto`

Caractere correspondente a um código Unicode (por exemplo, caractere(65) é "A").

### `caracteres(texto)` → `lista`

Lista com cada caractere do texto.

### `código(caractere)` → `inteiro`

Código Unicode de um caractere (por exemplo, código("A") é 65).

### `começa_com(texto, prefixo)` → `booleano`

Verdadeiro se o texto começar com o prefixo.

### `contém(coleção, valor)` → `booleano`

Verdadeiro se o valor estiver na lista, no texto ou entre as chaves do mapa (o mesmo que `valor em coleção`).

### `corresponde(texto, padrão)` → `booleano`

Verdadeiro se o texto contém um trecho que segue a expressão regular. Use ^ e $ para exigir o texto inteiro: corresponde(email, "^[^@]+@[^@]+$").

### `dividir(texto, [separador])` → `lista`

Divide o texto em uma lista de partes. Sem separador, divide nos espaços.

### `é_número(texto)` → `booleano`

Verdadeiro se o texto representa um número (útil para validar o que foi digitado).

### `fatia(coleção, início, [fim])` → `texto ou lista`

Parte de um texto ou lista, da posição início até a posição fim (inclusive). Posições negativas contam a partir do fim. Sem `fim`, vai até o último elemento.

### `formatar(número, casas)` → `texto`

Texto com o número escrito com a quantidade fixa de casas decimais (arredondamento comercial).

### `inverter(valor)` → `texto ou lista`

Novo texto ou nova lista com os elementos em ordem inversa.

### `juntar(lista, [separador])` → `texto`

Junta os elementos da lista em um único texto, colocando o separador entre eles.

### `maiúsculas(texto)` → `texto`

Converte o texto para letras maiúsculas.

### `minúsculas(texto)` → `texto`

Converte o texto para letras minúsculas.

### `posição(coleção, valor)` → `inteiro ou nulo`

Posição (a partir de 1) da primeira ocorrência do valor no texto ou na lista; nulo se não existir.

### `procurar_todos(texto, padrão)` → `lista`

Lista com todos os trechos do texto que seguem a expressão regular.

### `repetir(texto, vezes)` → `texto`

Repete o texto o número de vezes indicado.

### `substituir(texto, antigo, novo)` → `texto`

Troca todas as ocorrências de `antigo` por `novo` no texto.

### `substituir_padrão(texto, padrão, novo)` → `texto`

Troca todos os trechos que seguem a expressão regular por `novo` (\1, \2... repetem grupos).

### `tamanho(valor)` → `inteiro`

Quantidade de elementos de uma lista, de caracteres de um texto ou de pares de um mapa.

### `termina_com(texto, sufixo)` → `booleano`

Verdadeiro se o texto terminar com o sufixo.

## Matemática

### `absoluto(x)` → `número`

Valor absoluto (distância até zero).

### `aleatório()` → `decimal`

Número decimal aleatório entre 0 (inclusive) e 1 (exclusive).

### `aleatório_entre(minimo_, maximo_)` → `inteiro`

Inteiro aleatório entre os dois valores (ambos inclusive).

### `arredondar(número, [casas])` → `número`

Arredonda para o inteiro mais próximo (ou para a quantidade de casas decimais). Metades são arredondadas para longe do zero: arredondar(2.5) é 3.

### `cosseno(x)` → `decimal`

Cosseno de um ângulo em radianos (resultado corretamente arredondado, igual em qualquer plataforma).

### `logaritmo(x, [base])` → `decimal`

Logaritmo de x. Sem base, usa o logaritmo natural (base e). O resultado é corretamente arredondado e igual em qualquer plataforma: logaritmo(1000, 10) é exatamente 3.0.

### `máximo(valores...)`

Maior valor entre os argumentos (ou entre os elementos de uma lista).

### `média(lista)` → `decimal`

Média aritmética dos números de uma lista.

### `mínimo(valores...)`

Menor valor entre os argumentos (ou entre os elementos de uma lista).

### `piso(x)` → `inteiro`

Maior inteiro menor ou igual ao número.

### `potência(base, expoente)` → `número`

base elevada ao expoente (o mesmo que base ^ expoente).

### `raiz(x)` → `decimal`

Raiz quadrada.

### `semente_aleatória(semente)` → `nulo`

Fixa a semente dos números aleatórios, tornando a sequência reproduzível — a mesma no servidor e no navegador. Para senhas e sessões, use token_aleatório().

### `seno(x)` → `decimal`

Seno de um ângulo em radianos (resultado corretamente arredondado, igual em qualquer plataforma).

### `soma(lista)` → `número`

Soma dos números de uma lista.

### `tangente(x)` → `decimal`

Tangente de um ângulo em radianos (resultado corretamente arredondado, igual em qualquer plataforma).

### `teto(x)` → `inteiro`

Menor inteiro maior ou igual ao número.

### `pi` (constante)

A constante π (3.141592653589793).

## Listas e mapas

### `adicionar(lista, valor)` → `nulo`

Adiciona o valor ao final da lista.

### `algum(lista, função)` → `booleano`

Verdadeiro se a função devolver verdadeiro para pelo menos um elemento.

### `chaves(mapa)` → `lista`

Lista com as chaves do mapa, na ordem em que foram inseridas.

### `contar(coleção, valor)` → `inteiro`

Quantas vezes o valor aparece na lista (ou o trecho aparece no texto).

### `copiar(valor)`

Cópia de uma lista ou mapa (os elementos internos não são copiados).

### `filtrar(lista, função)` → `lista`

Nova lista só com os elementos para os quais a função devolve verdadeiro.

### `inserir(lista, posição, valor)` → `nulo`

Insere o valor na posição indicada, deslocando os demais elementos para a direita.

### `intervalo(início, fim, [passo])` → `lista`

Lista com os números de início até fim (inclusive), andando de passo em passo.

### `limpar(coleção)` → `nulo`

Remove todos os elementos de uma lista ou mapa.

### `mapear(lista, função)` → `lista`

Nova lista com o resultado da função aplicada a cada elemento.

### `nova_lista(tamanho, [valor_inicial])` → `lista`

Lista com `tamanho` elementos iguais ao valor inicial (nulo se omitido).

### `obter(coleção, chave, [padrão])`

Valor da chave no mapa (ou da posição na lista); devolve o padrão (nulo) se não existir.

### `ordenar(lista)` → `lista`

Nova lista com os elementos em ordem crescente (números ou textos). A lista original não muda.

### `ordenar_por(lista, função_chave)` → `lista`

Nova lista ordenada pelo valor que a função devolve para cada elemento.

### `pares(mapa)` → `lista`

Lista de pares [chave, valor] do mapa.

### `primeiro(lista)`

Primeiro elemento da lista.

### `reduzir(lista, função, valor_inicial)`

Combina os elementos: aplica função(acumulado, elemento) do primeiro ao último.

### `remover(lista, posição)`

Remove o elemento da posição indicada e o devolve.

### `remover_chave(mapa, chave)`

Remove a chave do mapa e devolve o valor que ela tinha (nulo se não existia).

### `remover_valor(lista, valor)` → `booleano`

Remove a primeira ocorrência do valor. Devolve verdadeiro se algo foi removido.

### `todos(lista, função)` → `booleano`

Verdadeiro se a função devolver verdadeiro para todos os elementos.

### `último(lista)`

Último elemento da lista.

### `valores(mapa)` → `lista`

Lista com os valores do mapa.

### `vazio(coleção)` → `booleano`

Verdadeiro se a lista, o texto ou o mapa não tiver elementos.

## Conversão de tipos

### `booleano(valor)` → `booleano`

Converte os textos "verdadeiro" e "falso" em booleano.

### `decimal(valor)` → `decimal`

Converte em número decimal. Aceita textos como "3.5" ou "3,5".

### `inteiro(valor)` → `inteiro`

Converte em inteiro. Decimais são truncados (a parte fracionária é descartada); textos precisam conter um número inteiro, como "42".

### `número(valor)` → `número`

Converte um texto em inteiro ou decimal, conforme o conteúdo ("42" -> 42, "3,5" -> 3.5).

### `texto(valor)` → `texto`

Converte qualquer valor em texto (a mesma forma usada por `mostre`).

### `tipo(valor)` → `texto`

Nome do tipo do valor: "inteiro", "decimal", "texto", "booleano", "lista", "mapa", "nulo" ou "função".

## JSON

### `de_json(texto)`

Converte um texto JSON em valor GALO: objetos viram mapas, arrays viram listas.

### `para_json(valor, [indentação])` → `texto`

Converte o valor (mapas, listas, registros, textos, números, booleanos, nulo) em um texto JSON. Com indentação (por exemplo 2), o resultado fica formatado em várias linhas.

## Arquivos

### `anexar_arquivo(caminho, conteudo)` → `nulo` *(só no servidor)*

Acrescenta o conteúdo ao final do arquivo (criando-o se não existir).

### `apagar_arquivo(caminho)` → `nulo` *(só no servidor)*

Apaga o arquivo.

### `arquivo_existe(caminho)` → `booleano` *(só no servidor)*

Verdadeiro se existir um arquivo nesse caminho.

### `escrever_arquivo(caminho, conteudo)` → `nulo` *(só no servidor)*

Grava o conteúdo no arquivo, substituindo o que havia antes.

### `ler_arquivo(caminho)` → `texto` *(só no servidor)*

Conteúdo completo de um arquivo de texto.

### `ler_linhas(caminho)` → `lista` *(só no servidor)*

Lista com as linhas de um arquivo de texto (sem as quebras de linha).

### `listar_arquivos([pasta])` → `lista` *(só no servidor)*

Lista em ordem alfabética com os nomes dos itens de uma pasta.

## Data e hora

### `agora()` → `mapa`

Mapa com a data e a hora atuais: ano, mês, dia, hora, minuto, segundo e dia_da_semana.

### `data_atual()` → `texto`

Data de hoje no formato DD/MM/AAAA.

### `data_hora_iso([segundos])` → `texto`

Data e hora no padrão ISO 8601 (2026-11-22T18:30:00), boa para guardar em bancos e APIs. Sem argumento usa o momento atual; com `segundos` (como os de tempo()) converte aquele instante.

### `espere(segundos)` → `nulo` *(só no servidor)*

Pausa o programa pela quantidade de segundos indicada.

### `hora_atual()` → `texto`

Hora atual no formato HH:MM:SS.

### `tempo()` → `decimal`

Segundos decorridos desde 01/01/1970 (útil para medir durações).

## Sistema

### `afirmar(condição, [mensagem])` → `nulo`

Verifica uma condição (útil em testes): se ela for falsa, interrompe com o erro G329 e a mensagem.

### `argumentos()` → `lista`

Lista com os argumentos passados ao programa na linha de comando (por exemplo: galo executar programa.galo um dois).

### `sair([código])` → `nulo`

Encerra o programa imediatamente com o código de saída indicado (0 = sucesso).

### `variável_ambiente(nome, [padrão])` *(só no servidor)*

Valor (texto) de uma variável de ambiente do sistema, ou o padrão (nulo) se ela não existir. Útil para configurar porta, senhas e caminhos sem alterar o código.

## Segurança e codificação

### `codificar_base64(texto)` → `texto`

Codifica o texto (UTF-8) em Base64.

### `codificar_url(texto)` → `texto`

Codifica o texto para uso seguro dentro de uma URL (espaço vira %20, etc.).

### `decodificar_base64(texto)` → `texto`

Decodifica um texto em Base64 de volta para texto UTF-8.

### `decodificar_url(texto)` → `texto`

Desfaz a codificação de URL (%20 vira espaço, etc.).

### `escapar_html(texto)` → `texto`

Troca < > & " ' por entidades HTML, para mostrar texto do usuário em páginas com segurança.

### `hash_senha(senha)` → `texto` *(só no servidor)*

Gera um hash seguro da senha (PBKDF2-SHA256 com sal aleatório), próprio para guardar no banco. Nunca guarde senhas em texto puro.

### `sha256(texto)` → `texto` *(só no servidor)*

Resumo SHA-256 do texto, em hexadecimal. Não use para senhas: use hash_senha().

### `token_aleatório([bytes])` → `texto`

Texto aleatório e imprevisível (seguro para criptografia), bom para sessões e chaves de API.

### `uuid()` → `texto`

Identificador único universal aleatório (UUID versão 4), como "1b4e28ba-2fa1-11d2-883f-0016d3cca427".

### `verificar_senha(senha, hash)` → `booleano` *(só no servidor)*

Verdadeiro se a senha corresponde ao hash gerado por hash_senha().

## Banco de dados (SQLite)

### `abrir_banco(caminho)` *(só no servidor)*

Abre (ou cria) um banco de dados SQLite. Use ":memória:" para um banco temporário. Devolve um BancoDeDados com os métodos executar, executar_script, inserir, consultar, consultar_um, transação e fechar. Valores entram sempre como parâmetros (? ou :nome).

## Modelos HTML

### `modelo(texto_do_modelo, [dados])` → `texto` *(só no servidor)*

Preenche um modelo de texto com os dados (mapa ou registro). {{ x }} insere o valor com escape HTML; {{{ x }}} sem escape; {% se x %}, {% para cada i em lista %}, {% inclua "arquivo" %} e {% fim %} controlam o modelo.

### `renderizar(arquivo, [dados])` → `texto` *(só no servidor)*

Lê um arquivo de modelo (por exemplo, paginas/inicio.html) e o preenche com os dados. Veja modelo() para a sintaxe. Inclusões são relativas à pasta do arquivo.

## Web: servidor e cliente HTTP

### `buscar(endereço, opções, ao_concluir)` → `nulo`

Como requisitar(), mas entrega a resposta para a função ao_concluir(resposta). No navegador a requisição não bloqueia a página; no servidor ela é feita na hora. Assim o mesmo código funciona nos dois lados. Se a rede falhar, a resposta tem status 0, ok falso e o campo "erro" com a explicação.

### `criar_servidor()` *(só no servidor)*

Cria um servidor web. Métodos: rota(método, caminho, função), get/post/put/delete/patch(caminho, função), arquivos(prefixo, pasta), antes(função), cliente(url, arquivo.galo), iniciar([porta], [host]), parar() e testar(método, caminho, [corpo], [cabeçalhos]).

### `redirecionar(endereço, [status])` *(só no servidor)*

Resposta que manda o navegador para outro endereço (útil depois de enviar formulários).

### `requisitar(endereço, [opções])` → `mapa` *(só no servidor)*

Faz uma requisição HTTP e espera a resposta. Opções (mapa): "método", "cabeçalhos", "json" (valor enviado como JSON), "corpo" (texto) e "tempo_limite" (segundos). Devolve um mapa com status, ok, corpo, cabeçalhos e json (corpo já convertido, quando for JSON).

### `resposta(corpo, [status], [cabeçalhos])` *(só no servidor)*

Resposta HTTP completa. Textos são enviados como estão (HTML por padrão); mapas, listas e registros viram JSON.

### `resposta_html(texto, [status], [cabeçalhos])` *(só no servidor)*

Resposta HTTP com uma página HTML.

### `resposta_json(valor, [status], [cabeçalhos])` *(só no servidor)*

Resposta HTTP com o valor convertido em JSON.

## Página (somente no navegador)

### `a_cada(milissegundos, função)` → `inteiro`

Executa a função repetidamente, a cada intervalo. Devolve um identificador. Só no navegador.

### `alerta(mensagem)` → `nulo`

Mostra uma caixa de mensagem no navegador.

### `armazenar(chave, valor)` → `nulo`

Guarda um valor no navegador (localStorage); ele continua lá depois de recarregar a página.

### `cancelar_temporizador(identificador)` → `nulo`

Cancela um temporizador criado por depois() ou a_cada(). Só no navegador.

### `confirmar(mensagem)` → `booleano`

Pergunta sim/não ao usuário do navegador; devolve verdadeiro se ele confirmar.

### `copiar_texto(texto)` → `booleano`

Copia o texto para a área de transferência (como Ctrl+C), por exemplo num botão "copiar". Devolve verdadeiro se o navegador aceitou copiar. Só no navegador.

### `criar_elemento(etiqueta, [texto])`

Cria um novo elemento HTML (por exemplo "li"), opcionalmente com um texto. Só no navegador.

### `depois(milissegundos, função)` → `inteiro`

Executa a função uma vez, depois do tempo indicado. Devolve um identificador. Só no navegador.

### `elemento(seletor)`

Primeiro elemento da página que corresponde ao seletor CSS ("#id", ".classe", "tag"), ou nulo. Elementos têm: texto, html, valor, marcado, ao(evento, função), adicionar(filho), remover(), limpar(), atributo(nome), definir_atributo(nome, valor), adicionar_classe, remover_classe, alternar_classe, procurar(seletor), focar() e estilo(propriedade, valor). Só no navegador.

### `elementos(seletor)` → `lista`

Lista com todos os elementos da página que correspondem ao seletor CSS. Só no navegador.

### `endereço_atual()` → `texto`

Endereço (URL) da página atual no navegador.

### `esquecer(chave)` → `nulo`

Apaga um valor guardado com armazenar(). Só no navegador.

### `navegar(endereço)` → `nulo`

Leva o navegador para outro endereço.

### `recuperar(chave, [padrão])`

Lê um valor guardado com armazenar(), ou o padrão (nulo) se não existir. Só no navegador.

## GALO dentro da GALO: compilar e executar programas

### `compilar_programa(código, [nome])` → `mapa` *(só no servidor)*

Compila código GALO (um texto) sem executá-lo. Devolve um mapa com ok (booleano), bytecode (o programa compilado, em base64, pronto para executar_programa no navegador), erros e avisos (listas de mapas com código, tipo, mensagem, sugestão, linha, coluna e texto — a mensagem completa, como no terminal). O código não pode usar importe: compilar nunca lê arquivos do servidor.

### `executar_programa(bytecode, opções, ao_concluir)` → `nulo`

Executa um programa compilado por compilar_programa(), isolado da página (num Web Worker: a página não trava). opções (mapa ou nulo): entradas (lista de textos para leia()), limite_segundos (padrão 5), ao_escrever (função chamada com cada trecho de saída). Ao terminar, ao_concluir recebe {saída, erro, tempo, interrompido}; erro é nulo ou um mapa com código, mensagem, linha, coluna, sugestão e texto. Programas que passam do tempo são interrompidos (G330); saída acima de 1 MB também (G331). Só no navegador.
