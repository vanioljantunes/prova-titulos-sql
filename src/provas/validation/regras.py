"""Regras de consistência. Erros bloqueiam prova de virar 'completa'; avisos não.

O runner é idempotente: achados automáticos não resolvidos da prova são
recriados a cada execução; resoluções humanas são preservadas.
"""

import re
from dataclasses import dataclass

from rapidfuzz import fuzz
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from provas.db.tables import (
    Alternativa,
    Prova,
    Proveniencia,
    Questao,
    QuestaoMidia,
    QuestaoTema,
    Validacao,
)
from provas.models.identificador import identificador_valido

TERMOS_MIDIA = re.compile(
    r"figura|traçado|eletrocardiograma|ecocardiograma|imagem (abaixo|a seguir)"
    r"|radiografia|tomografia|gráfico|exame de imagem",
    re.IGNORECASE,
)
LIMIAR_SIMILARIDADE = 90.0  # token_set_ratio 0-100


@dataclass(frozen=True)
class Achado:
    tabela: str
    registro_id: int | None
    regra: str
    severidade: str  # 'erro' | 'aviso'
    mensagem: str


def _erro(q: Questao, regra: str, msg: str) -> Achado:
    return Achado("questao", q.id, regra, "erro", f"{q.identificador}: {msg}")


def _aviso(q: Questao, regra: str, msg: str) -> Achado:
    return Achado("questao", q.id, regra, "aviso", f"{q.identificador}: {msg}")


def _questoes(session: Session, prova: Prova) -> list[Questao]:
    return list(
        session.scalars(
            select(Questao).where(Questao.prova_id == prova.id).order_by(Questao.numero)
        )
    )


def _alternativas(session: Session, questao: Questao) -> list[Alternativa]:
    return list(
        session.scalars(
            select(Alternativa)
            .where(Alternativa.questao_id == questao.id)
            .order_by(Alternativa.letra)
        )
    )


# --------------------------------------------------------------------------
# Erros
# --------------------------------------------------------------------------


def regra_correta_unica(session: Session, prova: Prova) -> list[Achado]:
    achados = []
    for q in _questoes(session, prova):
        if q.status != "valida" or q.gabarito_oficial is None:
            continue
        corretas = [a for a in _alternativas(session, q) if a.correta]
        if len(corretas) != 1:
            achados.append(
                _erro(q, "correta_unica", f"{len(corretas)} alternativas corretas (esperado 1).")
            )
    return achados


def regra_anulada_sem_gabarito(session: Session, prova: Prova) -> list[Achado]:
    return [
        _erro(q, "anulada_sem_gabarito", "questão anulada com gabarito_oficial preenchido.")
        for q in _questoes(session, prova)
        if q.status == "anulada" and q.gabarito_oficial is not None
    ]


def regra_alterada_consistente(session: Session, prova: Prova) -> list[Achado]:
    achados = []
    for q in _questoes(session, prova):
        if q.status == "gabarito_alterado" and (
            q.gabarito_preliminar is None or q.gabarito_preliminar == q.gabarito_oficial
        ):
            achados.append(
                _erro(
                    q, "alterada_consistente",
                    f"status gabarito_alterado mas preliminar={q.gabarito_preliminar!r} "
                    f"e oficial={q.gabarito_oficial!r}.",
                )
            )
    return achados


def regra_letras_contiguas(session: Session, prova: Prova) -> list[Achado]:
    achados = []
    for q in _questoes(session, prova):
        letras = [a.letra for a in _alternativas(session, q)]
        if not letras:
            continue
        esperado = [chr(ord("A") + i) for i in range(len(letras))]
        if letras != esperado:
            achados.append(
                _erro(q, "letras_contiguas", f"letras {letras} (esperado {esperado}).")
            )
    return achados


def regra_gabarito_letra_existente(session: Session, prova: Prova) -> list[Achado]:
    achados = []
    for q in _questoes(session, prova):
        if q.gabarito_oficial is None:
            continue
        letras = {a.letra for a in _alternativas(session, q)}
        if q.gabarito_oficial not in letras:
            achados.append(
                _erro(
                    q, "gabarito_letra_existente",
                    f"gabarito_oficial={q.gabarito_oficial!r} sem alternativa correspondente.",
                )
            )
    return achados


def regra_identificador_formato(session: Session, prova: Prova) -> list[Achado]:
    return [
        _erro(q, "identificador_formato", f"identificador {q.identificador!r} fora do formato.")
        for q in _questoes(session, prova)
        if not identificador_valido(q.identificador)
    ]


def regra_num_questoes_declarado(session: Session, prova: Prova) -> list[Achado]:
    if prova.num_questoes_declarado is None:
        return []
    n = len(_questoes(session, prova))
    if n != prova.num_questoes_declarado:
        return [
            Achado(
                "prova", prova.id, "num_questoes_declarado", "erro",
                f"prova id={prova.id}: {n} questões carregadas != "
                f"{prova.num_questoes_declarado} declaradas.",
            )
        ]
    return []


def regra_sem_saltos(session: Session, prova: Prova) -> list[Achado]:
    numeros = [q.numero for q in _questoes(session, prova)]
    if not numeros:
        return []
    faltando = sorted(set(range(1, max(numeros) + 1)) - set(numeros))
    if faltando:
        return [
            Achado(
                "prova", prova.id, "sem_saltos", "erro",
                f"prova id={prova.id}: numeração com buracos: {faltando}.",
            )
        ]
    return []


def regra_enunciado_minimo(session: Session, prova: Prova) -> list[Achado]:
    return [
        _erro(q, "enunciado_minimo", "enunciado vazio ou com menos de 20 caracteres.")
        for q in _questoes(session, prova)
        if not q.enunciado or len(q.enunciado.strip()) < 20
    ]


