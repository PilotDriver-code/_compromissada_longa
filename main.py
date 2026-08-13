from pathlib import Path

import pandas as pd

from services.GLOBAL_functions import limpar_terminal, ErroDeCarga, importar_configs, header, salvar_arquivo_xlsx

from services.REPASSE_pre_tratamento import pre_tratamento_REPASSE
from services.VCRAPRF_pre_tratamento import pre_tratamento_VCRAPRF


# ********* CONFIG DE CAMINHOS + VARIAVEL DE AMBIENTE -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=

PASTA_ATUAL = Path(__file__).resolve().parent

ARQUIVOS = {
    "REPASSE": PASTA_ATUAL / "data" / "REPASSE.xlsx",
    "CONFIG": PASTA_ATUAL / "config.json"
}

chaves_PROC = importar_configs(ARQUIVOS["CONFIG"])

limpar_terminal()

# ********* PRE TRATAMENTO DO REPASSE -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=--=-=-=

header("PRE-TRATAMENTO REPASSE")

df_repasse_pre = pre_tratamento_REPASSE(ARQUIVOS["REPASSE"])
salvar_arquivo_xlsx("./trash/PRE-TRATAMENTO-REPASSE", df_repasse_pre)

# ********* PRE TRATAMENTO DO VCRAPRF -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=--=-=-=

header("PRE-TRATAMENTO VCRA_POSICAO")

# df_VCRAPRF = pre_tratamento_VCRAPRF()
# salvar_arquivo_xlsx("./trash/PRE-TRATAMENTO-VCRAPRF", df_VCRAPRF)
