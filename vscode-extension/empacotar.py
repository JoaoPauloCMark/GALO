"""Empacota a extensão em um arquivo .vsix sem precisar de Node.js nem do `vsce`.

Uso (na raiz do repositório):
    python3 vscode-extension/empacotar.py
    code --install-extension vscode-extension/galo-linguagem-0.1.0.vsix

Um .vsix é um arquivo ZIP com um manifesto (extension.vsixmanifest), a lista
de tipos de conteúdo ([Content_Types].xml) e os arquivos da extensão dentro
da pasta extension/.
"""

from __future__ import annotations

import json
import os
import sys
import zipfile
from xml.sax.saxutils import escape

AQUI = os.path.dirname(os.path.abspath(__file__))
ARQUIVOS = [
    "package.json",
    "extension.js",
    "language-configuration.json",
    "syntaxes/galo.tmLanguage.json",
    "snippets/galo.json",
    "README.md",
    "LICENSE",
]

CONTENT_TYPES = """<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension=".json" ContentType="application/json"/>
  <Default Extension=".js" ContentType="application/javascript"/>
  <Default Extension=".md" ContentType="text/markdown"/>
  <Default Extension=".txt" ContentType="text/plain"/>
  <Default Extension=".vsixmanifest" ContentType="text/xml"/>
  <Default Extension="" ContentType="text/plain"/>
</Types>
"""


def manifesto(pkg: dict) -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011" xmlns:d="http://schemas.microsoft.com/developer/vsx-schema-design/2011">
  <Metadata>
    <Identity Language="en-US" Id="{escape(pkg['name'])}" Version="{escape(pkg['version'])}" Publisher="{escape(pkg['publisher'])}"/>
    <DisplayName>{escape(pkg['displayName'])}</DisplayName>
    <Description xml:space="preserve">{escape(pkg['description'])}</Description>
    <Tags>{escape(','.join(pkg.get('keywords', [])))}</Tags>
    <Categories>{escape(','.join(pkg.get('categories', [])))}</Categories>
    <GalleryFlags>Public</GalleryFlags>
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.Engine" Value="{escape(pkg['engines']['vscode'])}"/>
      <Property Id="Microsoft.VisualStudio.Code.ExtensionDependencies" Value=""/>
      <Property Id="Microsoft.VisualStudio.Code.ExtensionPack" Value=""/>
      <Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value="workspace"/>
      <Property Id="Microsoft.VisualStudio.Code.LocalizedLanguages" Value=""/>
    </Properties>
    <License>extension/LICENSE</License>
  </Metadata>
  <Installation>
    <InstallationTarget Id="Microsoft.VisualStudio.Code"/>
  </Installation>
  <Dependencies/>
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/>
    <Asset Type="Microsoft.VisualStudio.Services.Content.Details" Path="extension/README.md" Addressable="true"/>
    <Asset Type="Microsoft.VisualStudio.Services.Content.License" Path="extension/LICENSE" Addressable="true"/>
  </Assets>
</PackageManifest>
"""


def main() -> int:
    with open(os.path.join(AQUI, "package.json"), encoding="utf-8") as f:
        pkg = json.load(f)
    faltando = [a for a in ARQUIVOS if not os.path.exists(os.path.join(AQUI, a))]
    if faltando:
        print("Arquivos faltando:", ", ".join(faltando), file=sys.stderr)
        return 1
    destino = os.path.join(AQUI, f"{pkg['name']}-{pkg['version']}.vsix")
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("extension.vsixmanifest", manifesto(pkg))
        for arquivo in ARQUIVOS:
            z.write(os.path.join(AQUI, arquivo), "extension/" + arquivo)
    print(f"Extensão empacotada: {destino}")
    print(f"Instale com: code --install-extension {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
