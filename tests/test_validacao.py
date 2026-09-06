"""Marco 7: todas as regras de validação, promoção de status e idempotência."""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from provas.db.fontes import registrar_arquivo_fonte
from provas.db.tables import (
    Alternativa,
    Prova,
    Proveniencia,
    Questao,
    QuestaoMidia,
    QuestaoTema,
    Sociedade,
    Tema,
    Validacao,
)
from provas.validation.regras import validar_prova


def _prova(session: Session, tmp_path: Path, *, ano: int = 2024, declarado: int | None = None,
           status: str = "ingerida") -> Prova:
    soc = session.scalar(select(Sociedade).where(Sociedade.sigla == "SBC"))
    if soc is None:
        soc = Sociedade(sigla="SBC", nome="SBC", especialidade="cardiologia")
        session.add(soc)
        session.flush()
    pdf = tmp_path / f"p{ano}.pdf"
    if not pdf.exists():
        pdf.write_bytes(f"%PDF-{ano}".encode())
    arq = registrar_arquivo_fonte(session, pdf, "prova")
    p = Prova(
        sociedade_id=soc.id, arquivo_fonte_id=arq.id, ano=ano,
        num_questoes_declarado=declarado, status=status,
    )
    session.add(p)
    session.flush()
    return p


def _questao(
    session: Session, prova: Prova, numero: int, *,
    enunciado: str | None = "Enunciado padrão com mais de vinte caracteres.",
    letras: str = "ABCD", correta: str | None = None,
    gabarito_oficial: str | None = None, status: str = "valida",
    gabarito_preliminar: str | None = None, com_proveniencia: bool = True,
) -> Questao:
    q = Questao(
        prova_id=prova.id, identificador=f"SBC-{prova.ano}-{numero:03d}", numero=numero,
        enunciado=enunciado, status=status,
        gabarito_preliminar=gabarito_preliminar, gabarito_oficial=gabarito_oficial,
    )
    session.add(q)
    session.flush()
    for letra in letras:
        session.add(
            Alternativa(
                questao_id=q.id, letra=letra, texto=f"alternativa {letra} completa.",
                correta=(letra == correta),
            )
        )
    session.flush()
    if com_proveniencia:
        session.add(
            Proveniencia(
                tabela="questao", registro_id=q.id, campo="enunciado",
                arquivo_fonte_id=prova.arquivo_fonte_id, modelo="m", versao_prompt="t@1",
            )
        )
        for a in session.scalars(select(Alternativa).where(Alternativa.questao_id == q.id)):
            session.add(
                Proveniencia(
                    tabela="alternativa", registro_id=a.id, campo="texto",
                    arquivo_fonte_id=prova.arquivo_fonte_id, modelo="m", versao_prompt="t@1",
                )
            )
    session.flush()
    return q


def _regras_achadas(session: Session) -> set[str]:
    return {
        v.regra for v in session.scalars(select(Validacao).where(Validacao.resolvido.is_(False)))
    }


def test_prova_limpa_sem_erros_e_promovida(session: Session, tmp_path: Path) -> None:
    prova = _prova(session, tmp_path, declarado=2, status="classificada")
    tema = Tema(especialidade="cardiologia", nivel=1, nome="T", slug="t")
    session.add(tema)
    session.flush()
    for n in (1, 2):
        q = _questao(session, prova, n, correta="A", gabarito_oficial="A")
        session.add(QuestaoTema(questao_id=q.id, tema_id=tema.id, principal=True))
    session.flush()
    erros, _avisos = validar_prova(session, prova)
    assert erros == 0
    assert prova.status == "completa"


def test_erros_bloqueiam_completa_e_regras_disparam(session: Session, tmp_path: Path) -> None:
    prova = _prova(session, tmp_path, declarado=3, status="classificada")
    # 1: duas corretas + salto (sem questão 2) + enunciado curto
    _questao(session, prova, 1, correta=None, gabarito_oficial="E", enunciado="curto")
    _questao(session, prova, 3, correta="A", gabarito_oficial="A")
    erros, _ = validar_prova(session, prova)
    regras = _regras_achadas(session)
    assert {
        "correta_unica", "gabarito_letra_existente", "enunciado_minimo",
        "sem_saltos", "num_questoes_declarado",
    } <= regras
    assert erros >= 5
    assert prova.status == "classificada"  # não promovida


