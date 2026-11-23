# GALO para Visual Studio Code

Suporte à linguagem de programação **GALO** (arquivos `.galo`).

## Recursos

- Identificação de arquivos `.galo` e realce de sintaxe (palavras-chave, textos com
  interpolação `{...}`, números, comentários `#` e `#[ ... ]#`, funções internas).
- Autoindentação depois de `então`, `faça`, `vezes`, `senão`, `tente`, `capture` e de
  cabeçalhos de função; recuo automático ao digitar `fim`, `senão` e `capture`.
- Snippets: `se`, `sesenao`, `senaose`, `enquanto`, `para`, `parapasso`, `paracada`,
  `paracadachave`, `repita`, `funcao`, `funcaotipada`, `lambda`, `tente`, `defina`, `programa`.
- Diagnósticos enquanto você digita, autocompletar e documentação ao passar o mouse,
  pelo servidor de linguagem `galo lsp`.
- Comandos (Ctrl+Shift+P → "GALO"): **Executar arquivo** (também no botão ▶ do editor),
  **Compilar para bytecode**, **Compilar e rodar o bytecode**, **Verificar erros**,
  **Abrir modo interativo (REPL)** e **Reiniciar servidor de linguagem**.
- Tarefas (Terminal → Executar Tarefa → galo): `executar`, `compilar`, `verificar`, com
  os erros aparecendo no painel Problemas.

## Requisitos

O comando `galo` precisa estar instalado (veja o README do projeto). Se ele não estiver
no PATH, informe o caminho em **Configurações → GALO: Caminho Executavel**.

## Exemplo de tarefa (`.vscode/tasks.json`)

```json
{
  "version": "2.0.0",
  "tasks": [
    { "type": "galo", "comando": "executar", "label": "GALO: executar", "group": "build" },
    { "type": "galo", "comando": "verificar", "label": "GALO: verificar" }
  ]
}
```
