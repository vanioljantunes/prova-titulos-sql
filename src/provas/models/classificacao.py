"""Schema de classificação temática, restrito ao vocabulário controlado.

O schema é construído dinamicamente com os IDs válidos do edital vigente:
qualquer ID fora do vocabulário falha a validação Pydantic e o Instructor
força o modelo a corrigir. `null` com motivo tema_nao_mapeado é resposta
legítima — nunca inventar tema.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class ClassificacaoQuestao(BaseModel):
    tema_principal_id: int | None = Field(
        description=(
            "ID do tema principal, escolhido do vocabulário fornecido. "
            "Null APENAS se nenhum tema do vocabulário cobre a questão."
        )
    )
    motivo: Literal["tema_nao_mapeado"] | None = Field(
        default=None, description="Obrigatório quando tema_principal_id é null."
    )
    temas_secundarios_ids: list[int] = Field(
        default_factory=list,
        description="Outros temas do vocabulário que a questão toca (0 a 2).",
    )
    confianca: float = Field(ge=0.0, le=1.0)
    justificativa: str = Field(description="Uma frase justificando a escolha.")

    @model_validator(mode="after")
    def _nulo_exige_motivo(self) -> "ClassificacaoQuestao":
        if self.tema_principal_id is None and self.motivo is None:
            raise ValueError("tema_principal_id null exige motivo='tema_nao_mapeado'")
        if self.tema_principal_id is not None and self.motivo is not None:
            raise ValueError("motivo só é válido com tema_principal_id null")
        return self


def schema_para_vocabulario(ids_validos: set[int]) -> type[ClassificacaoQuestao]:
    """Subclasse com validação dos IDs contra o vocabulário do edital vigente."""

    class ClassificacaoRestrita(ClassificacaoQuestao):
        @field_validator("tema_principal_id")
        @classmethod
        def _principal_no_vocabulario(cls, v: int | None) -> int | None:
            if v is not None and v not in ids_validos:
                raise ValueError(
                    f"tema_principal_id {v} fora do vocabulário; use um ID listado ou null."
                )
            return v

        @field_validator("temas_secundarios_ids")
        @classmethod
        def _secundarios_no_vocabulario(cls, v: list[int]) -> list[int]:
            fora = [i for i in v if i not in ids_validos]
            if fora:
                raise ValueError(f"IDs fora do vocabulário: {fora}")
            return v

    return ClassificacaoRestrita
