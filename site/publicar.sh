#!/bin/sh
# Gera a versão estática do site em _site/ (é o que o GitHub Actions publica no GitHub Pages).
#
#   sh site/publicar.sh                 # endereços na raiz do domínio
#   BASE=/GALO sh site/publicar.sh      # endereços em https://usuario.github.io/GALO/
#
# No site estático não há servidor: o compilador da GALO roda no navegador (Pyodide), carregado
# por site/publico/compilador.js, e os programas executam isolados como no servidor GALO.
set -eu

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
DESTINO="${DESTINO:-$RAIZ/_site}"
BASE="${BASE:-}"
PY="${PYTHON:-python3}"

rm -rf "$DESTINO"
mkdir -p "$DESTINO/experimente" "$DESTINO/painel" "$DESTINO/js" "$DESTINO/_galo" "$DESTINO/estatico"
cd "$RAIZ"

echo "Páginas:"
DESTINO="$DESTINO" BASE="$BASE" GALO_SEM_COR=1 "$PY" -m galo executar site/gerar_estatico.galo

echo "Programas do navegador:"
for cliente in inicio experimente painel basico; do
    "$PY" -m galo compilar "site/cliente/$cliente.galo" -o "$DESTINO/js/$cliente.galoc" >/dev/null
    echo "  js/$cliente.galoc"
done

echo "Arquivos:"
cp site/publico/* "$DESTINO/estatico/"
cp galo/web/galo.js "$DESTINO/_galo/galo.js"
# O compilador (o pacote galo, só os .py) vai num zip que o Pyodide abre no navegador.
"$PY" - "$DESTINO/_galo/compilador.zip" <<'PYTHON'
import os, sys, zipfile
with zipfile.ZipFile(sys.argv[1], "w", zipfile.ZIP_DEFLATED) as z:
    for raiz, pastas, arquivos in os.walk("galo"):
        pastas[:] = sorted(p for p in pastas if p != "__pycache__")
        for a in sorted(arquivos):
            if a.endswith(".py"):
                z.write(os.path.join(raiz, a))
PYTHON
touch "$DESTINO/.nojekyll"
echo "  estatico/, _galo/galo.js, _galo/compilador.zip"
echo "Pronto: $DESTINO (base: '${BASE:-/}')"
