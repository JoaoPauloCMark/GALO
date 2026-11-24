#!/bin/sh
# Instala a GALO só para você, sem precisar de root (qualquer distribuição Linux).
#
#   sh instalar.sh                  instala em ~/.local (comando ~/.local/bin/galo)
#   sh instalar.sh --desinstalar    remove
#   PREFIXO=/outro/lugar sh instalar.sh
#
# A pasta vem com um Python próprio: não é preciso ter Python instalado.
set -eu

ORIGEM="$(cd "$(dirname "$0")" && pwd)"
PREFIXO="${PREFIXO:-$HOME/.local}"
DESTINO="$PREFIXO/share/galo"
BIN="$PREFIXO/bin"
DADOS="$PREFIXO/share"

atualizar_caches() {
    if command -v update-mime-database >/dev/null 2>&1; then update-mime-database "$DADOS/mime" >/dev/null 2>&1 || true; fi
    if command -v update-desktop-database >/dev/null 2>&1; then update-desktop-database "$DADOS/applications" >/dev/null 2>&1 || true; fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then gtk-update-icon-cache -q -t "$DADOS/icons/hicolor" >/dev/null 2>&1 || true; fi
}

desinstalar() {
    rm -rf "$DESTINO"
    rm -f "$BIN/galo" "$DADOS/mime/packages/galo.xml" "$DADOS/applications/galo.desktop" \
          "$DADOS/icons/hicolor/scalable/apps/galo.svg" "$DADOS/icons/hicolor/scalable/mimetypes/text-x-galo.svg" \
          "$DADOS/icons/hicolor/scalable/mimetypes/application-x-galo-bytecode.svg"
    atualizar_caches
    echo "GALO removida de $PREFIXO."
}

if [ "${1:-}" = "--desinstalar" ]; then
    desinstalar
    exit 0
fi

echo "Instalando a GALO em $DESTINO..."
rm -rf "$DESTINO"
mkdir -p "$DESTINO" "$BIN" "$DADOS/mime/packages" "$DADOS/applications" \
         "$DADOS/icons/hicolor/scalable/apps" "$DADOS/icons/hicolor/scalable/mimetypes"
cp -R "$ORIGEM/runtime" "$DESTINO/runtime"
cp "$ORIGEM/galo.vsix" "$ORIGEM/LICENSE" "$DESTINO/"

# o comando galo usa o Python embutido, isolado de outros Pythons da máquina
cat > "$BIN/galo" <<FIM
#!/bin/sh
exec "$DESTINO/runtime/bin/python3" -I -X utf8 -m galo "\$@"
FIM
chmod 755 "$BIN/galo"

# arquivos .galo: tipo, ícone e "Abrir com GALO"
cp "$ORIGEM/linux/galo.xml" "$DADOS/mime/packages/galo.xml"
cp "$ORIGEM/icones/galo.svg" "$DADOS/icons/hicolor/scalable/apps/galo.svg"
cp "$ORIGEM/icones/galo.svg" "$DADOS/icons/hicolor/scalable/mimetypes/text-x-galo.svg"
cp "$ORIGEM/icones/galo.svg" "$DADOS/icons/hicolor/scalable/mimetypes/application-x-galo-bytecode.svg"
sed "s|@GALO@|$BIN/galo|" "$ORIGEM/linux/galo.desktop" > "$DADOS/applications/galo.desktop"
atualizar_caches

"$DESTINO/runtime/bin/python3" -I -m compileall -q "$DESTINO/runtime/lib/python3.13/site-packages/galo" >/dev/null 2>&1 || true
echo
"$BIN/galo" --versao
if [ "${GALO_SEM_EXTENSAO:-}" = "" ]; then
    "$BIN/galo" extensao || true
fi
echo
case ":$PATH:" in
    *":$BIN:"*) echo "Pronto! Experimente:  galo repl" ;;
    *) echo "Pronto! Falta só uma coisa: $BIN não está no seu PATH."
       echo "Adicione esta linha ao ~/.bashrc (ou ~/.zshrc) e abra um terminal novo:"
       echo "    export PATH=\"$BIN:\$PATH\"" ;;
esac
