"""Modelo relacional completo (v1).

Convenções:
- snake_case em tudo; chaves substitutas inteiras via Sequence explícita
  (portável DuckDB ↔ PostgreSQL).
- Todo campo de negócio é anulável por princípio: omissão na fonte é um valor
  legítimo e deve ficar visível, nunca mascarada por defaults inventados.
- Enums de domínio são CHECK constraints (sem tipos nativos de enum, para
  portabilidade e migração não destrutiva).
- Nenhuma tabela ou coluna é específica de uma especialidade.
"""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Sequence,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from provas.db.base import Base


def _pk(table: str) -> Mapped[int]:
    return mapped_column(
        Integer, Sequence(f"seq_{table}_id"), primary_key=True, autoincrement=True
    )


# ---------------------------------------------------------------------------
# Fontes e organizações
# ---------------------------------------------------------------------------


class Sociedade(Base):
    """Sociedade emissora do título (SBC, SBCM, AMB...). Uma linha por sigla."""

    __tablename__ = "sociedade"

    id: Mapped[int] = _pk("sociedade")
    sigla: Mapped[str] = mapped_column(Text, unique=True)
    nome: Mapped[str | None] = mapped_column(Text)
    # string plana (ex.: 'cardiologia', 'clinica_medica'); casa com tema.especialidade,
    # permitindo que sociedades distintas compartilhem taxonomia
    especialidade: Mapped[str | None] = mapped_column(Text)


class ArquivoFonte(Base):
    """PDF original ingerido. hash_sha256 único garante idempotência da ingestão."""

    __tablename__ = "arquivo_fonte"
    __table_args__ = (
        CheckConstraint(
            "tipo IN ('edital','prova','gabarito_preliminar','gabarito_definitivo',"
            "'retificacao')",
            name="tipo",
        ),
    )

    id: Mapped[int] = _pk("arquivo_fonte")
    caminho: Mapped[str] = mapped_column(Text)
    hash_sha256: Mapped[str] = mapped_column(Text, unique=True)
    tipo: Mapped[str] = mapped_column(Text)
    num_paginas: Mapped[int | None] = mapped_column(Integer)
    ingerido_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ---------------------------------------------------------------------------
# Editais
# ---------------------------------------------------------------------------


class Edital(Base):
    """Documento normativo do concurso. Datas rotuladas extras vão em
    edital_cronograma (linhas), nunca viram coluna nova aqui."""

    __tablename__ = "edital"
    __table_args__ = (
        CheckConstraint(
            "modalidade IS NULL OR modalidade IN ('presencial','online','hibrida')",
            name="modalidade",
        ),
    )

    id: Mapped[int] = _pk("edital")
    sociedade_id: Mapped[int] = mapped_column(ForeignKey("sociedade.id"))
    arquivo_fonte_id: Mapped[int] = mapped_column(ForeignKey("arquivo_fonte.id"))
    ano: Mapped[int] = mapped_column(Integer)
    edicao: Mapped[int] = mapped_column(Integer, default=1)  # >1 se 2ª prova no ano
    titulo: Mapped[str | None] = mapped_column(Text)
    data_publicacao: Mapped[date | None] = mapped_column(Date)
    inscricao_abertura: Mapped[date | None] = mapped_column(Date)
    inscricao_encerramento: Mapped[date | None] = mapped_column(Date)
    taxa_valor: Mapped[float | None] = mapped_column(Float)
    data_prova: Mapped[date | None] = mapped_column(Date)
    local_prova: Mapped[str | None] = mapped_column(Text)
    modalidade: Mapped[str | None] = mapped_column(Text)
    num_questoes_previsto: Mapped[int | None] = mapped_column(Integer)
    nota_minima_aprovacao: Mapped[float | None] = mapped_column(Float)
    pre_requisitos: Mapped[str | None] = mapped_column(Text)
    bibliografia_recomendada: Mapped[str | None] = mapped_column(Text)
    observacoes: Mapped[str | None] = mapped_column(Text)
    # true apenas no edital mais recente por sociedade; fonte do vocabulário de temas
    vigente: Mapped[bool] = mapped_column(Boolean, default=False)


class EditalFase(Base):
    """Fase do certame (prova teórica, análise curricular, prova prática...)."""

    __tablename__ = "edital_fase"

    id: Mapped[int] = _pk("edital_fase")
    edital_id: Mapped[int] = mapped_column(ForeignKey("edital.id"))
    ordem: Mapped[int | None] = mapped_column(Integer)
    nome: Mapped[str] = mapped_column(Text)
    tipo: Mapped[str | None] = mapped_column(Text)
    peso: Mapped[float | None] = mapped_column(Float)
    data: Mapped[date | None] = mapped_column(Date)
    descricao: Mapped[str | None] = mapped_column(Text)


