"""
Leitura dos arquivos de operações da CETIP (Operacoes e operacoes_xz).

Formato: .txt separado por TAB, UTF-8 ou cp1252, decimal ".".
Colunas usadas: Conta, Tipo Operação, Título, Quantidade, PU, Valor, Data Liquidação (dd/mm/aaaa).
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

from app.worker import Falha
from . import parametros as P

# coluna interna -> nome no arquivo (já sem acento e em minúsculas)
COLUNAS = {
    "conta": "conta",
    "tipo": "tipo operacao",
    "titulo": "titulo",
    "qtd": "quantidade",
    "pu": "pu",
    "valor": "valor",
    "data_liq": "data liquidacao",
}

_TITULO_OK = re.compile(r"^[A-Z0-9]+$")


@dataclass
class LinhaCetip:
    arquivo: str          # base do arquivo de onde veio: LZ (Operacoes) ou XZ (operacoes_xz)
    linha: int            # número da linha no arquivo (1 = cabeçalho)
    conta: str            # só os dígitos: 2385400-6 -> 23854006
    conta_fmt: str        # como veio no arquivo
    titulo: str
    qtd: Decimal
    pu: Decimal
    valor: Decimal
    data_liq: date


@dataclass
class Leitura:
    caminho: Path
    arquivo: str
    linhas: list            # LinhaCetip de prêmio, válidas
    invalidas: list         # (linha, motivo)
    variacoes: dict         # "PAGAMENTO DE PREMIO DETENTOR" -> quantidade (ficaram de fora)
    total_linhas: int


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def sem_acento(texto) -> str:
    txt = unicodedata.normalize("NFKD", str(texto))
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", txt).strip().upper()


def para_decimal(texto) -> Decimal:
    """Converte o texto do arquivo em Decimal, sem passar por float. Decimal "." (aceita "," também)."""
    s = str(texto).strip().replace(" ", "")
    if not s:
        raise InvalidOperation
    if "," in s and "." in s:      # 1.234,56 -> 1234.56
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:                  # 1234,56 -> 1234.56
        s = s.replace(",", ".")
    valor = Decimal(s)
    if not valor.is_finite():
        raise InvalidOperation
    return valor


def so_digitos(conta) -> str:
    """2385400-6 -> 23854006; 23854006.0 -> 23854006."""
    s = str(conta).strip()
    if re.fullmatch(r"\d+\.0+", s):
        s = s.split(".")[0]
    return re.sub(r"\D", "", s)


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------
def _ler_tabela(caminho: Path) -> pd.DataFrame:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return pd.read_csv(caminho, sep="\t", dtype=str, keep_default_na=False, encoding=enc)
        except UnicodeDecodeError:
            continue
        except PermissionError:
            raise Falha(f"Não foi possível abrir {caminho.name}. Se ele estiver aberto, feche e tente de novo.") from None
    raise Falha(f"{caminho.name}: não consegui ler o arquivo (nem UTF-8 nem cp1252).")


def ler_operacoes(caminho, arquivo: str) -> Leitura:
    """Lê um arquivo de operações e devolve só as linhas de PAGAMENTO DE PRÊMIO, já validadas."""
    caminho = Path(caminho)
    if not caminho.is_file():
        raise Falha(f"Arquivo de operações não encontrado: {caminho}")
    df = _ler_tabela(caminho)

    # acha as colunas pelo nome, sem acento e sem diferenciar maiúsculas
    por_nome = {sem_acento(c).lower(): c for c in df.columns}
    faltando = [nome for nome in COLUNAS.values() if nome not in por_nome]
    if faltando:
        raise Falha(f"{caminho.name}: faltam as colunas {', '.join(faltando)}. "
                    f"Colunas do arquivo: {', '.join(map(str, df.columns))}")
    col = {interna: por_nome[nome] for interna, nome in COLUNAS.items()}

    eventos = {sem_acento(t) for t in P.TIPOS_EVENTO}
    linhas, invalidas, variacoes = [], [], {}
    for i, reg in enumerate(df.to_dict("records"), start=2):
        tipo = sem_acento(reg[col["tipo"]])
        if tipo not in eventos:
            if any(tipo.startswith(e) for e in eventos):
                variacoes[tipo] = variacoes.get(tipo, 0) + 1
            continue
        try:
            titulo = sem_acento(reg[col["titulo"]]).replace(" ", "")
            if not _TITULO_OK.match(titulo):
                raise ValueError(f"título inválido ({reg[col['titulo']]!r})")
            conta = so_digitos(reg[col["conta"]])
            if not conta:
                raise ValueError(f"conta inválida ({reg[col['conta']]!r})")
            campos = {}
            for nome in ("qtd", "pu", "valor"):
                try:
                    campos[nome] = para_decimal(reg[col[nome]])
                except (InvalidOperation, ValueError):
                    raise ValueError(f"{nome} inválido ({reg[col[nome]]!r})") from None
            try:
                data_liq = datetime.strptime(str(reg[col["data_liq"]]).strip(), "%d/%m/%Y").date()
            except ValueError:
                raise ValueError(f"data de liquidação inválida ({reg[col['data_liq']]!r})") from None
            if campos["qtd"] <= 0 or campos["pu"] <= 0 or campos["valor"] <= 0:
                raise ValueError("quantidade, PU e valor precisam ser maiores que zero")
        except ValueError as exc:
            invalidas.append((i, str(exc)))
            continue
        linhas.append(LinhaCetip(arquivo, i, conta, str(reg[col["conta"]]).strip(), titulo,
                                 campos["qtd"], campos["pu"], campos["valor"], data_liq))

    return Leitura(caminho, arquivo, linhas, invalidas, variacoes, len(df))
