"""Marco 4: geração determinística de identificador."""

import pytest

from provas.models.identificador import (
    gerar_identificador,
    identificador_valido,
)


def test_formato_basico_tres_digitos() -> None:
    assert gerar_identificador("SBC", 2024, 42) == "SBC-2024-042"
    assert gerar_identificador("SBCM", 2023, 7) == "SBCM-2023-007"
    assert gerar_identificador("SBC", 2024, 120) == "SBC-2024-120"


def test_edicao_maior_que_um_entra_no_identificador() -> None:
    assert gerar_identificador("SBC", 2024, 42, edicao=2) == "SBC-2024.2-042"


def test_edicao_um_omitida() -> None:
    assert gerar_identificador("SBC", 2024, 42, edicao=1) == "SBC-2024-042"


@pytest.mark.parametrize(
    ("sigla", "ano", "numero", "edicao"),
    [
        ("sbc", 2024, 1, 1),     # minúsculas
        ("S", 2024, 1, 1),       # curta demais
        ("SBC", 1024, 1, 1),     # ano absurdo
        ("SBC", 2024, 0, 1),     # numero < 1
        ("SBC", 2024, 1000, 1),  # numero > 999
        ("SBC", 2024, 1, 0),     # edicao < 1
    ],
)
def test_entradas_invalidas_rejeitadas(sigla: str, ano: int, numero: int, edicao: int) -> None:
    with pytest.raises(ValueError):
        gerar_identificador(sigla, ano, numero, edicao)


def test_regex_de_validacao() -> None:
    assert identificador_valido("SBC-2024-042")
    assert identificador_valido("SBC-2024.2-042")
    assert not identificador_valido("SBC-2024-42")
    assert not identificador_valido("sbc-2024-042")
    assert not identificador_valido("SBC-2024-0421")