class EditalCronograma(Base):
    """Calendário genérico: toda data rotulada do edital vira uma linha aqui
    (recurso, gabarito preliminar, resultado final, isenção...)."""

    __tablename__ = "edital_cronograma"

    id: Mapped[int] = _pk("edital_cronograma")
    edital_id: Mapped[int] = mapped_column(ForeignKey("edital.id"))
    evento: Mapped[str] = mapped_column(Text)  # rótulo literal do edital
    data_inicio: Mapped[date | None] = mapped_column(Date)
    data_fim: Mapped[date | None] = mapped_column(Date)
    descricao: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------------------
# Taxonomia de temas
# ---------------------------------------------------------------------------


class Tema(Base):
    """Taxonomia canônica, estável entre edições. Hierarquia via parent_id
    (grande-área → tema → subtema). Nunca criada automaticamente pelo LLM."""

    __tablename__ = "tema"
    __table_args__ = (UniqueConstraint("especialidade", "slug", name="uq_tema_especialidade_slug"),)

    id: Mapped[int] = _pk("tema")
    especialidade: Mapped[str] = mapped_column(Text)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("tema.id"))
    nivel: Mapped[int | None] = mapped_column(Integer)
    codigo: Mapped[str | None] = mapped_column(Text)  # numeração original (ex.: '2.1.3')
    nome: Mapped[str] = mapped_column(Text)
    slug: Mapped[str] = mapped_column(Text)


class EditalTema(Base):
    """Ponte entre a redação literal do conteúdo programático de UM edital e o
    tema canônico. Renomeações entre edições geram nova linha aqui apontando
    para o mesmo tema_id — a série histórica não quebra."""

    __tablename__ = "edital_tema"

    id: Mapped[int] = _pk("edital_tema")
    edital_id: Mapped[int] = mapped_column(ForeignKey("edital.id"))
    tema_id: Mapped[int] = mapped_column(ForeignKey("tema.id"))
    texto_original: Mapped[str] = mapped_column(Text)
    ordem: Mapped[int | None] = mapped_column(Integer)


# ---------------------------------------------------------------------------
# Provas e questões
# ---------------------------------------------------------------------------


class Prova(Base):
    """Caderno de questões de uma edição. status controla o ciclo de vida;
    'caderno_nao_canonico' = numeração não mapeável ao caderno tipo 1 →
    identificadores não são gerados."""

    __tablename__ = "prova"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ingerida','gabarito_carregado','classificada','completa',"
            "'caderno_nao_canonico')",
            name="status",
        ),
    )

    id: Mapped[int] = _pk("prova")
    sociedade_id: Mapped[int] = mapped_column(ForeignKey("sociedade.id"))
    edital_id: Mapped[int | None] = mapped_column(ForeignKey("edital.id"))
    arquivo_fonte_id: Mapped[int] = mapped_column(ForeignKey("arquivo_fonte.id"))
    ano: Mapped[int] = mapped_column(Integer)
    edicao: Mapped[int] = mapped_column(Integer, default=1)
    tipo_caderno: Mapped[str | None] = mapped_column(Text)  # 'Tipo 1', 'Branco'...
    num_questoes_declarado: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text, default="ingerida")


class Contexto(Base):
    """Enunciado longo compartilhado por várias questões (caso clínico, texto
    base, tabela). 1:N com questao."""

    __tablename__ = "contexto"
    __table_args__ = (
        CheckConstraint("tipo IN ('caso_clinico','texto_base','tabela')", name="tipo"),
    )

    id: Mapped[int] = _pk("contexto")
    prova_id: Mapped[int] = mapped_column(ForeignKey("prova.id"))
    tipo: Mapped[str] = mapped_column(Text)
    texto: Mapped[str] = mapped_column(Text)


class Questao(Base):
    """Questão individual. identificador é derivado por função pura
    ({SIGLA}-{ANO}[.{EDICAO}]-{NNN}), nunca gerado pelo modelo. Gabaritos são
    nulos até a ingestão dos documentos de gabarito."""

    __tablename__ = "questao"
    __table_args__ = (
        CheckConstraint(
            "tipo IN ('multipla_escolha','discursiva','verdadeiro_falso')", name="tipo"
        ),
        CheckConstraint(
            "status IN ('valida','anulada','gabarito_alterado')", name="status"
        ),
    )

    id: Mapped[int] = _pk("questao")
    prova_id: Mapped[int] = mapped_column(ForeignKey("prova.id"))
    identificador: Mapped[str] = mapped_column(Text, unique=True)
    numero: Mapped[int] = mapped_column(Integer)  # numeração canônica (caderno tipo 1)
    contexto_id: Mapped[int | None] = mapped_column(ForeignKey("contexto.id"))
    enunciado: Mapped[str | None] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(Text, default="multipla_escolha")
    gabarito_preliminar: Mapped[str | None] = mapped_column(Text)  # char(1): A-E, V, F
    gabarito_oficial: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="valida")
    justificativa_alteracao: Mapped[str | None] = mapped_column(Text)
    revisada_por_humano: Mapped[bool] = mapped_column(Boolean, default=False)


