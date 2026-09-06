"""Schemas de extração de edital: (a) metadados+calendário, (b) conteúdo programático.

Duas tarefas cognitivamente distintas → dois schemas, duas chamadas.
"""

from typing import Literal

from pydantic import BaseModel, Field

from provas.models.comum import CampoData, CampoInteiro, CampoNumero, CampoTexto


class FaseExtraida(BaseModel):
    """Uma fase do certame (prova teórica objetiva, análise curricular, prova prática...)."""

    ordem: int | None = None
    nome: str
    tipo: str | None = Field(default=None, description="ex.: teorica, curricular, pratica")
    peso: float | None = None
    data: CampoData
    descricao: str | None = None
    trecho_fonte: str | None = None
    pagina: int | None = None


class EventoCronograma(BaseModel):
    """Qualquer data rotulada do edital. O rótulo deve ser o texto LITERAL."""

    evento: str = Field(description="Rótulo literal do edital para esta data.")
    data_inicio: CampoData
    data_fim: CampoData
    descricao: str | None = None
    pagina: int | None = None


class EditalMetadados(BaseModel):
    """Chamada (a): metadados e calendário do edital."""

    titulo: CampoTexto
    ano: CampoInteiro
    data_publicacao: CampoData
    inscricao_abertura: CampoData
    inscricao_encerramento: CampoData
    taxa_valor: CampoNumero = Field(
        description="Menor taxa de inscrição em reais (categoria mais barata), se houver várias."
    )
    data_prova: CampoData
    local_prova: CampoTexto
    modalidade: CampoTexto = Field(description="presencial, online ou hibrida")
    num_questoes_previsto: CampoInteiro
    nota_minima_aprovacao: CampoNumero
    pre_requisitos: CampoTexto
    bibliografia_recomendada: CampoTexto
    observacoes: CampoTexto
    fases: list[FaseExtraida]
    cronograma: list[EventoCronograma]


class TemaExtraido(BaseModel):
    """Item do conteúdo programático, com a redação e a numeração LITERAIS do edital."""

    codigo: str | None = Field(
        default=None, description="Numeração original do edital (ex.: '2.1.3'), se existir."
    )
    texto_original: str = Field(description="Redação literal do item no edital.")
    nivel: int = Field(description="1 = grande área; 2 = tema; 3 = subtema...")
    parent_codigo: str | None = Field(
        default=None, description="Código do item pai na hierarquia, se houver."
    )
    ordem: int
    pagina: int | None = None


class ConteudoProgramatico(BaseModel):
    """Chamada (b): lista hierárquica do conteúdo programático."""

    presente: bool = Field(description="False se o edital não traz conteúdo programático.")
    motivo_ausencia: Literal["nao_consta", "ilegivel"] | None = None
    temas: list[TemaExtraido]
