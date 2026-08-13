import pandas as pd

from services.GLOBAL_functions import executar_query_AWS


query_AWS = f"""

SELECT * from EVENTOS

"""


def consulta_eventos():

    df = executar_query_AWS(query_AWS, nome_colunas=None)

    return df