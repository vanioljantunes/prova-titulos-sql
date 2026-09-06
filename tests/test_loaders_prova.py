"""Marco 4: carga de questões — contexto dedupe, mídia, gabaritos nulos, proveniência."""

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from provas.db.fontes import registrar_arquivo_fonte
from provas.db.loaders_edital import RegistradorProveniencia
from provas.db.loaders_prova import FiguraDisponivel, carregar_questao, criar_prova
from provas.db.tables import Alternativa, Contexto, Prova, Proveniencia, QuestaoMidia, Sociedade
from provas.extraction.client import Prompt
from provas.models.comum import CampoTexto
from provas.models.prova import AlternativaExtraida, MidiaReferida, QuestaoExtraida
from provas.parsing.segmenter import SegmentoQuestao

PROMPT = Prompt(nome="questao_extracao", version="1", texto="teste")


def _extraida(
    numero: int, *, contexto: str | None = None, midias: list[MidiaReferida] | None = None
) -> QuestaoExtraida:
    ctx = (
        CampoTexto(valor=contexto, trecho_fonte=contexto[:50], pagina=1)
        if contexto
        else CampoTexto(valor=None, motivo_ausencia="nao_aplicavel")
    )
    return QuestaoExtraida(
        numero=numero,
        enunciado=CampoTexto(
            valor=f"Enunciado da questão {numero} com tamanho adequado.",
            trecho_fonte="Enunciado", pagina=1,
        ),
        contexto_compartilhado=ctx,
        contexto_tipo="caso_clinico" if contexto else None,
        alternativas=[
            AlternativaExtraida(letra=letra, texto=f"alternativa {letra}")
            for letra in "ABCD"
        ],
        midias=midias or [],
    )


def _setup(session: Session, tmp_path: Path) -> tuple[Prova, RegistradorProveniencia, str]:
    soc = Sociedade(sigla="SBC", nome="SBC", especialidade="cardiologia")
    session.add(soc)
    session.flush()
    pdf = tmp_path / "prova.pdf"
    pdf.write_bytes(b"%PDF-fake-prova")
    arq = registrar_arquivo_fonte(session, pdf, "prova", num_paginas=20)
    prova = criar_prova(
        session, sociedade=soc, arquivo_fonte=arq, ano=2024, num_questoes_declarado=2
    )
    prov = RegistradorProveniencia(session, arq, "claude-sonnet-5", PROMPT)
    return prova, prov, soc.sigla


def _seg(numero: int, p1: int = 1, p2: int = 1) -> SegmentoQuestao:
    return SegmentoQuestao(numero=numero, pagina_inicio=p1, pagina_fim=p2, texto="...")


def test_carga_basica_gabaritos_nulos(session: Session, tmp_path: Path) -> None:
    prova, prov, sigla = _setup(session, tmp_path)
    q = carregar_questao(
        session, prova=prova, sigla=sigla, extraida=_extraida(1), segmento=_seg(1),
        figuras=[], prov=prov, contextos_cache={},
    )
    assert q.identificador == "SBC-2024-001"
    assert q.gabarito_preliminar is None and q.gabarito_oficial is None
    assert q.status == "valida"
    alts = session.scalars(select(Alternativa).where(Alternativa.questao_id == q.id)).all()
    assert [a.letra for a in alts] == ["A", "B", "C", "D"]
    assert all(a.correta is False for a in alts)


def test_contexto_compartilhado_deduplicado(session: Session, tmp_path: Path) -> None:
    prova, prov, sigla = _setup(session, tmp_path)
    cache: dict[str, int] = {}
    caso = "Paciente de 70 anos com dispneia... responda às questões 1 e 2."
    q1 = carregar_questao(
        session, prova=prova, sigla=sigla, extraida=_extraida(1, contexto=caso),
        segmento=_seg(1), figuras=[], prov=prov, contextos_cache=cache,
    )
    q2 = carregar_questao(
        session, prova=prova, sigla=sigla, extraida=_extraida(2, contexto=caso),
        segmento=_seg(2), figuras=[], prov=prov, contextos_cache=cache,
    )
    assert q1.contexto_id == q2.contexto_id
    n_ctx = session.scalar(select(func.count()).select_from(Contexto))
    assert n_ctx == 1


def test_midia_associada_por_pagina(session: Session, tmp_path: Path) -> None:
    prova, prov, sigla = _setup(session, tmp_path)
    figuras = [
        FiguraDisponivel(ordem=1, pagina=1, bbox=[0, 0, 100, 100], caminho="pic_001.png"),
        FiguraDisponivel(ordem=2, pagina=9, bbox=None, caminho="pic_002.png"),
    ]
    midia = MidiaReferida(tipo="imagem", legenda="ECG", pagina=1, descricao="ECG 12 derivações")
    q = carregar_questao(
        session, prova=prova, sigla=sigla, extraida=_extraida(1, midias=[midia]),
        segmento=_seg(1), figuras=figuras, prov=prov, contextos_cache={},
    )
    midias = session.scalars(select(QuestaoMidia).where(QuestaoMidia.questao_id == q.id)).all()
    assert len(midias) == 1
    assert midias[0].caminho_arquivo == "pic_001.png"  # página 9 fora do span não entra
    assert figuras[0].usada and not figuras[1].usada


def test_proveniencia_gravada_para_campos(session: Session, tmp_path: Path) -> None:
    prova, prov, sigla = _setup(session, tmp_path)
    q = carregar_questao(
        session, prova=prova, sigla=sigla, extraida=_extraida(1), segmento=_seg(1),
        figuras=[], prov=prov, contextos_cache={},
    )
    n = session.scalar(
        select(func.count()).select_from(Proveniencia).where(
            Proveniencia.tabela == "questao", Proveniencia.registro_id == q.id
        )
    )
    assert n == 2  # enunciado + numero
    n_alt = session.scalar(
        select(func.count()).select_from(Proveniencia).where(
            Proveniencia.tabela == "alternativa"
        )
    )
    assert n_alt == 4
