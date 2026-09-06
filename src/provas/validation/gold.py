"""Harness de avaliação contra o padrão-ouro (transcrição humana).

Métricas SEPARADAS por tipo de campo — campos numéricos/estruturais são o ponto
fraco documentado de extração por LLM e não podem se esconder numa acurácia
agregada:

  - categoricos:   tipo da questão, letra do gabarito
  - textuais:      enunciado, texto das alternativas, contexto
  - estruturais:   presença da questão, nº de alternativas, nº de mídias

Por campo: acurácia exata, taxa de omissão (extraído vazio com gold preenchido)
e taxa de erro (extraído diferente do gold).
"""

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from provas.db.tables import Alternativa, Questao, QuestaoMidia


def _norm(texto: str | None) -> str:
    if texto is None:
        return ""
    s = unicodedata.normalize("NFKC", texto)
    return re.sub(r"\s+", " ", s).strip().lower()


@dataclass
class MetricaCampo:
    total: int = 0
    exatos: int = 0
    omissoes: int = 0
    erros: int = 0

    def registrar(self, gold: str | None, extraido: str | None) -> None:
        gold_n, ext_n = _norm(gold), _norm(extraido)
        if not gold_n:
            return  # campo ausente no gold não pontua
        self.total += 1
        if not ext_n:
            self.omissoes += 1
        elif ext_n == gold_n:
            self.exatos += 1
        else:
            self.erros += 1

    def como_dict(self) -> dict[str, Any]:
        t = self.total or 1
        return {
            "total": self.total,
            "acuracia_exata": round(self.exatos / t, 4),
            "taxa_omissao": round(self.omissoes / t, 4),
            "taxa_erro": round(self.erros / t, 4),
        }


@dataclass
class RelatorioGold:
    categoricos: dict[str, MetricaCampo] = field(default_factory=dict)
    textuais: dict[str, MetricaCampo] = field(default_factory=dict)
    estruturais: dict[str, MetricaCampo] = field(default_factory=dict)
    questoes_gold: int = 0
    questoes_extraidas: int = 0
    questoes_faltando: list[int] = field(default_factory=list)

    def _grupo(self, nome: str) -> dict[str, MetricaCampo]:
        return getattr(self, nome)  # type: ignore[no-any-return]

    def metrica(self, grupo: str, campo: str) -> MetricaCampo:
        g = self._grupo(grupo)
        if campo not in g:
            g[campo] = MetricaCampo()
        return g[campo]

    def como_dict(self) -> dict[str, Any]:
        return {
            "questoes_gold": self.questoes_gold,
            "questoes_extraidas": self.questoes_extraidas,
            "questoes_faltando": self.questoes_faltando,
            "categoricos": {k: v.como_dict() for k, v in self.categoricos.items()},
            "textuais": {k: v.como_dict() for k, v in self.textuais.items()},
            "estruturais": {k: v.como_dict() for k, v in self.estruturais.items()},
        }


def carregar_gold(caminho: Path) -> dict[str, Any]:
    return json.loads(caminho.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def avaliar(session: Session, prova_id: int, gold: dict[str, Any]) -> RelatorioGold:
    rel = RelatorioGold()
    questoes_db = {
        q.numero: q
        for q in session.scalars(select(Questao).where(Questao.prova_id == prova_id))
    }
    gold_questoes: list[dict[str, Any]] = gold.get("questoes", [])
    rel.questoes_gold = len(gold_questoes)
    rel.questoes_extraidas = len(questoes_db)

    for gq in gold_questoes:
        numero = int(gq["numero"])
        q = questoes_db.get(numero)
        m_presenca = rel.metrica("estruturais", "questao_presente")
        m_presenca.registrar("presente", "presente" if q else None)
        if q is None:
            rel.questoes_faltando.append(numero)
            continue

        rel.metrica("categoricos", "tipo").registrar(gq.get("tipo"), q.tipo)
        rel.metrica("categoricos", "gabarito_oficial").registrar(
            gq.get("gabarito_oficial"), q.gabarito_oficial
        )
        rel.metrica("categoricos", "status").registrar(gq.get("status"), q.status)
        rel.metrica("textuais", "enunciado").registrar(gq.get("enunciado"), q.enunciado)

        alts_db = {
            a.letra: a
            for a in session.scalars(
                select(Alternativa).where(Alternativa.questao_id == q.id)
            )
        }
        gold_alts: list[dict[str, Any]] = gq.get("alternativas", [])
        rel.metrica("estruturais", "num_alternativas").registrar(
            str(len(gold_alts)), str(len(alts_db))
        )
        for ga in gold_alts:
            letra = str(ga["letra"]).upper()
            alt = alts_db.get(letra)
            rel.metrica("textuais", "alternativa_texto").registrar(
                ga.get("texto"), alt.texto if alt else None
            )

        if "num_midias" in gq:
            n_midias = session.scalars(
                select(QuestaoMidia).where(QuestaoMidia.questao_id == q.id)
            ).all()
            rel.metrica("estruturais", "num_midias").registrar(
                str(gq["num_midias"]), str(len(n_midias))
            )

    return rel
