"""Carga determinística de prova: contexto (dedupe), questões, alternativas, mídia.

Gabaritos ficam NULOS aqui — prova não define gabarito (vem em documento próprio).
"""

import json
from pathlib import Path

from sqlalchemy.orm import Session

from provas.db.loaders_edital import RegistradorProveniencia
from provas.db.tables import (
    Alternativa,
    ArquivoFonte,
    Contexto,
    Prova,
    Questao,
    QuestaoMidia,
    Sociedade,
)
from provas.models.identificador import gerar_identificador
from provas.models.prova import QuestaoExtraida
from provas.parsing.segmenter import SegmentoQuestao


def criar_prova(
    session: Session,
    *,
    sociedade: Sociedade,
    arquivo_fonte: ArquivoFonte,
    ano: int,
    edicao: int = 1,
    edital_id: int | None = None,
    tipo_caderno: str | None = None,
    num_questoes_declarado: int | None = None,
) -> Prova:
    prova = Prova(
        sociedade_id=sociedade.id,
        edital_id=edital_id,
        arquivo_fonte_id=arquivo_fonte.id,
        ano=ano,
        edicao=edicao,
        tipo_caderno=tipo_caderno,
        num_questoes_declarado=num_questoes_declarado,
        status="ingerida",
    )
    session.add(prova)
    session.flush()
    return prova


class FiguraDisponivel:
    """Figura extraída pelo parse (pictures.json), candidata a questao_midia."""

    def __init__(self, ordem: int, pagina: int | None, bbox: list[float] | None, caminho: str):
        self.ordem = ordem
        self.pagina = pagina
        self.bbox = bbox
        self.caminho = caminho
        self.usada = False


def carregar_figuras(interim: Path) -> list[FiguraDisponivel]:
    indice_path = interim / "pictures.json"
    if not indice_path.exists():
        return []
    saida = []
    for item in json.loads(indice_path.read_text(encoding="utf-8")):
        if item.get("caminho"):
            saida.append(
                FiguraDisponivel(
                    ordem=item["ordem"],
                    pagina=item.get("pagina"),
                    bbox=item.get("bbox"),
                    caminho=str(interim / item["caminho"]),
                )
            )
    return saida


def carregar_questao(
    session: Session,
    *,
    prova: Prova,
    sigla: str,
    extraida: QuestaoExtraida,
    segmento: SegmentoQuestao,
    figuras: list[FiguraDisponivel],
    prov: RegistradorProveniencia,
    contextos_cache: dict[str, int],
) -> Questao:
    """Insere uma questão extraída, com dedupe de contexto e associação de mídia."""
    contexto_id: int | None = None
    ctx_texto = extraida.contexto_compartilhado.valor
    if ctx_texto:
        chave = ctx_texto.strip()
        if chave in contextos_cache:
            contexto_id = contextos_cache[chave]
        else:
            ctx = Contexto(
                prova_id=prova.id,
                tipo=extraida.contexto_tipo or "texto_base",
                texto=ctx_texto,
            )
            session.add(ctx)
            session.flush()
            contextos_cache[chave] = ctx.id
            contexto_id = ctx.id
            prov.campo("contexto", ctx.id, "texto", extraida.contexto_compartilhado)

    questao = Questao(
        prova_id=prova.id,
        identificador=gerar_identificador(sigla, prova.ano, extraida.numero, prova.edicao),
        numero=extraida.numero,
        contexto_id=contexto_id,
        enunciado=extraida.enunciado.valor,
        tipo=extraida.tipo,
        gabarito_preliminar=None,
        gabarito_oficial=None,
        status="valida",
    )
    session.add(questao)
    session.flush()
    prov.campo("questao", questao.id, "enunciado", extraida.enunciado)
    prov.campo(
        "questao", questao.id, "numero",
        trecho=str(extraida.numero), pagina=segmento.pagina_inicio,
    )

    for alt in extraida.alternativas:
        a = Alternativa(
            questao_id=questao.id, letra=alt.letra.upper(), texto=alt.texto, correta=False
        )
        session.add(a)
        session.flush()
        prov.campo(
            "alternativa", a.id, "texto",
            trecho=(alt.texto or "")[:200] or None, pagina=segmento.pagina_inicio,
        )

    if extraida.midias:
        candidatas = [
            f for f in figuras
            if not f.usada and f.pagina is not None
            and segmento.pagina_inicio <= f.pagina <= segmento.pagina_fim
        ]
        for ordem, (midia, fig) in enumerate(
            zip(extraida.midias, candidatas, strict=False), start=1
        ):
            fig.usada = True
            m = QuestaoMidia(
                questao_id=questao.id,
                ordem=ordem,
                tipo=midia.tipo,
                caminho_arquivo=fig.caminho,
                legenda=midia.legenda,
                pagina=fig.pagina,
                bbox=json.dumps(fig.bbox) if fig.bbox else None,
            )
            session.add(m)
            session.flush()
            prov.campo(
                "questao_midia", m.id, "caminho_arquivo",
                trecho=midia.descricao, pagina=fig.pagina,
            )

    session.flush()
    return questao
