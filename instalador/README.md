# Instaladores da GALO

Instaladores de verdade para **Windows, macOS e Linux**: a pessoa baixa um arquivo, dá dois
cliques e pronto. Não é preciso ter Python nem baixar o repositório.

**Baixar:** https://github.com/JoaoPauloCMark/GALO/releases/latest

| Sistema | Arquivo | Instala em |
|---------|---------|------------|
| Windows 10 e 11 | `GALO-Instalador-Windows.exe` | `%LOCALAPPDATA%\Programs\GALO` (só para o usuário, sem administrador) |
| macOS (Apple Silicon) | `GALO-Instalador-macOS-AppleSilicon.pkg` | `/usr/local/galo` e `/usr/local/bin/galo` |
| macOS (Intel) | `GALO-Instalador-macOS-Intel.pkg` | `/usr/local/galo` e `/usr/local/bin/galo` |
| Ubuntu, Debian, Mint... | `galo-linux-amd64.deb` | `/opt/galo` e `/usr/bin/galo` |
| Qualquer Linux | `galo-linux-x64.tar.gz` → `sh instalar.sh` | `~/.local/share/galo` e `~/.local/bin/galo` (sem root) |

## O que cada instalador faz

* Instala **um Python 3.13 próprio** (do [python-build-standalone](https://github.com/astral-sh/python-build-standalone)),
  sem tocar em outros Pythons da máquina, e **só o pacote `galo`** — nada do site, dos testes
  ou da documentação. O comando `galo` usa esse Python em modo isolado (`-I`).
* Coloca o comando **`galo`** no PATH: funciona em qualquer pasta, em qualquer projeto.
* Faz o sistema **reconhecer os arquivos `.galo`** (e `.galoc`):
  * Windows: ícone da GALO; dois cliques executam o programa (`galo abrir`, que espera um Enter
    antes de fechar a janela); botão direito → *Editar* abre no Bloco de Notas;
  * Linux: tipo `text/x-galo` com ícone e a opção *Abrir com GALO*;
  * macOS: pelo editor de código (abaixo).
* Instala a **extensão para editores** (VS Code, Cursor, VSCodium, Windsurf) nos que estiverem
  instalados: cores, autocompletar, erros enquanto se digita. Se o editor for instalado depois,
  basta rodar `galo extensao`.
* Aparece em **Aplicativos instalados** (Windows) para desinstalar. No Linux, `sudo apt remove galo`
  ou `sh instalar.sh --desinstalar`; no macOS, `sudo rm -rf /usr/local/galo /usr/local/bin/galo`.

## Como os instaladores são gerados

O workflow [`.github/workflows/instaladores.yml`](../.github/workflows/instaladores.yml) roda a cada
push no `main` que mexa na linguagem: constrói os instaladores, **instala e testa cada um** num
Windows, num Mac Apple Silicon, num Mac Intel e num Ubuntu (executando [`teste.galo`](teste.galo)
e conferindo PATH, associação de arquivos e desinstalação) e publica uma **Release**. A Release é
criada quando a versão em `galo/__init__.py` ainda não tem uma; para publicar uma nova, aumente a
versão. Para regerar os arquivos de uma Release existente, rode o workflow à mão marcando
*substituir*.

Para gerar localmente:

```bash
python3 instalador/construir.py linux-x64 windows-x64   # no Linux (precisa do makensis, pacote nsis)
python3 instalador/construir.py macos-arm64 macos-x64   # no macOS
```

Os arquivos vão para `dist/instaladores/`. O Python portátil é baixado uma vez para
`instalador/.cache/`, com o SHA-256 conferido.

| Arquivo | Papel |
|---------|-------|
| `construir.py` | monta tudo: baixa o Python, tira o que a GALO não usa, copia o pacote `galo` e gera cada instalador |
| `windows/galo.nsi` | instalador do Windows (NSIS), em português |
| `windows/galo.cmd`, `windows/caminho.ps1` | o comando `galo` e o ajuste do PATH do usuário |
| `macos/` | script de pós-instalação e textos do instalador do macOS |
| `linux/` | tipo de arquivo, atalho "Abrir com GALO" e o `instalar.sh` do `.tar.gz` |
| `icones/` | ícone da GALO (SVG, PNG e ICO) |
| `teste.galo` | verificação rápida de uma instalação |

## Assinatura digital

Os instaladores ainda não são assinados (isso exige certificados pagos: um de *code signing* para
o Windows e a conta de desenvolvedor da Apple para o macOS). Por isso:

* **Windows:** pode aparecer "O Windows protegeu o computador" → *Mais informações* → *Executar assim mesmo*.
* **macOS:** se o instalador for bloqueado, abra *Ajustes do Sistema → Privacidade e Segurança* e
  clique em *Abrir Mesmo Assim*.
