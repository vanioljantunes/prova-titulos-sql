"""Marco 8: harness gold — métricas separadas por tipo de campo."""

from pathlib import Path

from sqlalchemy.orm import Session

from provas.db.fontes import registrar_arquivo_fonte
from provas.db.tables import Alternativa, Prova, Questao, Sociedade
from provas.validation.gold import avaliar


def _prova_com_questoes(session: Session, tmp_path: Path) -> Prova:
    soc = Sociedade(sigla="SBC", nome="SBC", especialidade="cardiologia")
    session.add(soc)
    session.flush()
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF-x")
    arq = registrar_arquivo_fonte(session, pdf, "prova")
    prova = Prova(sociedade_id=soc.id, arquivo_fonte_id=arq.id, ano=2024)
    session.add(prova)
    session.flush()
    q1 = Questao(
        prova_id=prova.id, identificador="SBC-2024-001", numero=1,
        enunciado="Paciente com dor torácica típica.", gabarito_oficial="B",
    )
    q2 = Questao(
        prova_id=prova.id, identificador="SBC-2024-002", numero=2,
        enunciado=None,  # omissão proposital
        gabarito_oficial="A",
    )
    session.add_all([q1, q2])
    session.flush()
    session.add_all([
        Alternativa(questao_id=q1.id, letra="A", texto="Aspirina."),
        Alternativa(questao_id=q1.id, letra="B", texto="Cateterismo imediato."),
        Alternativa(questao_id=q2.id, letra="A", texto="Texto errado extraído."),
    ])
    session.flush()
    return prova


GOLD = {
    "questoes": [
        {
            "numero": 1,
            "tipo": "multipla_escolha",
            "gabarito_oficial": "B",
            "enunciado": "Paciente com dor torácica típica.",
            "alternativas": [
                {"letra": "A", "texto": "Aspirina."},
                {"letra": "B", "texto": "Cateterismo imediato."},
            ],
            "num_midias": 0,
        },
        {
            "numero": 2,
            "tipo": "multipla_escolha",
            "gabarito_oficial": "C",  # extraído diz A → erro categórico
            "enunciado": "Enunciado que o parser omitiu.",  # omissão textual
            "alternativas": [{"letra": "A", "texto": "Texto certo do gold."}],  # erro textual
        },
        {"numero": 3, "enunciado": "Questão que a extração perdeu inteira."},
    ]
}


def test_metricas_separadas_por_tipo_de_campo(session: Session, tmp_path: Path) -> None:
    prova = _prova_com_questoes(session, tmp_path)
    rel = avaliar(session, prova.id, GOLD)
    d = rel.como_dict()

    assert d["questoes_gold"] == 3
    assert d["questoes_faltando"] == [3]

    presenca = d["estruturais"]["questao_presente"]
    assert presenca["total"] == 3
    assert presenca["taxa_omissao"] == round(1 / 3, 4)

    gab = d["categoricos"]["gabarito_oficial"]
    assert gab["total"] == 2
    assert gab["acuracia_exata"] == 0.5  # q1 acerta, q2 erra
    assert gab["taxa_erro"] == 0.5

    enun = d["textuais"]["enunciado"]
    assert enun["total"] == 2
    assert enun["taxa_omissao"] == 0.5  # q2 sem enunciado
    assert enun["acuracia_exata"] == 0.5

    alt = d["textuais"]["alternativa_texto"]
    assert alt["total"] == 3
    assert alt["acuracia_exata"] == round(2 / 3, 4)
    assert alt["taxa_erro"] == round(1 / 3, 4)

    n_alt = d["estruturais"]["num_alternativas"]
    assert n_alt["acuracia_exata"] == 1.0  # 2==2 e 1==1

    midias = d["estruturais"]["num_midias"]
    assert midias["total"] == 1 and midias["acuracia_exata"] == 1.0


def test_normalizacao_de_texto_tolerante_a_espacos_e_caixa(
    session: Session, tmp_path: Path
) -> None:
    prova = _prova_com_questoes(session, tmp_path)
    gold = {
        "questoes": [
            {"numero": 1, "enunciado": "  PACIENTE com dor  torácica típica. "},
        ]
    }
    rel = avaliar(session, prova.id, gold)
    assert rel.como_dict()["textuais"]["enunciado"]["acuracia_exata"] == 1.0