def test_anulada_com_gabarito_e_alterada_inconsistente(session: Session, tmp_path: Path) -> None:
    prova = _prova(session, tmp_path)
    _questao(session, prova, 1, status="anulada", gabarito_oficial="A", correta="A")
    _questao(
        session, prova, 2, status="gabarito_alterado",
        gabarito_preliminar="B", gabarito_oficial="B", correta="B",
    )
    validar_prova(session, prova)
    regras = _regras_achadas(session)
    assert {"anulada_sem_gabarito", "alterada_consistente"} <= regras


def test_letras_nao_contiguas(session: Session, tmp_path: Path) -> None:
    prova = _prova(session, tmp_path)
    _questao(session, prova, 1, letras="ABD")  # pula C
    validar_prova(session, prova)
    assert "letras_contiguas" in _regras_achadas(session)


def test_proveniencia_ausente_e_erro(session: Session, tmp_path: Path) -> None:
    prova = _prova(session, tmp_path)
    _questao(session, prova, 1, com_proveniencia=False)
    validar_prova(session, prova)
    assert "proveniencia_presente" in _regras_achadas(session)


def test_principal_unico_so_para_classificadas(session: Session, tmp_path: Path) -> None:
    prova = _prova(session, tmp_path)
    q1 = _questao(session, prova, 1, correta="A", gabarito_oficial="A")
    _questao(session, prova, 2, correta="A", gabarito_oficial="A")  # sem classificação: ok
    tema = Tema(especialidade="cardiologia", nivel=1, nome="T", slug="t")
    session.add(tema)
    session.flush()
    session.add(QuestaoTema(questao_id=q1.id, tema_id=tema.id, principal=False))  # sem principal
    session.flush()
    validar_prova(session, prova)
    assert "principal_unico" in _regras_achadas(session)
    msgs = [
        v.mensagem
        for v in session.scalars(select(Validacao).where(Validacao.regra == "principal_unico"))
    ]
    assert len(msgs) == 1  # questão 2 (não classificada) não dispara


def test_aviso_midia_perdida(session: Session, tmp_path: Path) -> None:
    prova = _prova(session, tmp_path)
    q1 = _questao(
        session, prova, 1,
        enunciado="Observe o eletrocardiograma abaixo e responda corretamente.",
        correta="A", gabarito_oficial="A",
    )
    q2 = _questao(
        session, prova, 2,
        enunciado="Analise a figura a seguir do ecocardiograma transtorácico.",
        correta="A", gabarito_oficial="A",
    )
    session.add(
        QuestaoMidia(questao_id=q2.id, tipo="imagem", caminho_arquivo="x.png", ordem=1)
    )
    session.flush()
    validar_prova(session, prova)
    achadas = [
        v.registro_id
        for v in session.scalars(
            select(Validacao).where(Validacao.regra == "midia_provavelmente_perdida")
        )
    ]
    assert achadas == [q1.id]  # q2 tem mídia, não dispara


def test_aviso_alternativa_truncada(session: Session, tmp_path: Path) -> None:
    prova = _prova(session, tmp_path)
    q = _questao(session, prova, 1, letras="AB", correta="A", gabarito_oficial="A")
    alt_b = session.scalar(
        select(Alternativa).where(Alternativa.questao_id == q.id, Alternativa.letra == "B")
    )
    assert alt_b is not None
    alt_b.texto = "Aumento do"  # curto, sem pontuação
    session.flush()
    validar_prova(session, prova)
    assert "alternativa_truncada" in _regras_achadas(session)


def test_aviso_questao_repetida_entre_anos(session: Session, tmp_path: Path) -> None:
    enunciado = (
        "Paciente de 60 anos com dor torácica típica em aperto irradiada para o braço "
        "esquerdo há 2 horas, com supradesnivelamento de ST em parede inferior."
    )
    p1 = _prova(session, tmp_path, ano=2023)
    _questao(session, p1, 1, enunciado=enunciado, correta="A", gabarito_oficial="A")
    p2 = _prova(session, tmp_path, ano=2024)
    _questao(session, p2, 1, enunciado=enunciado, correta="A", gabarito_oficial="A")
    validar_prova(session, p2)
    assert "questao_repetida_entre_anos" in _regras_achadas(session)


def test_validacao_idempotente_nao_duplica(session: Session, tmp_path: Path) -> None:
    prova = _prova(session, tmp_path)
    _questao(session, prova, 1, enunciado="curto")
    validar_prova(session, prova)
    validar_prova(session, prova)
    achados = session.scalars(
        select(Validacao).where(Validacao.regra == "enunciado_minimo")
    ).all()
    assert len(achados) == 1
