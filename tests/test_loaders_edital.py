"""Marco 3: carga determinística de edital, proveniência, vigência e aprovação de temas."""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from provas.db.fontes import registrar_arquivo_fonte
from provas.db.loaders_edital import (
    RegistradorProveniencia,
    atualizar_vigencia,
    carregar_edital,
    carregar_reconciliacao,
    temas_canonicos,
)
from provas.db.tables import (
    Edital,
    EditalCronograma,
    EditalTema,
    Proveniencia,
    Sociedade,
    Tema,
    Validacao,
)
from provas.db.temas import aprovar_propostas, propostas_pendentes
from provas.extraction.client import Prompt
from provas.extraction.reconcile import reconciliar
from provas.models.comum import CampoData, CampoInteiro, CampoNumero, CampoTexto
from provas.models.edital import (
    EditalMetadados,
    EventoCronograma,
    FaseExtraida,
    TemaExtraido,
)

PROMPT = Prompt(nome="edital_metadados", version="1", texto="teste")


def _campo_texto(valor: str | None, trecho: str | None = None) -> CampoTexto:
    if valor is None:
        return CampoTexto(valor=None, motivo_ausencia="nao_consta")
    return CampoTexto(valor=valor, trecho_fonte=trecho or valor, pagina=1)


def _meta(ano: int = 2026) -> EditalMetadados:
    ausente_data = CampoData(valor=None, motivo_ausencia="nao_consta")
    ausente_num = CampoNumero(valor=None, motivo_ausencia="nao_consta")
    return EditalMetadados(
        titulo=_campo_texto(f"Edital TEC {ano}"),
        ano=CampoInteiro(valor=ano, trecho_fonte=str(ano), pagina=1),
        data_publicacao=CampoData(valor=date(ano, 6, 9), trecho_fonte="09/06", pagina=1),
        inscricao_abertura=ausente_data,
        inscricao_encerramento=ausente_data,
        taxa_valor=CampoNumero(valor=2178.0, trecho_fonte="R$ 2.178,00", pagina=12),
        data_prova=CampoData(valor=date(ano, 12, 6), trecho_fonte="06 de dezembro", pagina=2),
        local_prova=_campo_texto(None),
        modalidade=_campo_texto("online"),
        num_questoes_previsto=CampoInteiro(valor=100, trecho_fonte="100 questões", pagina=3),
        nota_minima_aprovacao=ausente_num,
        pre_requisitos=_campo_texto(None),
        bibliografia_recomendada=_campo_texto(None),
        observacoes=_campo_texto(None),
        fases=[
            FaseExtraida(
                ordem=1, nome="Prova teórica",
                data=CampoData(valor=date(ano, 12, 6), trecho_fonte="06/12", pagina=2),
            )
        ],
        cronograma=[
            EventoCronograma(
                evento="Encerramento das inscrições",
                data_inicio=CampoData(valor=date(ano, 7, 9), trecho_fonte="09/07", pagina=2),
                data_fim=CampoData(valor=None, motivo_ausencia="nao_aplicavel"),
            )
        ],
    )


def _setup(session: Session, tmp_path: object, ano: int = 2026) -> tuple[Sociedade, Edital]:
    from pathlib import Path

    soc = session.scalar(select(Sociedade).where(Sociedade.sigla == "SBC"))
    if soc is None:
        soc = Sociedade(sigla="SBC", nome="SBC", especialidade="cardiologia")
        session.add(soc)
        session.flush()
    pdf = Path(str(tmp_path)) / f"edital{ano}.pdf"
    pdf.write_bytes(f"%PDF-fake-{ano}".encode())
    arq = registrar_arquivo_fonte(session, pdf, "edital", num_paginas=30)
    prov = RegistradorProveniencia(session, arq, "claude-sonnet-5", PROMPT)
    edital = carregar_edital(
        session, sociedade=soc, arquivo_fonte=arq, meta=_meta(ano), prov=prov
    )
    return soc, edital


