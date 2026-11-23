"""Segurança e codificação: senhas, tokens, hashes, HTML, URLs e Base64."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import html
import secrets
import uuid as _uuid
from urllib.parse import quote, unquote

from ._util import erro, exige_inteiro, exige_texto
from .registry import nativa

ITERACOES = 120_000


@nativa("hash_senha", retorna="texto")
def hash_senha(vm, senha):
    """Gera um hash seguro da senha (PBKDF2-SHA256 com sal aleatório), próprio para guardar no banco.
    Nunca guarde senhas em texto puro."""
    exige_texto("hash_senha", 1, senha)
    sal = secrets.token_bytes(16)
    chave = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), sal, ITERACOES)
    return "pbkdf2_sha256${}${}${}".format(
        ITERACOES, base64.b64encode(sal).decode("ascii"), base64.b64encode(chave).decode("ascii"))


@nativa("verificar_senha", retorna="booleano", assinatura="verificar_senha(senha, hash)")
def verificar_senha(vm, senha, guardado):
    """Verdadeiro se a senha corresponde ao hash gerado por hash_senha()."""
    exige_texto("verificar_senha", 1, senha)
    exige_texto("verificar_senha", 2, guardado)
    try:
        algoritmo, iteracoes, sal, chave = guardado.split("$")
        if algoritmo != "pbkdf2_sha256":
            return False
        calculado = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), base64.b64decode(sal), int(iteracoes))
        return hmac.compare_digest(calculado, base64.b64decode(chave))
    except (ValueError, binascii.Error):
        return False


@nativa("token_aleatório", retorna="texto", assinatura="token_aleatório([bytes])")
def token_aleatorio(vm, tamanho=32):
    """Texto aleatório e imprevisível (seguro para criptografia), bom para sessões e chaves de API."""
    exige_inteiro("token_aleatório", 1, tamanho)
    if not 8 <= tamanho <= 1024:
        raise erro("G322", "O tamanho do token deve estar entre 8 e 1024 bytes.")
    return secrets.token_urlsafe(tamanho)


@nativa("uuid", retorna="texto")
def uuid(vm):
    """Identificador único universal aleatório (UUID versão 4), como "1b4e28ba-2fa1-11d2-883f-0016d3cca427"."""
    return str(_uuid.uuid4())


@nativa("sha256", retorna="texto")
def sha256(vm, texto):
    """Resumo SHA-256 do texto, em hexadecimal. Não use para senhas: use hash_senha()."""
    return hashlib.sha256(exige_texto("sha256", 1, texto).encode("utf-8")).hexdigest()


@nativa("escapar_html", retorna="texto")
def escapar_html(vm, texto):
    """Troca < > & " ' por entidades HTML, para mostrar texto do usuário em páginas com segurança."""
    from ..runtime.values import display

    return html.escape(display(texto), quote=True)


@nativa("codificar_url", retorna="texto")
def codificar_url(vm, texto):
    """Codifica o texto para uso seguro dentro de uma URL (espaço vira %20, etc.)."""
    return quote(exige_texto("codificar_url", 1, texto), safe="")


@nativa("decodificar_url", retorna="texto")
def decodificar_url(vm, texto):
    """Desfaz a codificação de URL (%20 vira espaço, etc.)."""
    return unquote(exige_texto("decodificar_url", 1, texto))


@nativa("codificar_base64", retorna="texto")
def codificar_base64(vm, texto):
    """Codifica o texto (UTF-8) em Base64."""
    return base64.b64encode(exige_texto("codificar_base64", 1, texto).encode("utf-8")).decode("ascii")


@nativa("decodificar_base64", retorna="texto")
def decodificar_base64(vm, texto):
    """Decodifica um texto em Base64 de volta para texto UTF-8."""
    try:
        return base64.b64decode(exige_texto("decodificar_base64", 1, texto), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        raise erro("G312", "O texto não é um Base64 válido.")
