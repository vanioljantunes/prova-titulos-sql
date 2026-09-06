"""Reconciliação determinística de gabarito com as questões da prova.

- preliminar → preenche gabarito_preliminar
- definitivo → preenche gabarito_oficial, resolve status e alternativa.correta:
    anulada            → status='anulada', gabarito_oficial=NULL
    preliminar≠oficial → status='gabarito_alterado' (+ justificativa)
"""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from provas.db.loaders_edital import RegistradorProveniencia
from provas.db.tables import Alternativa, Prova, Questao, Validacao
from provas.models.gabarito import GabaritoExtraido, ItemGabarito


@dataclass
class ResultadoReconciliacao:
    aplicados: int = 0
    anuladas: int = 0
    alteradas: int = 0
    sem_questao_na_prova: list[int] = field(default_factory=list)
    sem_item_no_gabarito: list[int] = field(default_factory=list)


def _aplicar_definitivo(
    session: Session, questao: Questao, item: ItemGabarito, res: ResultadoReconciliacao
) -> None:
    if item.anulada:
        questao.status = "anulada"
        questao.gabarito_oficial = None
        if item.justificativa:
            questao.justificativa_alteracao = item.justificativa
        res.anuladas += 1
    else:
        letra = (item.letra or "").upper() or None
        questao.gabarito_oficial = letra
        if questao.gabarito_preliminar is not None and questao.gabarito_preliminar != letra:
            questao.status = "gabarito_alterado"
            if item.justificativa:
                questao.justificativa_alteracao = item.justificativa
            res.alteradas += 1
        elif questao.status != "anulada":
            questao.status = "valida"

    # alternativa.correta espelha o gabarito oficial
    alternativas = session.scalars(
        select(Alternativa).where(Alternativa.questao_id == questao.id)
    ).all()
    for alt in alternativas:
        alt.correta = (
            questao.gabarito_oficial is not None and alt.letra == questao.gabarito_oficial
        )


def reconciliar_gabarito(
    session: Session,
    *,
    prova: Prova,
    gabarito: GabaritoExtraido,
    tipo: str,
    prov: RegistradorProveniencia,
) -> ResultadoReconciliacao:
    if tipo not in ("preliminar", "definitivo"):
        raise ValueError(f"tipo inválido: {tipo!r} (esperado preliminar|definitivo)")

    questoes = {
        q.numero: q
        for q in session.scalars(select(Questao).where(Questao.prova_id == prova.id))
    }
    res = ResultadoReconciliacao()
    numeros_gabarito: set[int] = set()

    for item in gabarito.itens:
        numeros_gabarito.add(item.numero)
        questao = questoes.get(item.numero)
        if questao is None:
            res.sem_questao_na_prova.append(item.numero)
            session.add(
                Validacao(
                    tabela="questao",
                    registro_id=None,
                    regra="gabarito_sem_questao",
                    severidade="aviso",
                    mensagem=(
                        f"Gabarito ({tipo}) traz questão {item.numero} "
                        f"inexistente na prova id={prova.id}."
                    ),
                )
            )
            continue

        if tipo == "preliminar":
            questao.gabarito_preliminar = (
                None if item.anulada else ((item.letra or "").upper() or None)
            )
            campo = "gabarito_preliminar"
        else:
            _aplicar_definitivo(session, questao, item, res)
            campo = "gabarito_oficial"

        prov.campo(
            "questao", questao.id, campo,
            trecho=item.trecho_fonte or item.letra, pagina=item.pagina,
        )
        res.aplicados += 1

    res.sem_item_no_gabarito = sorted(set(questoes) - numeros_gabarito)
    for numero in res.sem_item_no_gabarito:
        session.add(
            Validacao(
                tabela="questao",
                registro_id=questoes[numero].id,
                regra="questao_sem_item_no_gabarito",
                severidade="aviso",
                mensagem=f"Questão {numero} da prova id={prova.id} ausente do gabarito {tipo}.",
            )
        )

    if tipo == "definitivo" and prova.status == "ingerida":
        prova.status = "gabarito_carregado"
    session.flush()
    return res
