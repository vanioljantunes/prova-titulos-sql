"""Schema de extração de UMA questão (chamada multimodal individual)."""

from typing import Literal

from pydantic import BaseModel, Field

from provas.models.comum import CampoTexto, MotivoAusencia


class AlternativaExtraida(BaseModel):
    letra: str = Field(description="Letra da alternativa (A, B, C, D, E).")
    texto: str | None = None
    motivo_ausencia: MotivoAusencia | None = Field(
        default=None, description="Preencher se o texto da alternativa não for legível."
    )


class MidiaReferida(BaseModel):
    """Mídia que a questão referencia (ECG, imagem, tabela, gráfico)."""

    tipo: Literal["imagem", "tabela", "grafico"]
    legenda: str | None = None
    pagina: int | None = Field(default=None, description="Página onde a mídia aparece.")
    descricao: str | None = Field(
        default=None, description="Descrição curta do conteúdo visual (ex.: 'ECG 12 derivações')."
    )


class QuestaoExtraida(BaseModel):
    numero: int = Field(description="Número da questão no caderno.")
    tipo: Literal["multipla_escolha", "discursiva", "verdadeiro_falso"] = "multipla_escolha"
    enunciado: CampoTexto
    contexto_compartilhado: CampoTexto = Field(
        description=(
            "Texto-base/caso clínico compartilhado com outras questões "
            "('Considerando o caso acima...'). Null com nao_aplicavel se a questão é autônoma."
        )
    )
    contexto_tipo: Literal["caso_clinico", "texto_base", "tabela"] | None = None
    alternativas: list[AlternativaExtraida]
    midias: list[MidiaReferida]