class Alternativa(Base):
    """Alternativa de múltipla escolha. correta é preenchida na reconciliação
    do gabarito, nunca na extração da prova."""

    __tablename__ = "alternativa"
    __table_args__ = (UniqueConstraint("questao_id", "letra", name="uq_alternativa_questao_letra"),)

    id: Mapped[int] = _pk("alternativa")
    questao_id: Mapped[int] = mapped_column(ForeignKey("questao.id"))
    letra: Mapped[str] = mapped_column(Text)
    texto: Mapped[str | None] = mapped_column(Text)
    correta: Mapped[bool] = mapped_column(Boolean, default=False)


class QuestaoMidia(Base):
    """Mídia da questão (ECG, ecocardiograma, tabela, gráfico) recortada da
    página. Obrigatória para questões de imagem — sem ela o registro é inútil."""

    __tablename__ = "questao_midia"
    __table_args__ = (
        CheckConstraint("tipo IN ('imagem','tabela','grafico')", name="tipo"),
    )

    id: Mapped[int] = _pk("questao_midia")
    questao_id: Mapped[int] = mapped_column(ForeignKey("questao.id"))
    ordem: Mapped[int | None] = mapped_column(Integer)
    tipo: Mapped[str] = mapped_column(Text)
    caminho_arquivo: Mapped[str] = mapped_column(Text)  # relativo a data/interim/midia/
    legenda: Mapped[str | None] = mapped_column(Text)
    pagina: Mapped[int | None] = mapped_column(Integer)
    bbox: Mapped[str | None] = mapped_column(Text)  # JSON '[x0,y0,x1,y1]'


class QuestaoTema(Base):
    """Classificação temática N:N restrita ao vocabulário controlado do edital
    vigente. Exatamente uma linha principal=true por questão CLASSIFICADA
    (regra aplicada pela validação apenas após classificar-temas)."""

    __tablename__ = "questao_tema"
    __table_args__ = (
        UniqueConstraint("questao_id", "tema_id", name="uq_questao_tema_questao_tema"),
        CheckConstraint(
            "confianca IS NULL OR (confianca >= 0 AND confianca <= 1)", name="confianca"
        ),
    )

    id: Mapped[int] = _pk("questao_tema")
    questao_id: Mapped[int] = mapped_column(ForeignKey("questao.id"))
    tema_id: Mapped[int] = mapped_column(ForeignKey("tema.id"))
    principal: Mapped[bool] = mapped_column(Boolean, default=False)
    confianca: Mapped[float | None] = mapped_column(Float)
    classificado_em: Mapped[datetime | None] = mapped_column(DateTime)
    modelo: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------------------
# Auditoria
# ---------------------------------------------------------------------------


class Proveniencia(Base):
    """Procedência de cada campo extraído. Sem linha aqui, o dado não entra:
    página, recorte, trecho literal, modelo, versão do prompt e timestamp."""

    __tablename__ = "proveniencia"

    id: Mapped[int] = _pk("proveniencia")
    tabela: Mapped[str] = mapped_column(Text)
    registro_id: Mapped[int] = mapped_column(Integer)
    campo: Mapped[str] = mapped_column(Text)
    arquivo_fonte_id: Mapped[int] = mapped_column(ForeignKey("arquivo_fonte.id"))
    pagina: Mapped[int | None] = mapped_column(Integer)
    bbox: Mapped[str | None] = mapped_column(Text)
    trecho_fonte: Mapped[str | None] = mapped_column(Text)
    char_inicio: Mapped[int | None] = mapped_column(Integer)
    char_fim: Mapped[int | None] = mapped_column(Integer)
    modelo: Mapped[str | None] = mapped_column(Text)
    versao_prompt: Mapped[str | None] = mapped_column(Text)
    executado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    confianca: Mapped[float | None] = mapped_column(Float)


class Validacao(Base):
    """Fila de achados da camada de validação. severidade 'erro' bloqueia a
    prova de virar 'completa'; 'aviso' alimenta a revisão humana."""

    __tablename__ = "validacao"
    __table_args__ = (
        CheckConstraint("severidade IN ('erro','aviso')", name="severidade"),
    )

    id: Mapped[int] = _pk("validacao")
    tabela: Mapped[str] = mapped_column(Text)
    registro_id: Mapped[int | None] = mapped_column(Integer)
    regra: Mapped[str] = mapped_column(Text)
    severidade: Mapped[str] = mapped_column(Text)
    mensagem: Mapped[str | None] = mapped_column(Text)
    resolvido: Mapped[bool] = mapped_column(Boolean, default=False)
    resolvido_por: Mapped[str | None] = mapped_column(Text)
    resolvido_em: Mapped[datetime | None] = mapped_column(DateTime)
