import json
from pathlib import Path
import os
import pyodbc

class ErroDeCarga(Exception):
    """Falha que deve PARAR a execução (arquivos incoerentes), não virar saída."""


def header(titulo):
    largura = 100

    titulo_formatado = f" {titulo} "
    espaco_restante = largura - len(titulo_formatado)

    lado_esquerdo = espaco_restante // 2
    lado_direito = espaco_restante - lado_esquerdo

    print()
    print(("-=" * 30)[:lado_esquerdo] + titulo_formatado + ("-=" * 30)[:lado_direito])
    print("")


def limpar_terminal():
    """Limpa o terminal, independente do sistema operacional."""

    os.system('cls' if os.name in ('nt', 'dos') else 'clear')


def salvar_arquivo_xlsx (nome, df):
    """Salva um DataFrame em arquivo Excel (.xlsx) com o nome especificado."""

    caminho_arquivo = Path(nome).with_suffix('.xlsx')
    df.to_excel(caminho_arquivo, index=False)
    print(f"Arquivo salvo: {caminho_arquivo}")


def importar_configs(caminho):
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    return (
        dados["KEYS"]
    )


def executar_query_AWS(query, nome_colunas):


    return None