def regra_proveniencia_presente(session: Session, prova: Prova) -> list[Achado]:
    achados = []
    for q in _questoes(session, prova):
        n = session.scalar(
            select(Proveniencia.id).where(
                Proveniencia.tabela == "questao", Proveniencia.registro_id == q.id
            ).limit(1)
        )
        if n is None:
            achados.append(_erro(q, "proveniencia_presente", "questão sem proveniência."))
        for a in _alternativas(session, q):
            p = session.scalar(
                select(Proveniencia.id).where(
                    Proveniencia.tabela == "alternativa", Proveniencia.registro_id == a.id
                ).limit(1)
            )
            if p is None:
                achados.append(
                    _erro(
                        q, "proveniencia_presente",
                        f"alternativa {a.letra} (id={a.id}) sem proveniência.",
                    )
                )
    return achados


def regra_principal_unico(session: Session, prova: Prova) -> list[Achado]:
    """Aplicada apenas a questões JÁ classificadas (≥1 linha em questao_tema)."""
    achados = []
    for q in _questoes(session, prova):
        linhas = list(
            session.scalars(select(QuestaoTema).where(QuestaoTema.questao_id == q.id))
        )
        if not linhas:
            continue
        principais = [x for x in linhas if x.principal]
        if len(principais) != 1:
            achados.append(
                _erro(
                    q, "principal_unico",
                    f"{len(principais)} temas principais (esperado exatamente 1).",
                )
            )
    return achados


# --------------------------------------------------------------------------
# Avisos
# --------------------------------------------------------------------------


def regra_midia_provavelmente_perdida(session: Session, prova: Prova) -> list[Achado]:
    achados = []
    for q in _questoes(session, prova):
        texto = q.enunciado or ""
        if not TERMOS_MIDIA.search(texto):
            continue
        tem_midia = session.scalar(
            select(QuestaoMidia.id).where(QuestaoMidia.questao_id == q.id).limit(1)
        )
        if tem_midia is None:
            achados.append(
                _aviso(
                    q, "midia_provavelmente_perdida",
                    "enunciado menciona figura/traçado/imagem mas não há mídia associada.",
                )
            )
    return achados


def regra_alternativa_truncada(session: Session, prova: Prova) -> list[Achado]:
    achados = []
    for q in _questoes(session, prova):
        for a in _alternativas(session, q):
            t = (a.texto or "").strip()
            if t and len(t) < 15 and not t.endswith((".", "!", "?", ")", "%", '"')):
                achados.append(
                    _aviso(
                        q, "alternativa_truncada",
                        f"alternativa {a.letra} suspeita de truncamento: {t!r}.",
                    )
                )
    return achados


def regra_questao_repetida_entre_anos(session: Session, prova: Prova) -> list[Achado]:
    """Similaridade >0.9 com questão de OUTRO ano → achado interessante, não erro."""
    achados = []
    outras = list(
        session.execute(
            select(Questao, Prova.ano)
            .join(Prova, Questao.prova_id == Prova.id)
            .where(Prova.ano != prova.ano, Prova.sociedade_id == prova.sociedade_id)
        ).all()
    )
    if not outras:
        return []
    for q in _questoes(session, prova):
        if not q.enunciado:
            continue
        for outra, ano in outras:
            if not outra.enunciado:
                continue
            score = fuzz.token_set_ratio(q.enunciado, outra.enunciado)
            if score > LIMIAR_SIMILARIDADE:
                achados.append(
                    _aviso(
                        q, "questao_repetida_entre_anos",
                        f"similaridade {score:.0f} com {outra.identificador} ({ano}).",
                    )
                )
    return achados


# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------

REGRAS = [
    regra_correta_unica,
    regra_anulada_sem_gabarito,
    regra_alterada_consistente,
    regra_letras_contiguas,
    regra_gabarito_letra_existente,
    regra_identificador_formato,
    regra_num_questoes_declarado,
    regra_sem_saltos,
    regra_enunciado_minimo,
    regra_proveniencia_presente,
    regra_principal_unico,
    regra_midia_provavelmente_perdida,
    regra_alternativa_truncada,
    regra_questao_repetida_entre_anos,
]
NOMES_REGRAS = [r.__name__.removeprefix("regra_") for r in REGRAS]


def validar_prova(session: Session, prova: Prova) -> tuple[int, int]:
    """Roda todas as regras; devolve (n_erros, n_avisos) não resolvidos.

    Recria os achados automáticos não resolvidos da prova (idempotente) e
    promove/despromove prova.status 'completa'.
    """
    questao_ids = [q.id for q in _questoes(session, prova)]
    session.execute(
        delete(Validacao).where(
            Validacao.regra.in_(NOMES_REGRAS),
            Validacao.resolvido.is_(False),
            (
                (Validacao.tabela == "questao") & Validacao.registro_id.in_(questao_ids)
                if questao_ids
                else (Validacao.tabela == "questao") & (Validacao.registro_id.is_(None))
            )
            | ((Validacao.tabela == "prova") & (Validacao.registro_id == prova.id)),
        )
    )

    achados: list[Achado] = []
    for regra in REGRAS:
        achados.extend(regra(session, prova))

    for a in achados:
        session.add(
            Validacao(
                tabela=a.tabela,
                registro_id=a.registro_id,
                regra=a.regra,
                severidade=a.severidade,
                mensagem=a.mensagem,
            )
        )

    n_erros = sum(1 for a in achados if a.severidade == "erro")
    n_avisos = sum(1 for a in achados if a.severidade == "aviso")

    if n_erros == 0 and prova.status == "classificada":
        prova.status = "completa"
    elif n_erros > 0 and prova.status == "completa":
        prova.status = "classificada"
    session.flush()
    return n_erros, n_avisos
