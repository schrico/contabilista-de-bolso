"""Verificador de dados pessoais: bloqueia NIFs e IBANs válidos antes de entrarem no git.

Corre no hook de pre-commit (recebe os ficheiros do commit) e no CI com ``--todos``
(varre todos os ficheiros versionados), porque o hook local pode ser saltado com
``--no-verify``.

Só apanha valores com dígito de controlo válido, para não bloquear qualquer número de
9 dígitos. Os valores encontrados nunca são impressos por inteiro: os logs do CI são
públicos.

Uma linha que tenha de levar um destes valores (por exemplo, o NIF público de uma
entidade) pode ser marcada com o texto ``dados-pessoais: permitido``.

Uso:
    python -m ferramentas.verificar_dados_pessoais FICHEIRO...
    python -m ferramentas.verificar_dados_pessoais --todos
"""

from __future__ import annotations

import argparse
import contextlib
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

MARCADOR_PERMITIDO = "dados-pessoais: permitido"

# Ficheiros gerados por ferramentas, sem dados escritos à mão.
FICHEIROS_IGNORADOS = frozenset({"uv.lock"})

# Prefixos de NIF atribuídos pela AT (primeiro dígito, ou dois primeiros dígitos).
_PREFIXOS_NIF_1 = frozenset("123568")
_PREFIXOS_NIF_2 = frozenset(
    {"45", "70", "71", "72", "74", "75", "77", "78", "79", "90", "91", "98", "99"}
)

# Comprimento total do IBAN por país (registo SWIFT da norma ISO 13616).
COMPRIMENTO_IBAN = {
    "AD": 24, "AE": 23, "AL": 28, "AT": 20, "AZ": 28, "BA": 20, "BE": 16, "BG": 22,
    "BH": 22, "BR": 29, "BY": 28, "CH": 21, "CR": 22, "CY": 28, "CZ": 24, "DE": 22,
    "DK": 18, "DO": 28, "EE": 20, "EG": 29, "ES": 24, "FI": 18, "FO": 18, "FR": 27,
    "GB": 22, "GE": 22, "GI": 23, "GL": 18, "GR": 27, "GT": 28, "HR": 21, "HU": 28,
    "IE": 22, "IL": 23, "IQ": 23, "IS": 26, "IT": 27, "JO": 30, "KW": 30, "KZ": 20,
    "LB": 28, "LC": 32, "LI": 21, "LT": 20, "LU": 20, "LV": 21, "MC": 27, "MD": 24,
    "ME": 22, "MK": 19, "MR": 27, "MT": 31, "MU": 30, "NL": 18, "NO": 15, "PK": 24,
    "PL": 28, "PS": 29, "PT": 25, "QA": 29, "RO": 24, "RS": 22, "SA": 24, "SC": 31,
    "SE": 24, "SI": 19, "SK": 24, "SM": 27, "ST": 25, "SV": 28, "TL": 23, "TN": 24,
    "TR": 26, "UA": 29, "VA": 22, "VG": 24, "XK": 20,
}  # fmt: skip
_IBAN_MIN, _IBAN_MAX = 15, 34

# 9 dígitos (opcionalmente "PT" antes, ou em grupos de 3), sem letras nem dígitos colados,
# e que não sejam casas decimais ("3.123..." ou "0,123...").
_RE_NIF = re.compile(r"(?<![0-9A-Za-z])(?<!\d[.,])(?:PT)?(\d{3} ?\d{3} ?\d{3})(?![0-9A-Za-z])")
# Início de um IBAN: código do país e dois dígitos de controlo, seguidos de mais caracteres.
_RE_INICIO_IBAN = re.compile(r"(?<![0-9A-Za-z])[A-Za-z]{2}\d{2}(?: ?[0-9A-Za-z])+")


@dataclass(frozen=True)
class Achado:
    linha: int
    tipo: str  # "NIF" ou "IBAN"
    mascarado: str


# --- validação -----------------------------------------------------------------------


def digito_controlo_nif(oito_digitos: str) -> int:
    """Dígito de controlo do NIF (módulo 11, pesos 9 a 2)."""
    soma = sum(int(d) * peso for d, peso in zip(oito_digitos, range(9, 1, -1), strict=True))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def nif_valido(nif: str) -> bool:
    if len(nif) != 9 or not nif.isdigit():
        return False
    if nif[0] not in _PREFIXOS_NIF_1 and nif[:2] not in _PREFIXOS_NIF_2:
        return False
    return int(nif[8]) == digito_controlo_nif(nif[:8])


def _iban_para_numero(texto: str) -> int:
    return int("".join(str(int(c, 36)) for c in texto))


