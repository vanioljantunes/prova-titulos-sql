"""Carga determinística de edital no banco (o LLM nunca escreve SQL).

Cada campo carregado gera linha de proveniencia — inclusive os nulos, cuja
procedência registra a execução que constatou a ausência (o motivo fica no
JSON persistido em data/interim/).
"""

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from provas.db.tables import (
    ArquivoFonte,
    Edital,
    EditalCronograma,
    EditalFase,
    EditalTema,
    Sociedade,
    Tema,
    Validacao,
)
from provas.extraction.client import Prompt
from provas.extraction.reconcile import (
    REGRA_TEMA_NOVO,
    Casamento,
    Proposta,
    TemaCanonico,
)
from provas.models.comum import _CampoBase
from provas.models.edital import EditalMetadados


def _agora() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class RegistradorProveniencia:
    """Acumula e grava linhas de proveniencia para uma execução de extração."""

    def __init__(
        self, session: Session, arquivo_fonte: ArquivoFonte, modelo: str, prompt: Prompt
    ) -> None:
        self.session = session
        self.arquivo_fonte = arquivo_fonte
        self.modelo = modelo
        self.versao_prompt = f"{prompt.nome}@{prompt.version}"
        self.executado_em = _agora()

    def campo(
        self,
        tabela: str,
        registro_id: int,
        nome_campo: str,
        origem: _CampoBase | None = None,
        *,
        trecho: str | None = None,
        pagina: int | None = None,
    ) -> None:
        from provas.db.tables import Proveniencia

        if origem is not None:
            trecho = origem.trecho_fonte
            pagina = origem.pagina
        self.session.add(
            Proveniencia(
                tabela=tabela,
                registro_id=registro_id,
                campo=nome_campo,
                arquivo_fonte_id=self.arquivo_fonte.id,
                pagina=pagina,
                trecho_fonte=trecho,
                modelo=self.modelo,
                versao_prompt=self.versao_prompt,
                executado_em=self.executado_em,
            )
        )


def carregar_edital(
    session: Session,
    *,
    sociedade: Sociedade,
    arquivo_fonte: ArquivoFonte,
    meta: EditalMetadados,
    prov: RegistradorProveniencia,
    ano_fallback: int | None = None,
    edicao: int = 1,
) -> Edital:
    """Insere edital + fases + cronograma, com proveniencia por campo."""
    ano = meta.ano.valor if meta.ano.valor is not None else ano_fallback
    if ano is None:
        raise ValueError("ano não extraído do edital e sem fallback informado (--ano)")

    edital = Edital(
        sociedade_id=sociedade.id,
        arquivo_fonte_id=arquivo_fonte.id,
        ano=ano,
        edicao=edicao,
        titulo=meta.titulo.valor,
        data_publicacao=meta.data_publicacao.valor,
        inscricao_abertura=meta.inscricao_abertura.valor,
        inscricao_encerramento=meta.inscricao_encerramento.valor,
        taxa_valor=meta.taxa_valor.valor,
        data_prova=meta.data_prova.valor,
        local_prova=meta.local_prova.valor,
        modalidade=meta.modalidade.valor,
        num_questoes_previsto=meta.num_questoes_previsto.valor,
        nota_minima_aprovacao=meta.nota_minima_aprovacao.valor,
        pre_requisitos=meta.pre_requisitos.valor,
        bibliografia_recomendada=meta.bibliografia_recomendada.valor,
        observacoes=meta.observacoes.valor,
        vigente=False,
    )
    session.add(edital)
    session.flush()

    campos: dict[str, _CampoBase] = {
        "titulo": meta.titulo,
        "ano": meta.ano,
        "data_publicacao": meta.data_publicacao,
        "inscricao_abertura": meta.inscricao_abertura,
        "inscricao_encerramento": meta.inscricao_encerramento,
        "taxa_valor": meta.taxa_valor,
        "data_prova": meta.data_prova,
        "local_prova": meta.local_prova,
        "modalidade": meta.modalidade,
        "num_questoes_previsto": meta.num_questoes_previsto,
        "nota_minima_aprovacao": meta.nota_minima_aprovacao,
        "pre_requisitos": meta.pre_requisitos,
        "bibliografia_recomendada": meta.bibliografia_recomendada,
        "observacoes": meta.observacoes,
    }
    for nome_campo, origem in campos.items():
        prov.campo("edital", edital.id, nome_campo, origem)

    for fase in meta.fases:
        f = EditalFase(
            edital_id=edital.id,
            ordem=fase.ordem,
            nome=fase.nome,
            tipo=fase.tipo,
            peso=fase.peso,
            data=fase.data.valor,
            descricao=fase.descricao,
        )
        session.add(f)
        session.flush()
        prov.campo("edital_fase", f.id, "nome", trecho=fase.trecho_fonte, pagina=fase.pagina)
        prov.campo("edital_fase", f.id, "data", fase.data)

    for ev in meta.cronograma:
        c = EditalCronograma(
            edital_id=edital.id,
            evento=ev.evento,
            data_inicio=ev.data_inicio.valor,
            data_fim=ev.data_fim.valor,
            descricao=ev.descricao,
        )
        session.add(c)
        session.flush()
        prov.campo("edital_cronograma", c.id, "evento", trecho=ev.evento, pagina=ev.pagina)
        prov.campo("edital_cronograma", c.id, "data_inicio", ev.data_inicio)
        prov.campo("edital_cronograma", c.id, "data_fim", ev.data_fim)

    session.flush()
    return edital


def temas_canonicos(session: Session, especialidade: str) -> list[TemaCanonico]:
    linhas = session.scalars(select(Tema).where(Tema.especialidade == especialidade)).all()
    return [TemaCanonico(id=t.id, nome=t.nome, slug=t.slug) for t in linhas]


def carregar_reconciliacao(
    session: Session,
    *,
    edital: Edital,
    especialidade: str,
    casados: list[Casamento],
    propostas: list[Proposta],
    prov: RegistradorProveniencia,
) -> None:
    """Grava edital_tema para casamentos confiantes e propostas em validacao."""
    for c in casados:
        et = EditalTema(
            edital_id=edital.id,
            tema_id=c.tema_id,
            texto_original=c.extraido.texto_original,
            ordem=c.extraido.ordem,
        )
        session.add(et)
        session.flush()
        prov.campo(
            "edital_tema", et.id, "texto_original",
            trecho=c.extraido.texto_original, pagina=c.extraido.pagina,
        )

    for p in propostas:
        session.add(
            Validacao(
                tabela="edital_tema",
                registro_id=None,
                regra=REGRA_TEMA_NOVO,
                severidade="aviso",
                mensagem=p.payload_json(edital.id, especialidade),
            )
        )
    session.flush()


def atualizar_vigencia(session: Session, sociedade_id: int) -> Edital | None:
    """vigente=true apenas no edital mais recente (ano, edicao) da sociedade."""
    mais_recente = session.scalar(
        select(Edital)
        .where(Edital.sociedade_id == sociedade_id)
        .order_by(Edital.ano.desc(), Edital.edicao.desc(), Edital.id.desc())
        .limit(1)
    )
    if mais_recente is None:
        return None
    session.execute(
        update(Edital).where(Edital.sociedade_id == sociedade_id).values(vigente=False)
    )
    session.execute(update(Edital).where(Edital.id == mais_recente.id).values(vigente=True))
    session.flush()
    return mais_recente
