"""Utilitários de data/hora no fuso do atleta (America/Sao_Paulo).

O servidor roda em UTC; usar datetime.now()/date.today() direto faz o "hoje"
virar o dia seguinte a partir das 21h no horário de Brasília.
"""
from datetime import date, datetime

import pytz

TZ = pytz.timezone("America/Sao_Paulo")


def agora_local() -> datetime:
    return datetime.now(TZ)


def hoje_local() -> date:
    return agora_local().date()
