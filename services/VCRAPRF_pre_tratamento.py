import pandas as pd

from services.GLOBAL_functions import executar_query_AWS


query_AWS = f"""

SELECT * from VCRA_POSICAO

"""


def pre_tratamento_VCRAPRF():

    df = executar_query_AWS(query_AWS, nome_colunas=None)

    return df