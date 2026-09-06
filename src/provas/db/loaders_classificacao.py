"""Carga determinística da classificação temática em questao_tema."""

from datetime import UTC, datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session

from provas.db.tables import Questao, QuestaoTema, Validacao
from provas.models.classificacao import ClassificacaoQuestao

LIMIAR_REVISAO = 0.7


def aplicar_classificacao(
    session: Session,
    questao: Questao,
    resultado: ClassificacaoQuestao,
    *,
    modelo: str,
) -> None:
    """Substitui a classificação da questão (idempotente) e alimenta a fila de revisão."""
    agora = datetime.now(UTC).replace(tzinfo=None)
    session.execute(delete(QuestaoTema).where(QuestaoTema.questao_id == questao.id))

    if resultado.tema_principal_id is not None:
        session.add(
            QuestaoTema(
                questao_id=questao.id,
                tema_id=resultado.tema_principal_id,
                principal=True,
                confianca=resultado.confianca,
                classificado_em=agora,
                modelo=modelo,
            )
        )
        for tid in resultado.temas_secundarios_ids:
            if tid == resultado.tema_principal_id:
                continue
            session.add(
                QuestaoTema(
                    questao_id=questao.id,
                    tema_id=tid,
                    principal=False,
                    confianca=resultado.confianca,
                    classificado_em=agora,
                    modelo=modelo,
                )
            )

    if resultado.tema_principal_id is None:
        session.add(
            Validacao(
                tabela="questao",
                registro_id=questao.id,
                regra="tema_nao_mapeado",
                severidade="aviso",
                mensagem=(
                    f"{questao.identificador}: nenhum tema do vocabulário cobre a questão. "
                    f"Justificativa do modelo: {resultado.justificativa}"
                ),
            )
        )
    elif resultado.confianca < LIMIAR_REVISAO:
        session.add(
            Validacao(
                tabela="questao",
                registro_id=questao.id,
                regra="classificacao_baixa_confianca",
                severidade="aviso",
                mensagem=(
                    f"{questao.identificador}: confiança {resultado.confianca:.2f} < "
                    f"{LIMIAR_REVISAO}. Tema {resultado.tema_principal_id}: "
                    f"{resultado.justificativa}"
                ),
            )
        )
    session.flush()
