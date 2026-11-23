"""Data, hora e tempo."""

from __future__ import annotations

import datetime
import time

from ..runtime.values import GaloMapa
from ._util import erro, exige_numero
from .registry import nativa

DIAS = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo")


@nativa("agora", retorna="mapa")
def agora(vm):
    """Mapa com a data e a hora atuais: ano, mês, dia, hora, minuto, segundo e dia_da_semana."""
    d = datetime.datetime.now()
    return GaloMapa.from_pairs([
        ("ano", d.year), ("mês", d.month), ("dia", d.day),
        ("hora", d.hour), ("minuto", d.minute), ("segundo", d.second),
        ("dia_da_semana", DIAS[d.weekday()]),
    ])


@nativa("data_atual", retorna="texto")
def data_atual(vm):
    """Data de hoje no formato DD/MM/AAAA."""
    return datetime.date.today().strftime("%d/%m/%Y")


@nativa("hora_atual", retorna="texto")
def hora_atual(vm):
    """Hora atual no formato HH:MM:SS."""
    return datetime.datetime.now().strftime("%H:%M:%S")


@nativa("tempo", retorna="decimal")
def tempo(vm):
    """Segundos decorridos desde 01/01/1970 (útil para medir durações)."""
    return time.time()


@nativa("espere", retorna="nulo")
def espere(vm, segundos):
    """Pausa o programa pela quantidade de segundos indicada."""
    exige_numero("espere", 1, segundos)
    if segundos < 0:
        raise erro("G322", "A função espere() não aceita tempo negativo.")
    vm.flush()
    time.sleep(segundos)
    return None


@nativa("data_hora_iso", retorna="texto", assinatura="data_hora_iso([segundos])")
def data_hora_iso(vm, segundos=None):
    """Data e hora no padrão ISO 8601 (2026-11-22T18:30:00), boa para guardar em bancos e APIs.
    Sem argumento usa o momento atual; com `segundos` (como os de tempo()) converte aquele instante."""
    if segundos is None:
        d = datetime.datetime.now()
    else:
        exige_numero("data_hora_iso", 1, segundos)
        d = datetime.datetime.fromtimestamp(segundos)
    return d.replace(microsecond=0).isoformat()
