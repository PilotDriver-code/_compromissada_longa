"""
Rotina principal: monta e executa a query no Athena, trata o resultado e
gera os Excel ANTES e DEPOIS.

Só é preciso informar as datas do evento. A janela de posição
(D-7 a D-1 úteis ANBIMA da data inicial) é calculada automaticamente.

Como rodar (a partir da pasta raiz do projeto):
    python -m eventos.rodar
ou pelo botão "Run" do VS Code com este arquivo aberto.
"""

import sys
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
if str(RAIZ_PROJETO) not in sys.path:          # permite rodar o arquivo direto
    sys.path.insert(0, str(RAIZ_PROJETO))

import pandas as pd                             # noqa: E402
import pyodbc                                   # noqa: E402
from bizdays import Calendar                    # noqa: E402

from aws.query_eventos import QUERY_EVENTOS     # noqa: E402
from eventos.exportacao import gerar_excels     # noqa: E402

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
# Datas do evento (no futuro virão da tela)
DATA_INICIAL = "2026-11-10"
DATA_FINAL = "2026-11-10"

PASTA_SAIDA = RAIZ_PROJETO / "saida"
DSN_ATHENA = "AWS Athena ODBC"
DIAS_UTEIS_POSICAO = 7   # janela de posição: D-7 até D-1

# True  = eventos do intervalo em fim de semana/feriado vão para o próximo dia útil
#         (data cadastrada fica na coluna data_evento_original)
# False = mantém as datas cadastradas
LEVAR_PARA_DIA_UTIL = True


# ---------------------------------------------------------------------------
# Datas da query
# ---------------------------------------------------------------------------
def calcular_janela_posicao(data_inicial) -> tuple[pd.Timestamp, pd.Timestamp]:
    """
    D-7 a D-1 dias úteis ANBIMA da data inicial.
    Se a data inicial não for dia útil (ex.: sábado), o D-1 é o último dia útil antes dela.
    """
    cal = Calendar.load(name="ANBIMA")
    dia_anterior = (pd.Timestamp(data_inicial).normalize() - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    d_menos_1 = pd.Timestamp(cal.preceding(dia_anterior))
    d_menos_7 = pd.Timestamp(cal.offset(d_menos_1.strftime("%Y-%m-%d"), -(DIAS_UTEIS_POSICAO - 1)))
    return d_menos_7, d_menos_1


def montar_query(data_inicial, data_final) -> str:
    """Preenche a query com as datas do evento e a janela de posição."""
    ini = pd.Timestamp(data_inicial).normalize()
    fim = pd.Timestamp(data_final).normalize()
    if ini > fim:
        raise ValueError(f"Data inicial ({ini:%d/%m/%Y}) maior que a data final ({fim:%d/%m/%Y}).")

    posicao_de, posicao_ate = calcular_janela_posicao(ini)
    print(f"Eventos: {ini:%d/%m/%Y} a {fim:%d/%m/%Y} | "
          f"Posição: {posicao_de:%d/%m/%Y} a {posicao_ate:%d/%m/%Y}")

    um_dia = pd.Timedelta(days=1)
    return QUERY_EVENTOS.format(
        evento_de=f"{ini:%Y-%m-%d}",
        evento_ate_exclusivo=f"{fim + um_dia:%Y-%m-%d}",
        posicao_de=f"{posicao_de:%Y-%m-%d}",
        posicao_ate_exclusivo=f"{posicao_ate + um_dia:%Y-%m-%d}",
    )


# ---------------------------------------------------------------------------
# Athena
# ---------------------------------------------------------------------------
def executar_query_athena(query: str) -> pd.DataFrame | None:
    """Executa a query via ODBC (DSN configurado na máquina) e devolve um DataFrame."""
    try:
        connection = pyodbc.connect(f"DSN={DSN_ATHENA}", timeout=30)
        cursor = connection.cursor()
        cursor.execute(query)
        columns = [column[0] for column in cursor.description]
        results = cursor.fetchall()
        cursor.close()
        connection.close()
        return pd.DataFrame.from_records(results, columns=columns)
    except pyodbc.Error as e:
        print("Erro ao conectar ou executar a query:", e)
        return None


def obter_dados_athena(data_inicial, data_final) -> pd.DataFrame:
    """Monta a query com as datas, executa e devolve o DataFrame."""
    df = executar_query_athena(montar_query(data_inicial, data_final))
    if df is None:
        raise RuntimeError("A query no Athena falhou (ver mensagem de erro acima).")
    return df


# ---------------------------------------------------------------------------
# Rotina
# ---------------------------------------------------------------------------
def rodar(data_inicial: str, data_final: str) -> None:
    df = obter_dados_athena(data_inicial, data_final)
    print(f"Linhas recebidas da query: {len(df)}")

    caminho_antes, caminho_depois, resultado = gerar_excels(
        df, data_inicial, data_final, PASTA_SAIDA, levar_para_dia_util=LEVAR_PARA_DIA_UTIL
    )

    print("\n=== RESUMO ===")
    for item, valor in resultado.resumo.items():
        print(f"{item}: {valor}")
    print(f"\nExcel ANTES : {caminho_antes}")
    print(f"Excel DEPOIS: {caminho_depois}")


if __name__ == "__main__":
    rodar(DATA_INICIAL, DATA_FINAL)
