"""Blocos Pydantic compartilhados por todos os schemas de extração.

Princípio: nulo é legítimo e explícito. Todo campo extraído carrega valor OU
motivo_ausencia, mais a procedência mínima (trecho literal + página) exigida
para o dado entrar no banco.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

MotivoAusencia = Literal["nao_consta", "ilegivel", "nao_aplicavel"]


class _CampoBase(BaseModel):
    """Base de campo extraído com procedência embutida."""

    motivo_ausencia: MotivoAusencia | None = Field(
        default=None,
        description="Obrigatório quando valor é null: por que o dado está ausente.",
    )
    trecho_fonte: str | None = Field(
        default=None,
        description="Trecho LITERAL do documento de onde o valor foi lido. Null só se valor null.",
    )
    pagina: int | None = Field(default=None, description="Página (1-based) do trecho_fonte.")

    @model_validator(mode="after")
    def _valor_ou_motivo(self) -> "_CampoBase":
        valor = getattr(self, "valor", None)
        if valor is None and self.motivo_ausencia is None:
            raise ValueError("campo sem valor exige motivo_ausencia")
        if valor is not None and self.motivo_ausencia is not None:
            raise ValueError("campo com valor não pode ter motivo_ausencia")
        return self


class CampoTexto(_CampoBase):
    valor: str | None = None


class CampoData(_CampoBase):
    valor: date | None = None


class CampoNumero(_CampoBase):
    valor: float | None = None


class CampoInteiro(_CampoBase):
    valor: int | None = None
