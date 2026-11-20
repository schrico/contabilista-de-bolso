"""Testes do verificador de NIF e IBAN.

Regra do projeto: nenhum NIF ou IBAN válido fica escrito no repositório, nem nos testes.
Os valores de teste são gerados quando os testes correm, a partir de dígitos inventados,
com o dígito de controlo calculado na hora. A única exceção é o exemplo oficial da norma
do IBAN, que não corresponde a nenhuma conta e está marcado como permitido.
"""

import subprocess

import pytest

from ferramentas.verificar_dados_pessoais import (
    MARCADOR_PERMITIDO,
    digito_controlo_nif,
    digitos_controlo_iban,
    iban_valido,
    main,
    nif_valido,
    procurar_no_texto,
    verificar_ficheiro,
)

# --- geradores de valores inventados -------------------------------------------------


def gerar_nif(oito_digitos: str) -> str:
    return oito_digitos + str(digito_controlo_nif(oito_digitos))


def nif_com_controlo_errado(oito_digitos: str) -> str:
    errado = (digito_controlo_nif(oito_digitos) + 1) % 10
    return oito_digitos + str(errado)


def gerar_iban(pais: str, bban: str) -> str:
    return pais + digitos_controlo_iban(pais, bban) + bban


def agrupar(iban: str) -> str:
    return " ".join(iban[i : i + 4] for i in range(0, len(iban), 4))


# Dígitos inventados. O primeiro dígito do NIF tem de ser um prefixo atribuído pela AT.
NIF_SINGULAR = gerar_nif("2" + "9876543")
NIF_COLETIVO = gerar_nif("5" + "0102030")
BBAN_PT = "0000" + "0000" + "12345678901" + "00"  # banco, balcão, conta, controlo nacional
IBAN_PT = gerar_iban("PT", BBAN_PT)
IBAN_ES = gerar_iban("ES", "0000" + "0000" + "00" + "1234567890")


# --- dígito de controlo do NIF -------------------------------------------------------


def test_digito_controlo_nif_exemplo_feito_a_mao():
    # 1*9 + 2*8 + 3*7 + 4*6 + 5*5 + 6*4 + 7*3 + 8*2 = 156; 156 % 11 = 2; 11 - 2 = 9
    assert digito_controlo_nif("12345678") == 9


def test_digito_controlo_nif_resto_0_ou_1_da_zero():
    # 1*9 + 1*2 = 11 -> resto 0 -> controlo 0
    assert digito_controlo_nif("10000001") == 0
    # 1*9 + 1*3 = 12 -> resto 1 -> controlo 0
    assert digito_controlo_nif("10000010") == 0


def test_nif_valido_aceita_gerado():
    assert nif_valido(NIF_SINGULAR)
    assert nif_valido(NIF_COLETIVO)


def test_nif_valido_rejeita_controlo_errado():
    assert not nif_valido(nif_com_controlo_errado("29876543"))


@pytest.mark.parametrize("posicao", range(8))
def test_nif_valido_rejeita_qualquer_digito_trocado(posicao):
    digitos = list(NIF_SINGULAR)
    digitos[posicao] = str((int(digitos[posicao]) + 1) % 10)
    trocado = "".join(digitos)
    # Trocar um dígito muda sempre o resto da divisão por 11 (os pesos são 2 a 9). Os restos
    # 0 e 1 dão ambos controlo 0, por isso em geral pode haver colisões; com os dígitos
    # inventados acima (resto 3) nenhuma troca cai nesse caso.
    assert not nif_valido(trocado)


@pytest.mark.parametrize("prefixo", ["4", "0", "73", "76", "92", "97"])
def test_nif_valido_rejeita_prefixo_nao_atribuido(prefixo):
    resto = "1234567"[: 8 - len(prefixo)]
    assert not nif_valido(gerar_nif(prefixo + resto))


PREFIXOS_ATRIBUIDOS = [
    "1", "2", "3", "45", "5", "6", "70", "71", "72", "74",
    "75", "77", "78", "79", "8", "90", "91", "98", "99",
]  # fmt: skip


@pytest.mark.parametrize("prefixo", PREFIXOS_ATRIBUIDOS)
def test_nif_valido_aceita_prefixos_atribuidos(prefixo):
    resto = "1234567"[: 8 - len(prefixo)]
    assert nif_valido(gerar_nif(prefixo + resto))


def test_nif_valido_rejeita_formato_errado():
    assert not nif_valido("12345678")
    assert not nif_valido("1234567890")
    assert not nif_valido("12345678a")


# --- IBAN ----------------------------------------------------------------------------


def test_iban_exemplo_oficial_da_norma():
    exemplo = "GB82WEST12345698765432"  # dados-pessoais: permitido (exemplo da norma ISO 13616)
    assert iban_valido(exemplo)


def test_iban_valido_aceita_gerados():
    assert iban_valido(IBAN_PT)
    assert iban_valido(IBAN_ES)
    assert iban_valido(agrupar(IBAN_PT))


def test_iban_valido_rejeita_mod97_errado():
    errado = IBAN_PT[:-1] + str((int(IBAN_PT[-1]) + 1) % 10)
    assert not iban_valido(errado)


def test_iban_valido_rejeita_comprimento_errado_para_o_pais():
    curto = gerar_iban("PT", BBAN_PT[:-1])
    assert not iban_valido(curto)


