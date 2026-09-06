"""Marco 5: reconciliação de gabarito — preliminar, definitivo, anulada, alterada."""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from provas.db.fontes import registrar_arquivo_fonte
from provas.db.loaders_edital import RegistradorProveniencia
from provas.db.loaders_gabarito import reconciliar_gabarito
from provas.db.tables import Alternativa, Prova, Questao, Sociedade, Validacao
from provas.extraction.client import Prompt
from provas.models.gabarito import GabaritoExtraido, ItemGabarito

PROMPT = Prompt(nome="gabarito_extracao", version="1", texto="teste")


def _setup(
    session: Session, tmp_path: Path, n_questoes: int = 3
) -> tuple[Prova, RegistradorProveniencia]:
    soc = Sociedade(sigla="SBC", nome="SBC", especialidade="cardiologia")
    session.add(soc)
    session.flush()
    pdf = tmp_path / "gab.pdf"
    pdf.write_bytes(b"%PDF-gab")
    arq = registrar_arquivo_fonte(session, pdf, "gabarito_definitivo")
    prova = Prova(
        sociedade_id=soc.id, arquivo_fonte_id=arq.id, ano=2024,
        num_questoes_declarado=n_questoes, status="ingerida",
    )
    session.add(prova)
    session.flush()
    for n in range(1, n_questoes + 1):
        q = Questao(
            prova_id=prova.id, identificador=f"SBC-2024-{n:03d}", numero=n,
            enunciado=f"Enunciado {n} suficientemente longo para os testes.",
        )
        session.add(q)
        session.flush()
        for letra in "ABCD":
            session.add(Alternativa(questao_id=q.id, letra=letra, texto=f"alt {letra}"))
    session.flush()
    return prova, RegistradorProveniencia(session, arq, "claude-sonnet-5", PROMPT)


def _q(session: Session, prova: Prova, numero: int) -> Questao:
    q = session.scalar(
        select(Questao).where(Questao.prova_id == prova.id, Questao.numero == numero)
    )
    assert q is not None
    return q


def test_preliminar_preenche_somente_preliminar(session: Session, tmp_path: Path) -> None:
    prova, prov = _setup(session, tmp_path)
    gab = GabaritoExtraido(itens=[ItemGabarito(numero=1, letra="A")])
    reconciliar_gabarito(session, prova=prova, gabarito=gab, tipo="preliminar", prov=prov)
    q = _q(session, prova, 1)
    assert q.gabarito_preliminar == "A"
    assert q.gabarito_oficial is None
    assert prova.status == "ingerida"  # preliminar não muda status da prova


def test_definitivo_marca_correta_e_status(session: Session, tmp_path: Path) -> None:
    prova, prov = _setup(session, tmp_path)
    gab_p = GabaritoExtraido(itens=[ItemGabarito(numero=1, letra="B")])
    reconciliar_gabarito(session, prova=prova, gabarito=gab_p, tipo="preliminar", prov=prov)
    gab_d = GabaritoExtraido(itens=[ItemGabarito(numero=1, letra="B")])
    res = reconciliar_gabarito(session, prova=prova, gabarito=gab_d, tipo="definitivo", prov=prov)
    q = _q(session, prova, 1)
    assert q.gabarito_oficial == "B" and q.status == "valida"
    corretas = session.scalars(
        select(Alternativa).where(Alternativa.questao_id == q.id, Alternativa.correta)
    ).all()
    assert [a.letra for a in corretas] == ["B"]
    assert res.alteradas == 0
    assert prova.status == "gabarito_carregado"


def test_anulada_gabarito_oficial_nulo(session: Session, tmp_path: Path) -> None:
    prova, prov = _setup(session, tmp_path)
    gab = GabaritoExtraido(
        itens=[ItemGabarito(numero=2, anulada=True, justificativa="Duas respostas corretas.")]
    )
    reconciliar_gabarito(session, prova=prova, gabarito=gab, tipo="definitivo", prov=prov)
    q = _q(session, prova, 2)
    assert q.status == "anulada"
    assert q.gabarito_oficial is None
    assert q.justificativa_alteracao == "Duas respostas corretas."
    corretas = session.scalars(
        select(Alternativa).where(Alternativa.questao_id == q.id, Alternativa.correta)
    ).all()
    assert corretas == []


def test_alteracao_preliminar_diferente_do_definitivo(session: Session, tmp_path: Path) -> None:
    prova, prov = _setup(session, tmp_path)
    reconciliar_gabarito(
        session, prova=prova,
        gabarito=GabaritoExtraido(itens=[ItemGabarito(numero=1, letra="A")]),
        tipo="preliminar", prov=prov,
    )
    res = reconciliar_gabarito(
        session, prova=prova,
        gabarito=GabaritoExtraido(
            itens=[ItemGabarito(numero=1, letra="C", justificativa="Recurso deferido.")]
        ),
        tipo="definitivo", prov=prov,
    )
    q = _q(session, prova, 1)
    assert q.status == "gabarito_alterado"
    assert q.gabarito_preliminar == "A" and q.gabarito_oficial == "C"
    assert q.justificativa_alteracao == "Recurso deferido."
    assert res.alteradas == 1
    corretas = session.scalars(
        select(Alternativa).where(Alternativa.questao_id == q.id, Alternativa.correta)
    ).all()
    assert [a.letra for a in corretas] == ["C"]


def test_divergencias_registradas_em_validacao(session: Session, tmp_path: Path) -> None:
    prova, prov = _setup(session, tmp_path, n_questoes=2)
    gab = GabaritoExtraido(
        itens=[ItemGabarito(numero=1, letra="A"), ItemGabarito(numero=99, letra="D")]
    )
    res = reconciliar_gabarito(session, prova=prova, gabarito=gab, tipo="definitivo", prov=prov)
    assert res.sem_questao_na_prova == [99]
    assert res.sem_item_no_gabarito == [2]
    regras = {
        v.regra
        for v in session.scalars(select(Validacao).where(Validacao.resolvido.is_(False)))
    }
    assert {"gabarito_sem_questao", "questao_sem_item_no_gabarito"} <= regras