def test_carga_completa_com_proveniencia(session: Session, tmp_path: object) -> None:
    _, edital = _setup(session, tmp_path)
    assert edital.ano == 2026
    assert edital.taxa_valor == 2178.0
    assert edital.local_prova is None  # nulo explícito preservado

    # todo campo de edital tem proveniência (14 campos) + fase + cronograma
    n_edital = session.scalar(
        select(func.count()).select_from(Proveniencia).where(
            Proveniencia.tabela == "edital", Proveniencia.registro_id == edital.id
        )
    )
    assert n_edital == 14
    cron = session.scalars(
        select(EditalCronograma).where(EditalCronograma.edital_id == edital.id)
    ).all()
    assert len(cron) == 1 and cron[0].evento == "Encerramento das inscrições"


def test_vigencia_apenas_no_mais_recente(session: Session, tmp_path: object) -> None:
    soc, e1 = _setup(session, tmp_path, ano=2025)
    _, e2 = _setup(session, tmp_path, ano=2026)
    atualizar_vigencia(session, soc.id)
    assert session.get(Edital, e2.id).vigente is True  # type: ignore[union-attr]
    assert session.get(Edital, e1.id).vigente is False  # type: ignore[union-attr]


def test_reconciliacao_propoe_e_aprovacao_cria_hierarquia(
    session: Session, tmp_path: object
) -> None:
    _soc, edital = _setup(session, tmp_path)
    extraidos = [
        TemaExtraido(codigo="1", texto_original="Insuficiência Cardíaca", nivel=1, ordem=1),
        TemaExtraido(
            codigo="1.1", texto_original="IC de fração reduzida", nivel=2,
            parent_codigo="1", ordem=2,
        ),
    ]
    casados, propostas = reconciliar(extraidos, temas_canonicos(session, "cardiologia"))
    assert not casados and len(propostas) == 2
    from provas.db.tables import ArquivoFonte

    arq = session.get_one(ArquivoFonte, edital.arquivo_fonte_id)
    prov = RegistradorProveniencia(session, arq, "claude-sonnet-5", PROMPT)
    carregar_reconciliacao(
        session, edital=edital, especialidade="cardiologia",
        casados=casados, propostas=propostas, prov=prov,
    )

    pendentes = propostas_pendentes(session, edital.id)
    assert len(pendentes) == 2
    criados = aprovar_propostas(session, pendentes)
    assert len(criados) == 2
    filho = session.scalar(select(Tema).where(Tema.slug == "ic-de-fracao-reduzida"))
    pai = session.scalar(select(Tema).where(Tema.slug == "insuficiencia-cardiaca"))
    assert filho is not None and pai is not None and filho.parent_id == pai.id

    # edital_tema criada para ambos; validações fechadas
    n_et = session.scalar(
        select(func.count()).select_from(EditalTema).where(EditalTema.edital_id == edital.id)
    )
    assert n_et == 2
    abertas = session.scalars(select(Validacao).where(Validacao.resolvido.is_(False))).all()
    assert abertas == []


def test_segundo_edital_renomeacao_casa_no_mesmo_tema(
    session: Session, tmp_path: object
) -> None:
    _soc, e1 = _setup(session, tmp_path, ano=2025)
    ext1 = [TemaExtraido(texto_original="Arritmias cardíacas", nivel=1, ordem=1)]
    _, props = reconciliar(ext1, temas_canonicos(session, "cardiologia"))
    from provas.db.tables import ArquivoFonte

    arq = session.get_one(ArquivoFonte, e1.arquivo_fonte_id)
    prov = RegistradorProveniencia(session, arq, "claude-sonnet-5", PROMPT)
    carregar_reconciliacao(
        session, edital=e1, especialidade="cardiologia", casados=[], propostas=props, prov=prov
    )
    aprovar_propostas(session, propostas_pendentes(session, e1.id))
    tema_id = session.scalar(select(Tema.id).where(Tema.slug == "arritmias-cardiacas"))

    _setup(session, tmp_path, ano=2026)
    ext2 = [TemaExtraido(texto_original="Arritmia cardíaca", nivel=1, ordem=1)]
    casados, props2 = reconciliar(ext2, temas_canonicos(session, "cardiologia"))
    assert len(casados) == 1 and not props2
    assert casados[0].tema_id == tema_id  # série histórica preservada
