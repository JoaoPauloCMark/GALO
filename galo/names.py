"""Forma canônica de nomes, compartilhada pelo compilador e pelo runtime."""

from __future__ import annotations

import unicodedata


def canonical(text: str) -> str:
    """Remove acentos e cedilha: em GALO, `função`/`funcao` e `pontuação`/`pontuacao`
    são o mesmo nome. Maiúsculas e minúsculas continuam diferentes."""
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return unicodedata.normalize("NFC", stripped)
