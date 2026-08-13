import pandas as pd

from services.GLOBAL_functions import ErroDeCarga

# DATA ORIG. -=-=-=-=-=-  Data de aquisicao do ativo
# INIC. RET. -=-=-=-=-=-  Data de vencimento do ativo
# FACE/QT    -=-=-=-=-=-  Quantidade de ativos
# PU ORIG.   -=-=-=-=-=-  Preco de aquisicao do ativo

COLUNAS_OBRIGATORIAS = [
    "DATA ORIG.",
    "INIC. RET.",
    "FACE/QT",
    "PU ORIG.",
    "PU_REPASSE",
    "FINANCEIRO",
    "SIGLA_SAC",
]


def validar_colunas_obrigatorias(df):

    df.columns = df.columns.str.strip()
    colunas_df = df.columns.tolist()

    colunas_faltantes = [col for col in COLUNAS_OBRIGATORIAS if col not in colunas_df]

    if colunas_faltantes:
        raise ErroDeCarga(
            f"As seguintes colunas obrigatórias estão faltando no DataFrame: {', '.join(colunas_faltantes)}"
        )

    # Cria uma copia do DataFrame e apaga as colunas que não são obrigatórias
    df_copy = df.copy()
    df_copy = df_copy[COLUNAS_OBRIGATORIAS]

    return df_copy


def normalizar_data_int(series):
    return pd.to_datetime(
        series.astype("Int64").astype(str), format="%Y%m%d", errors="coerce"
    )


def normalizar_colunas(df_repasse):

    df_repasse["_sigla"] = df_repasse["SIGLA_SAC"].str.upper().str.strip()
    df_repasse["_dt_aqui"] = normalizar_data_int(df_repasse["DATA ORIG."])
    df_repasse["_dt_venc"] = normalizar_data_int(df_repasse["INIC. RET."])

    df_repasse["_qntd"] = pd.to_numeric(df_repasse["FACE/QT"], errors="coerce").astype("Int64")
    df_repasse["_pu_raw"] = pd.to_numeric(df_repasse["PU ORIG."], errors="coerce")


    

def pre_tratamento_REPASSE(caminho_REPASSE):

    try:
        df_repasse = pd.read_excel(caminho_REPASSE)
    except FileNotFoundError:
        raise ErroDeCarga(f"Arquivo não encontrado: {caminho_REPASSE}")

    df_repasse_att = validar_colunas_obrigatorias(df_repasse)

    normalizar_colunas(df_repasse_att)

    return df_repasse_att
