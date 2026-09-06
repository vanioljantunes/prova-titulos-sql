"""Classificação temática: vocabulário do edital vigente + uma chamada por questão.

Passada SEPARADA da extração (nunca na mesma chamada). Resultados persistidos
em data/interim/classificacao/prova_<id>/qNNN.json.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from provas.db.tables import Edital, EditalTema, Questao, Tema
from provas.extraction.client import Prompt, carregar_prompt, extrair
from provas.models.classificacao import ClassificacaoQuestao, schema_para_vocabulario

CLASSIFICACAO_ROOT = Path("data/interim/classificacao")


@dataclass(frozen=True)
class ItemVocabulario:
    tema_id: int
    nivel: int
    nome: str


def vocabulario_do_edital_vigente(
    session: Session, sociedade_id: int
) -> tuple[Edital | None, list[ItemVocabulario]]:
    """Temas do edital vigente da sociedade (via edital_tema → tema)."""
    vigente = session.scalar(
        select(Edital).where(Edital.sociedade_id == sociedade_id, Edital.vigente.is_(True))
    )
    if vigente is None:
        return None, []
    linhas = session.execute(
        select(Tema, EditalTema)
        .join(EditalTema, EditalTema.tema_id == Tema.id)
        .where(EditalTema.edital_id == vigente.id)
        .order_by(EditalTema.ordem)
    ).all()
    itens = [
        ItemVocabulario(tema_id=t.id, nivel=t.nivel or 1, nome=t.nome) for t, _et in linhas
    ]
    return vigente, itens


def formatar_vocabulario(itens: list[ItemVocabulario]) -> str:
    linhas = []
    for i, item in enumerate(itens, start=1):
        recuo = "  " * (item.nivel - 1)
        linhas.append(f"{recuo}{i}. [id={item.tema_id}] {item.nome}")
    return "\n".join(linhas)


def _texto_questao(session: Session, questao: Questao) -> str:
    from provas.db.tables import Alternativa

    alts = session.scalars(
        select(Alternativa).where(Alternativa.questao_id == questao.id).order_by(Alternativa.letra)
    ).all()
    corpo = [f"Enunciado: {questao.enunciado or '(vazio)'}"]
    corpo += [f"{a.letra}) {a.texto or '(ilegível)'}" for a in alts]
    return "\n".join(corpo)


def classificar_questao(
    cliente: Any,
    session: Session,
    questao: Questao,
    vocabulario: list[ItemVocabulario],
    *,
    force: bool = False,
) -> tuple[ClassificacaoQuestao, Prompt]:
    prompt = carregar_prompt("classificar_tema")
    destino = CLASSIFICACAO_ROOT / f"prova_{questao.prova_id}" / f"q{questao.numero:03d}.json"
    if destino.exists() and not force:
        return ClassificacaoQuestao.model_validate_json(
            destino.read_text(encoding="utf-8")
        ), prompt

    ids_validos = {item.tema_id for item in vocabulario}
    schema = schema_para_vocabulario(ids_validos)
    conteudo = (
        f"Vocabulário controlado (edital vigente):\n\n{formatar_vocabulario(vocabulario)}"
        f"\n\n---\n\nQuestão {questao.identificador}:\n\n{_texto_questao(session, questao)}"
    )
    resultado = extrair(
        cliente, prompt=prompt, response_model=schema, user_content=conteudo
    )
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(resultado.model_dump_json(indent=2), encoding="utf-8")
    return resultado, prompt


def persistir_vocabulario_usado(prova_id: int, itens: list[ItemVocabulario]) -> None:
    destino = CLASSIFICACAO_ROOT / f"prova_{prova_id}" / "vocabulario.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(
            [{"tema_id": i.tema_id, "nivel": i.nivel, "nome": i.nome} for i in itens],
            ensure_ascii=False, indent=1,
        ),
        encoding="utf-8",
    )
