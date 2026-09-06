"""Marco 3: reconciliação de taxonomia — determinística, nunca cria tema sozinha."""

from provas.extraction.reconcile import (
    LIMIAR_CONFIANTE,
    TemaCanonico,
    reconciliar,
    slugify,
)
from provas.models.edital import TemaExtraido


def _ext(texto: str, ordem: int = 1, **kw: object) -> TemaExtraido:
    return TemaExtraido(texto_original=texto, nivel=1, ordem=ordem, **kw)  # type: ignore[arg-type]


def test_slugify_normaliza_acentos_e_pontuacao() -> None:
    assert slugify("Doenças Cardiovasculares: Hipertensão Arterial") == (
        "doencas-cardiovasculares-hipertensao-arterial"
    )


def test_casamento_exato_por_slug() -> None:
    canonicos = [TemaCanonico(id=1, nome="Insuficiência Cardíaca", slug="insuficiencia-cardiaca")]
    casados, propostas = reconciliar([_ext("Insuficiência cardíaca")], canonicos)
    assert len(casados) == 1 and not propostas
    assert casados[0].tema_id == 1
    assert casados[0].score == 100.0


def test_casamento_fuzzy_confiante_renomeacao_leve() -> None:
    canonicos = [
        TemaCanonico(id=7, nome="Arritmias cardíacas", slug="arritmias-cardiacas"),
        TemaCanonico(id=8, nome="Valvopatias", slug="valvopatias"),
    ]
    casados, propostas = reconciliar([_ext("Arritmia cardíaca")], canonicos)
    assert len(casados) == 1 and not propostas
    assert casados[0].tema_id == 7
    assert casados[0].score >= LIMIAR_CONFIANTE


def test_tema_desconhecido_vira_proposta_nunca_criacao() -> None:
    canonicos = [TemaCanonico(id=1, nome="Valvopatias", slug="valvopatias")]
    casados, propostas = reconciliar([_ext("Cardio-oncologia", ordem=3)], canonicos)
    assert not casados and len(propostas) == 1
    p = propostas[0]
    assert p.extraido.texto_original == "Cardio-oncologia"
    assert p.melhor_score < LIMIAR_CONFIANTE


def test_taxonomia_vazia_todos_viram_proposta() -> None:
    casados, propostas = reconciliar([_ext("A"), _ext("B", ordem=2)], [])
    assert not casados and len(propostas) == 2
    assert all(p.melhor_candidato_id is None for p in propostas)


def test_payload_json_da_proposta_e_completo() -> None:
    import json

    _, propostas = reconciliar(
        [_ext("Cardiopatias congênitas", ordem=5, codigo="3.2", parent_codigo="3")], []
    )
    payload = json.loads(propostas[0].payload_json(edital_id=42, especialidade="cardiologia"))
    assert payload["edital_id"] == 42
    assert payload["codigo"] == "3.2"
    assert payload["parent_codigo"] == "3"
    assert payload["slug"] == "cardiopatias-congenitas"
