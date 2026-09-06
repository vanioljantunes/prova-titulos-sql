"""Marco 1: o schema cria, aceita inserts com autoincremento e aplica os CHECKs."""

import pytest
from sqlalchemy import Engine, inspect
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from provas.db.tables import Alternativa, ArquivoFonte, Prova, Questao, Sociedade

TABELAS_ESPERADAS = {
    "sociedade", "arquivo_fonte", "edital", "edital_fase", "edital_cronograma",
    "tema", "edital_tema", "prova", "contexto", "questao", "alternativa",
    "questao_midia", "questao_tema", "proveniencia", "validacao",
}


def test_todas_as_tabelas_criadas(engine: Engine) -> None:
    assert set(inspect(engine).get_table_names()) >= TABELAS_ESPERADAS


def _prova_minima(session: Session) -> Prova:
    soc = Sociedade(sigla="SBC", nome="Sociedade Brasileira de Cardiologia",
                    especialidade="cardiologia")
    arq = ArquivoFonte(caminho="data/raw/x.pdf", hash_sha256="a" * 64, tipo="prova")
    session.add_all([soc, arq])
    session.flush()
    prova = Prova(sociedade_id=soc.id, arquivo_fonte_id=arq.id, ano=2024)
    session.add(prova)
    session.flush()
    return prova


def test_insert_autoincremento_e_defaults(session: Session) -> None:
    prova = _prova_minima(session)
    assert isinstance(prova.id, int)
    assert prova.status == "ingerida"
    assert prova.edicao == 1


def test_check_tipo_arquivo_fonte_rejeita_valor_invalido(session: Session) -> None:
    session.add(ArquivoFonte(caminho="x.pdf", hash_sha256="b" * 64, tipo="invalido"))
    with pytest.raises((IntegrityError, StatementError)):
        session.flush()


def test_hash_sha256_unico(session: Session) -> None:
    session.add(ArquivoFonte(caminho="1.pdf", hash_sha256="c" * 64, tipo="prova"))
    session.flush()
    session.add(ArquivoFonte(caminho="2.pdf", hash_sha256="c" * 64, tipo="prova"))
    with pytest.raises((IntegrityError, StatementError)):
        session.flush()


def test_alternativa_letra_unica_por_questao(session: Session) -> None:
    prova = _prova_minima(session)
    q = Questao(prova_id=prova.id, identificador="SBC-2024-001", numero=1,
                enunciado="Enunciado de teste com tamanho suficiente.")
    session.add(q)
    session.flush()
    session.add(Alternativa(questao_id=q.id, letra="A", texto="alt A"))
    session.flush()
    session.add(Alternativa(questao_id=q.id, letra="A", texto="alt A duplicada"))
    with pytest.raises((IntegrityError, StatementError)):
        session.flush()
