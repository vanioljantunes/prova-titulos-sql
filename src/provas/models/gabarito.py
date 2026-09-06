"""Schema de extração de documento de gabarito (preliminar/definitivo/retificação)."""

from pydantic import BaseModel, Field


class ItemGabarito(BaseModel):
    numero: int = Field(description="Número da questão.")
    letra: str | None = Field(
        default=None,
        description="Letra da resposta (A-E, V, F). Null se a questão foi anulada.",
    )
    anulada: bool = Field(default=False, description="True se o documento marca ANULADA.")
    justificativa: str | None = Field(
        default=None,
        description="Texto do parecer de anulação/alteração, quando presente no documento.",
    )
    trecho_fonte: str | None = None
    pagina: int | None = None


class GabaritoExtraido(BaseModel):
    itens: list[ItemGabarito]
    observacoes: str | None = Field(
        default=None, description="Notas gerais do documento (erratas, avisos)."
    )
