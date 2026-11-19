"""
Busca a posição no Athena para os títulos do dia (todas as bases de uma vez).

Por que todas as bases: o cruzamento com a CETIP é por conta + título, e a base de cada
linha vem da posição. Assim uma conta de BN7 que aparece no arquivo Operacoes não vira
"sem posição" no LZ. A tela mostra só as bases marcadas.
"""

import re

import pandas as pd

from app.worker import Falha
from .. import parametros as P
from .query_posicao import QUERY_POSICAO

# Colunas obrigatórias no retorno da query (em minúsculas)
COLUNAS = ["codigo_sistema", "sigla_carteira", "cd_cetip", "data_posicao",
           "codigo_operacao", "tipo_ativo", "clearing", "qtd_total"]

_SEGURO = re.compile(r"^[A-Z0-9]+$")


def janela_posicao(hoje=None) -> tuple[str, str]:
    """D-5 a D-1 dias úteis ANBIMA (P.DIAS_POSICAO), como texto aaaa-mm-dd."""
    from bizdays import Calendar

    cal = Calendar.load(name="ANBIMA")
    hoje = pd.Timestamp(hoje or pd.Timestamp.today()).normalize()
    ontem = (hoje - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    d_menos_1 = pd.Timestamp(cal.preceding(ontem))
    d_menos_n = pd.Timestamp(cal.offset(d_menos_1.strftime("%Y-%m-%d"), -(P.DIAS_POSICAO - 1)))
    return d_menos_n.strftime("%Y-%m-%d"), d_menos_1.strftime("%Y-%m-%d")


def montar_query(bases: list[str], titulos: list[str], data_de: str, data_ate: str) -> str:
    """Preenche a query. Bases e títulos só entram se forem letras e números (protege a query)."""
    for valor in list(bases) + list(titulos):
        if not _SEGURO.match(valor):
            raise Falha(f"Valor inválido para a query: {valor!r}")
    lista = lambda itens: ", ".join(f"'{v}'" for v in itens)  # noqa: E731
    return (QUERY_POSICAO
            .replace("{bases}", lista(bases))
            .replace("{titulos}", lista(titulos))
            .replace("{data_de}", data_de)
            .replace("{data_ate}", data_ate))


def executar_query(query: str) -> pd.DataFrame:
    """Roda a query pelo ODBC. A conexão é sempre fechada, mesmo com erro."""
    try:
        import pyodbc  # aqui dentro: a Central abre mesmo sem o driver instalado
    except ImportError:
        raise Falha("O pacote pyodbc não está instalado (pip install pyodbc).") from None

    conexao = None
    try:
        conexao = pyodbc.connect(f"DSN={P.DSN_ATHENA}", timeout=30)
        cursor = conexao.cursor()
        cursor.execute(query)
        colunas = [c[0] for c in cursor.description]
        linhas = cursor.fetchall()
        cursor.close()
        return pd.DataFrame.from_records(linhas, columns=colunas)
    except pyodbc.Error as exc:
        raise Falha(f"Erro no Athena: {exc}. Confira as credenciais na tela AWS.") from None
    finally:
        if conexao is not None:
            conexao.close()


def buscar_posicao(bases: list[str], titulos: list[str], ctx=None) -> tuple[pd.DataFrame, str]:
    """Devolve (posição com as colunas de COLUNAS, texto da janela usada)."""
    data_de, data_ate = janela_posicao()
    if ctx:
        ctx.log(f"Janela da posição: {pd.Timestamp(data_de):%d/%m} a {pd.Timestamp(data_ate):%d/%m} "
                f"({P.DIAS_POSICAO} dias úteis)", "step")
        ctx.log(f"Consultando {len(titulos)} título(s) nas bases {', '.join(bases)}...", "step")
    df = executar_query(montar_query(bases, titulos, data_de, data_ate))
    return normalizar(df), f"{pd.Timestamp(data_de):%d/%m} a {pd.Timestamp(data_ate):%d/%m}"


def normalizar(df: pd.DataFrame) -> pd.DataFrame:
    """Padroniza os nomes das colunas e confere se as obrigatórias vieram."""
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    faltando = [c for c in COLUNAS if c not in df.columns]
    if faltando:
        raise Falha(f"A query da posição não trouxe a(s) coluna(s): {', '.join(faltando)}. "
                    "Confira tasks/premio/aws/query_posicao.py.")
    return df