# --- procurar no texto ---------------------------------------------------------------


def test_procura_nif_solto():
    achados = procurar_no_texto(f"O meu NIF é {NIF_SINGULAR}.")
    assert [(a.linha, a.tipo) for a in achados] == [(1, "NIF")]


def test_procura_nif_com_prefixo_pt():
    achados = procurar_no_texto(f"NIF: PT{NIF_COLETIVO}")
    assert [a.tipo for a in achados] == ["NIF"]


def test_procura_nif_agrupado_com_espacos():
    agrupado = f"{NIF_SINGULAR[:3]} {NIF_SINGULAR[3:6]} {NIF_SINGULAR[6:]}"
    assert [a.tipo for a in procurar_no_texto(f"contribuinte {agrupado}")] == ["NIF"]


def test_procura_nif_em_csv():
    assert [a.tipo for a in procurar_no_texto(f"nome,{NIF_SINGULAR},2026")] == ["NIF"]


def test_ignora_nif_com_controlo_errado():
    assert procurar_no_texto(f"valor {nif_com_controlo_errado('29876543')}") == []


def test_ignora_nove_digitos_dentro_de_numero_maior():
    assert procurar_no_texto(f"id 1{NIF_SINGULAR}") == []
    assert procurar_no_texto(f"id {NIF_SINGULAR}1") == []


def test_ignora_nove_digitos_colados_a_letras():
    assert procurar_no_texto(f"hash ab{NIF_SINGULAR}cd") == []


def test_ignora_casas_decimais():
    assert procurar_no_texto(f"pi = 3.{NIF_SINGULAR}") == []
    assert procurar_no_texto(f"taxa 0,{NIF_SINGULAR}") == []


def test_procura_iban_seguido_e_agrupado():
    texto = f"IBAN {IBAN_PT}\nou {agrupar(IBAN_PT)} OK"
    achados = procurar_no_texto(texto)
    assert [(a.linha, a.tipo) for a in achados] == [(1, "IBAN"), (2, "IBAN")]


def test_procura_iban_estrangeiro():
    assert [a.tipo for a in procurar_no_texto(f"conta {IBAN_ES}")] == ["IBAN"]


def test_ignora_iban_com_mod97_errado():
    errado = IBAN_PT[:-1] + str((int(IBAN_PT[-1]) + 1) % 10)
    assert procurar_no_texto(f"IBAN {errado}") == []


def test_ignora_iban_colado_a_mais_caracteres():
    assert procurar_no_texto(f"IBAN {IBAN_PT}9") == []


def test_iban_nao_gera_tambem_um_nif():
    assert [a.tipo for a in procurar_no_texto(IBAN_PT)] == ["IBAN"]


def test_marcador_permitido_salta_a_linha():
    texto = f"NIF da entidade {NIF_COLETIVO}  # {MARCADOR_PERMITIDO}\noutro {NIF_SINGULAR}"
    achados = procurar_no_texto(texto)
    assert [(a.linha, a.tipo) for a in achados] == [(2, "NIF")]


def test_valor_aparece_mascarado():
    (achado,) = procurar_no_texto(NIF_SINGULAR)
    assert NIF_SINGULAR not in achado.mascarado
    assert achado.mascarado == NIF_SINGULAR[:2] + "*" * 7
    (achado,) = procurar_no_texto(IBAN_PT)
    assert IBAN_PT not in achado.mascarado
    assert achado.mascarado.startswith("PT") and achado.mascarado.count("*") == 21


# --- ficheiros e linha de comandos ---------------------------------------------------


def test_verificar_ficheiro_salta_binarios(tmp_path):
    ficheiro = tmp_path / "imagem.png"
    ficheiro.write_bytes(b"\x89PNG\x00\x00" + NIF_SINGULAR.encode())
    assert verificar_ficheiro(ficheiro) == []


def test_verificar_ficheiro_inexistente_nao_falha(tmp_path):
    assert verificar_ficheiro(tmp_path / "apagado.txt") == []


def test_main_devolve_0_sem_achados(tmp_path, capsys):
    limpo = tmp_path / "limpo.md"
    limpo.write_text("Nada de dados pessoais aqui.\n", encoding="utf-8")
    assert main([str(limpo)]) == 0


def test_main_devolve_1_e_nao_imprime_o_valor(tmp_path, capsys):
    sujo = tmp_path / "sujo.py"
    sujo.write_text(f'nif = "{NIF_SINGULAR}"\niban = "{IBAN_PT}"\n', encoding="utf-8")
    assert main([str(sujo)]) == 1
    saida = capsys.readouterr()
    texto = saida.out + saida.err
    assert "sujo.py:1" in texto and "sujo.py:2" in texto
    assert NIF_SINGULAR not in texto and IBAN_PT not in texto


def test_main_todos_usa_os_ficheiros_do_git(tmp_path, monkeypatch, capsys):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "versionado.txt").write_text(f"{NIF_SINGULAR}\n", encoding="utf-8")
    (tmp_path / "fora_do_git.txt").write_text(f"{NIF_COLETIVO}\n", encoding="utf-8")
    subprocess.run(["git", "add", "versionado.txt"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    assert main(["--todos"]) == 1
    saida = capsys.readouterr()
    texto = saida.out + saida.err
    assert "versionado.txt:1" in texto
    assert "fora_do_git.txt" not in texto
