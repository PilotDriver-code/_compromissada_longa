"""
Rotina principal: executa a query no Athena (seu código), trata o resultado
e gera os Excel ANTES e DEPOIS.

Só é preciso preencher a função `obter_dados_athena` com o código que você
já usa para rodar a query e receber o DataFrame.
"""

import pandas as pd

from exportacao import gerar_excels

DATA_INICIAL = "2026-11-07"   # mesmas datas usadas na query
DATA_FINAL = "2026-11-10"
PASTA_SAIDA = "saida"

# True  = eventos do intervalo em fim de semana/feriado vão para o próximo dia útil
#         (data cadastrada fica na coluna data_evento_original)
# False = mantém as datas cadastradas
LEVAR_PARA_DIA_UTIL = True


def obter_dados_athena(data_inicial: str, data_final: str) -> pd.DataFrame:
    """
    >>> COLOQUE AQUI O SEU CÓDIGO QUE EXECUTA A QUERY NO ATHENA <<<

    Deve devolver o DataFrame com as colunas da query_fluxo_completo.sql:
    codigo_lastro, data_evento, sigla_evento, percentual_juros_evento,
    sigla_sistema_origem, tipo_ativo, data_vencimento, codigo_clearing, origem_selecao
    """
    raise NotImplementedError("Preencha obter_dados_athena com o código da sua query.")


if __name__ == "__main__":
    df = obter_dados_athena(DATA_INICIAL, DATA_FINAL)
    print(f"Linhas recebidas da query: {len(df)}")

    caminho_antes, caminho_depois, resultado = gerar_excels(
        df, DATA_INICIAL, DATA_FINAL, PASTA_SAIDA, levar_para_dia_util=LEVAR_PARA_DIA_UTIL
    )

    print("\n=== RESUMO ===")
    for item, valor in resultado.resumo.items():
        print(f"{item}: {valor}")
    print(f"\nExcel ANTES : {caminho_antes}")
    print(f"Excel DEPOIS: {caminho_depois}")
