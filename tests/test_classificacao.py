"""Marco 6: schema restrito ao vocabulário + carga de questao_tema + fila de revisão."""

from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from provas.db.fontes import registrar_arquivo_fonte
from provas.db.loaders_classificacao import aplicar_classificacao
from provas.db.tables import Prova, Questao, QuestaoTema, Sociedade, Tema, Validacao
from provas.models.classificacao import ClassificacaoQuestao, schema_para_vocabulario


def test_schema_rejeita_id_fora_do_vocabulario() -> None:
    schema = schema_para_vocabulario({1, 2, 3})
    with pytest.raises(ValidationError, match="fora do vocabulário"):
        schema(tema_principal_id=99, confianca=0.9, justificativa="x")
    with pytest.raises(ValidationError, match="fora do vocabulário"):
        schema(
            tema_principal_id=1, temas_secundarios_ids=[7],
            confianca=0.9, justificativa="x",
        )


def test_schema_aceita_null_com_motivo() -> None:
    schema = schema_para_vocabulario({1})
    ok = schema(
        tema_principal_id=None, motivo="tema_nao_mapeado", confianca=0.4, justificativa="x"
    )
    assert ok.tema_principal_id is None


def test_null_sem_motivo_rejeitado() -> None:
    with pytest.raises(ValidationError, match="motivo"):
        ClassificacaoQuestao(tema_principal_id=None, confianca=0.5, justificativa="x")


def _questao(session: Session, tmp_path: Path) -> tuple[Questao, list[Tema]]:
    soc = Sociedade(sigla="SBC", nome="SBC", especialidade="cardiologia")
    session.add(soc)
    session.flush()
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF-x")
    arq = registrar_arquivo_fonte(session, pdf, "prova")
    prova = Prova(sociedade_id=soc.id, arquivo_fonte_id=arq.id, ano=2024)
    session.add(prova)
    session.flush()
    q = Questao(
        prova_id=prova.id, identificador="SBC-2024-001", numero=1,
        enunciado="Enunciado suficientemente longo para o teste.",
    )
    temas = [
        Tema(especialidade="cardiologia", nivel=1, nome=f"Tema {i}", slug=f"tema-{i}")
        for i in (1, 2)
    ]
    session.add_all([q, *temas])
    session.flush()
    return q, temas


def test_aplicar_classificacao_principal_e_secundario(session: Session, tmp_path: Path) -> None:
    q, temas = _questao(session, tmp_path)
    r = ClassificacaoQuestao(
        tema_principal_id=temas[0].id, temas_secundarios_ids=[temas[1].id],
        confianca=0.95, justificativa="Encaixe claro.",
    )
    aplicar_classificacao(session, q, r, modelo="claude-sonnet-5")
    linhas = session.scalars(
        select(QuestaoTema).where(QuestaoTema.questao_id == q.id)
    ).all()
    principais = [x for x in linhas if x.principal]
    assert len(linhas) == 2 and len(principais) == 1
    assert principais[0].tema_id == temas[0].id
    assert principais[0].modelo == "claude-sonnet-5"


def test_reclassificar_e_idempotente(session: Session, tmp_path: Path) -> None:
    q, temas = _questao(session, tmp_path)
    r1 = ClassificacaoQuestao(
        tema_principal_id=temas[0].id, confianca=0.9, justificativa="a"
    )
    r2 = ClassificacaoQuestao(
        tema_principal_id=temas[1].id, confianca=0.9, justificativa="b"
    )
    aplicar_classificacao(session, q, r1, modelo="m")
    aplicar_classificacao(session, q, r2, modelo="m")
    linhas = session.scalars(select(QuestaoTema).where(QuestaoTema.questao_id == q.id)).all()
    assert len(linhas) == 1 and linhas[0].tema_id == temas[1].id


def test_nao_mapeado_vai_para_fila(session: Session, tmp_path: Path) -> None:
    q, _ = _questao(session, tmp_path)
    r = ClassificacaoQuestao(
        tema_principal_id=None, motivo="tema_nao_mapeado",
        confianca=0.3, justificativa="Nada cobre.",
    )
    aplicar_classificacao(session, q, r, modelo="m")
    assert session.scalars(select(QuestaoTema)).all() == []
    fila = session.scalars(
        select(Validacao).where(Validacao.regra == "tema_nao_mapeado")
    ).all()
    assert len(fila) == 1 and fila[0].registro_id == q.id


def test_baixa_confianca_vai_para_fila(session: Session, tmp_path: Path) -> None:
    q, temas = _questao(session, tmp_path)
    r = ClassificacaoQuestao(
        tema_principal_id=temas[0].id, confianca=0.5, justificativa="Duvidoso."
    )
    aplicar_classificacao(session, q, r, modelo="m")
    fila = session.scalars(
        select(Validacao).where(Validacao.regra == "classificacao_baixa_confianca")
    ).all()
    assert len(fila) == 1