def digitos_controlo_iban(pais: str, bban: str) -> str:
    """Dígitos de controlo do IBAN (ISO 7064, mod 97-10)."""
    return f"{98 - _iban_para_numero(bban + pais + '00') % 97:02d}"


def iban_valido(iban: str) -> bool:
    compacto = iban.replace(" ", "").upper()
    if not compacto.isalnum() or not compacto[:2].isalpha() or not compacto[2:4].isdigit():
        return False
    esperado = COMPRIMENTO_IBAN.get(compacto[:2])
    if esperado is not None and len(compacto) != esperado:
        return False
    if not _IBAN_MIN <= len(compacto) <= _IBAN_MAX:
        return False
    return _iban_para_numero(compacto[4:] + compacto[:4]) % 97 == 1


# --- procura -------------------------------------------------------------------------


def _mascarar(valor: str, visiveis: int) -> str:
    return valor[:visiveis] + "*" * (len(valor) - visiveis)


def _ibans_na_linha(linha: str) -> list[tuple[int, int, str]]:
    """Devolve (início, fim, iban compacto) de cada IBAN válido na linha."""
    encontrados = []
    for m in _RE_INICIO_IBAN.finditer(linha):
        pais = m.group()[:2].upper()
        comprimento = COMPRIMENTO_IBAN.get(pais)
        # Recolhe caracteres alfanuméricos (aceitando espaços simples entre eles) até
        # chegar ao comprimento do país; para países desconhecidos só aceita a forma seguida.
        recolhidos: list[str] = []
        fim = m.start()
        for i in range(m.start(), m.end()):
            c = linha[i]
            if c == " ":
                if comprimento is None:
                    break
                continue
            recolhidos.append(c)
            fim = i + 1
            if comprimento is not None and len(recolhidos) == comprimento:
                break
        # O IBAN não pode continuar colado a mais caracteres.
        if fim < len(linha) and linha[fim].isalnum():
            continue
        candidato = "".join(recolhidos)
        if iban_valido(candidato):
            encontrados.append((m.start(), fim, candidato.upper()))
    return encontrados


def procurar_no_texto(texto: str) -> list[Achado]:
    achados: list[Achado] = []
    for numero, linha in enumerate(texto.splitlines(), start=1):
        if MARCADOR_PERMITIDO in linha:
            continue
        ibans = _ibans_na_linha(linha)
        for _, _, iban in ibans:
            achados.append(Achado(numero, "IBAN", _mascarar(iban, 4)))
        for m in _RE_NIF.finditer(linha):
            if any(inicio < m.end() and m.start() < fim for inicio, fim, _ in ibans):
                continue
            nif = m.group(1).replace(" ", "")
            if nif_valido(nif):
                achados.append(Achado(numero, "NIF", _mascarar(nif, 2)))
    return achados


def verificar_ficheiro(caminho: Path) -> list[Achado]:
    try:
        conteudo = caminho.read_bytes()
    except (FileNotFoundError, IsADirectoryError, PermissionError):
        return []
    if b"\x00" in conteudo[:8192]:  # binário
        return []
    return procurar_no_texto(conteudo.decode("utf-8", errors="replace"))


def _ficheiros_do_git() -> list[str]:
    saida = subprocess.run(
        ["git", "ls-files", "-z"], capture_output=True, check=True
    ).stdout.decode("utf-8")
    return [f for f in saida.split("\0") if f]


# --- linha de comandos ---------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="verificar_dados_pessoais",
        description="Bloqueia NIFs e IBANs válidos em ficheiros do repositório.",
    )
    parser.add_argument("ficheiros", nargs="*", help="ficheiros a verificar")
    parser.add_argument(
        "--todos", action="store_true", help="verificar todos os ficheiros versionados no git"
    )
    args = parser.parse_args(argv)

    # No Windows o stderr de um pipe usa a página de código local e estraga os acentos.
    reconfigurar = getattr(sys.stderr, "reconfigure", None)
    if reconfigurar is not None:
        with contextlib.suppress(OSError, ValueError):
            reconfigurar(encoding="utf-8", errors="replace")

    ficheiros = _ficheiros_do_git() if args.todos else args.ficheiros
    total = 0
    for nome in ficheiros:
        if Path(nome).name in FICHEIROS_IGNORADOS:
            continue
        for achado in verificar_ficheiro(Path(nome)):
            total += 1
            print(
                f"{nome}:{achado.linha}: {achado.tipo} possível ({achado.mascarado})",
                file=sys.stderr,
            )

    if total:
        print(
            f"\n{total} possível(eis) dado(s) pessoal(is) encontrado(s). Usa só valores "
            "inventados.\nSe o valor for público e tiver de ficar (por exemplo o NIF de uma "
            f"entidade), acrescenta '{MARCADOR_PERMITIDO}' nessa linha.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
