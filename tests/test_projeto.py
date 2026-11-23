"""Verificações de consistência entre implementação, documentação e ferramentas."""

import json
import os
import re
import subprocess
import sys
import unittest

from auxiliar import RAIZ
from galo.stdlib import BUILTINS


def ler(*partes):
    with open(os.path.join(RAIZ, *partes), encoding="utf-8") as f:
        return f.read()


class TestConsistencia(unittest.TestCase):
    def test_cada_modulo_importa_isoladamente(self):
        modulos = ["galo.runtime.values", "galo.runtime.vm", "galo.stdlib", "galo.compiler",
                   "galo.compiler.bytecode", "galo.session", "galo.cli.main", "galo.lsp.server"]
        for m in modulos:
            with self.subTest(modulo=m):
                r = subprocess.run([sys.executable, "-c", f"import {m}"], cwd=RAIZ, capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)

    def test_todo_codigo_de_erro_esta_documentado(self):
        usados = set()
        for raiz, _, arquivos in os.walk(os.path.join(RAIZ, "galo")):
            for a in arquivos:
                if a.endswith(".py"):
                    usados |= set(re.findall(r'"([GA]\d{3})"', ler(raiz, a)))
                elif a.endswith(".js"):  # a VM do navegador também lança erros (G330, G331...)
                    usados |= set(re.findall(r"erro\('([GA]\d{3})'", ler(raiz, a)))
        documentados = set(re.findall(r"^\| ([GA]\d{3}) \|", ler("docs", "erros.md"), re.M))
        self.assertEqual(usados - documentados, set(), "códigos sem documentação")
        self.assertEqual(documentados - usados, set(), "códigos documentados mas não usados")

    def test_toda_funcao_interna_tem_documentacao(self):
        sem_doc = [nf.name for nf in BUILTINS.values() if len(nf.doc.strip()) < 10]
        self.assertEqual(sem_doc, [])

    def test_referencia_da_biblioteca_esta_atualizada(self):
        sys.path.insert(0, os.path.join(RAIZ, "docs"))
        import gerar_referencia

        self.assertEqual(gerar_referencia.gerar(), ler("docs", "biblioteca-padrao.md"),
                         "rode: python3 docs/gerar_referencia.py")

    def test_gramatica_do_vscode_esta_atualizada(self):
        sys.path.insert(0, os.path.join(RAIZ, "vscode-extension"))
        import gerar_gramatica

        atual = json.loads(ler("vscode-extension", "syntaxes", "galo.tmLanguage.json"))
        self.assertEqual(gerar_gramatica.gramatica(), atual, "rode: python3 vscode-extension/gerar_gramatica.py")

    def test_arquivos_json_da_extensao_sao_validos(self):
        for arquivo in ("package.json", "language-configuration.json", os.path.join("snippets", "galo.json")):
            with self.subTest(arquivo=arquivo):
                json.loads(ler("vscode-extension", arquivo))
        pkg = json.loads(ler("vscode-extension", "package.json"))
        comandos = {c["command"] for c in pkg["contributes"]["commands"]}
        registrados = set(re.findall(r"registerCommand\('([\w.]+)'", ler("vscode-extension", "extension.js")))
        self.assertEqual(comandos, registrados)

    def test_palavras_reservadas_estao_na_gramatica(self):
        from galo.compiler.tokens import KEYWORDS

        gramatica = ler("docs", "grammar.md")
        for kw in KEYWORDS:
            self.assertIn(kw, gramatica)


if __name__ == "__main__":
    unittest.main()
