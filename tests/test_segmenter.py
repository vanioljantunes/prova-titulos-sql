"""Marco 4: segmentação determinística de questões."""

from provas.parsing.segmenter import segmentar


def test_segmenta_questoes_simples_em_uma_pagina() -> None:
    page_texts = {
        1: "QUESTÃO 1 Paciente de 60 anos...\nA) x\nB) y\n"
           "QUESTÃO 2 Mulher de 45 anos...\nA) w\nB) z\n",
    }
    segs = segmentar(page_texts)
    assert [s.numero for s in segs] == [1, 2]
    assert "Paciente de 60 anos" in segs[0].texto
    assert "Mulher de 45 anos" in segs[1].texto
    assert "Mulher" not in segs[0].texto  # corte no início da questão seguinte


def test_questao_atravessando_paginas() -> None:
    page_texts = {
        1: "1. Enunciado longo que continua...",
        2: "...continuação e alternativas\n2. Segunda questão",
    }
    segs = segmentar(page_texts)
    assert [s.numero for s in segs] == [1, 2]
    assert segs[0].pagina_inicio == 1
    assert segs[0].pagina_fim == 2
    assert segs[1].pagina_inicio == 2


def test_falso_positivo_fora_de_sequencia_ignorado() -> None:
    # "10." numa tabela no meio da questão 1 não pode virar questão
    page_texts = {
        1: "1. Enunciado com tabela:\n10. linhas de dado\n2. Próxima questão real",
    }
    segs = segmentar(page_texts)
    assert [s.numero for s in segs] == [1, 2]


def test_numeracao_deve_comecar_em_um() -> None:
    # caderno cortado começando na questão 5: sem âncora 1, nada é segmentado
    page_texts = {1: "5. Questão avulsa\n6. Outra"}
    assert segmentar(page_texts) == []


def test_bullet_antes_do_rotulo_questao() -> None:
    # formato real do caderno SBCM 2026: "▪  QUESTÃO 1"
    page_texts = {1: "▪  QUESTÃO 1\nEnunciado um\n▪  QUESTÃO 2\nEnunciado dois"}
    segs = segmentar(page_texts)
    assert [s.numero for s in segs] == [1, 2]


def test_prefixo_questao_case_insensitive_e_pontuacao_variada() -> None:
    page_texts = {1: "Questão 1: enunciado\nQUESTÃO 2 - enunciado\n3) enunciado"}
    segs = segmentar(page_texts)
    assert [s.numero for s in segs] == [1, 2, 3]
