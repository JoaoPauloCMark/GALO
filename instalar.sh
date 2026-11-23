#!/bin/sh
# Instalador da GALO para Linux e macOS. Não precisa de pip nem de internet.
#
#   ./instalar.sh                 instala o comando `galo` em ~/.local/bin
#   PREFIXO=/opt/galo ./instalar.sh   instala em outro lugar
#   ./instalar.sh --pyz           gera dist/galo.pyz (um único arquivo executável)
#   ./instalar.sh --vscode        instala a extensão do VS Code (precisa do comando `code`)
#   ./instalar.sh --desinstalar   remove o que foi instalado
set -eu

ORIGEM="$(cd "$(dirname "$0")" && pwd)"
PREFIXO="${PREFIXO:-$HOME/.local}"
PASTA_LIB="$PREFIXO/lib/galo"
PASTA_BIN="$PREFIXO/bin"
LANCADOR="$PASTA_BIN/galo"

uso() {
    sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'
}

encontrar_python() {
    for candidato in "${PYTHON:-}" python3 python; do
        [ -n "$candidato" ] || continue
        if command -v "$candidato" >/dev/null 2>&1 &&
           "$candidato" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
            command -v "$candidato"
            return 0
        fi
    done
    return 1
}

exigir_python() {
    PY="$(encontrar_python)" || {
        echo "Erro: a GALO precisa do Python 3.10 ou mais recente (não encontrado)." >&2
        echo "Instale o Python 3 pelo gerenciador de pacotes do sistema e tente de novo." >&2
        exit 1
    }
}

desinstalar() {
    rm -rf "$PASTA_LIB"
    rm -f "$LANCADOR"
    echo "GALO removida de $PREFIXO."
}

gerar_pyz() {
    exigir_python
    temporario="$(mktemp -d)"
    trap 'rm -rf "$temporario"' EXIT
    cp -R "$ORIGEM/galo" "$temporario/galo"
    find "$temporario/galo" -name '__pycache__' -type d -prune -exec rm -rf {} +
    printf 'import sys\nfrom galo.cli.main import main\nsys.exit(main())\n' > "$temporario/__main__.py"
    mkdir -p "$ORIGEM/dist"
    "$PY" -m zipapp "$temporario" -p "/usr/bin/env python3" -o "$ORIGEM/dist/galo.pyz"
    echo "Gerado: $ORIGEM/dist/galo.pyz  (execute com: ./dist/galo.pyz --versao)"
}

instalar_vscode() {
    exigir_python
    "$PY" "$ORIGEM/vscode-extension/empacotar.py"
    vsix="$(ls "$ORIGEM"/vscode-extension/*.vsix | tail -n 1)"
    if command -v code >/dev/null 2>&1; then
        code --install-extension "$vsix"
    else
        echo "O comando 'code' não foi encontrado no PATH."
        echo "No VS Code, use: Extensões → ... → Instalar a partir do VSIX → $vsix"
    fi
}

instalar() {
    exigir_python
    mkdir -p "$PASTA_LIB" "$PASTA_BIN"
    rm -rf "$PASTA_LIB/galo"
    cp -R "$ORIGEM/galo" "$PASTA_LIB/galo"
    find "$PASTA_LIB/galo" -name '__pycache__' -type d -prune -exec rm -rf {} +
    "$PY" -m compileall -q "$PASTA_LIB/galo" >/dev/null
    # O lançador usa -I (modo isolado) para que pastas do usuário não interfiram
    # na importação; o caminho da biblioteca é passado como argumento.
    cat > "$LANCADOR" <<EOF
#!/bin/sh
exec "$PY" -I -c 'import sys; sys.path.insert(0, sys.argv.pop(1)); from galo.cli.main import main; sys.exit(main())' "$PASTA_LIB" "\$@"
EOF
    chmod +x "$LANCADOR"
    echo "GALO instalada em $PREFIXO (Python: $PY)."
    "$LANCADOR" --versao
    case ":$PATH:" in
        *":$PASTA_BIN:"*) echo "Pronto! Experimente: galo repl" ;;
        *)
            echo
            echo "Atenção: $PASTA_BIN não está no seu PATH. Adicione esta linha ao ~/.bashrc ou ~/.zshrc:"
            echo "    export PATH=\"$PASTA_BIN:\$PATH\""
            ;;
    esac
}

case "${1:-}" in
    "") instalar ;;
    --desinstalar) desinstalar ;;
    --pyz) gerar_pyz ;;
    --vscode) instalar_vscode ;;
    -h|--ajuda) uso ;;
    *) echo "Opção desconhecida: $1" >&2; uso; exit 64 ;;
esac
