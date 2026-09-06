"""Identificador determinístico de questão: {SIGLA}-{ANO}[.{EDICAO}]-{NNN}.

Função pura, nunca gerada pelo modelo. A numeração canônica é a do caderno
tipo 1 (ou do gabarito oficial). Cadernos não mapeáveis → prova marcada como
caderno_nao_canonico e SEM identificadores.
"""

import re

REGEX_IDENTIFICADOR = re.compile(r"^[A-Z]{2,10}-\d{4}(\.\d+)?-\d{3}$")


def gerar_identificador(sigla: str, ano: int, numero: int, edicao: int = 1) -> str:
    if not re.fullmatch(r"[A-Z]{2,10}", sigla):
        raise ValueError(f"sigla inválida: {sigla!r} (esperado 2-10 maiúsculas)")
    if not 1900 <= ano <= 2200:
        raise ValueError(f"ano inválido: {ano}")
    if not 1 <= numero <= 999:
        raise ValueError(f"numero inválido: {numero} (esperado 1-999)")
    if edicao < 1:
        raise ValueError(f"edicao inválida: {edicao}")
    base = f"{sigla}-{ano}" if edicao == 1 else f"{sigla}-{ano}.{edicao}"
    return f"{base}-{numero:03d}"


def identificador_valido(identificador: str) -> bool:
    return REGEX_IDENTIFICADOR.fullmatch(identificador) is not None
