"""
Gera os Excel ANTES e DEPOIS a partir do DataFrame retornado pela query.

Uso:
    from exportacao import gerar_excels
    caminho_antes, caminho_depois, resultado = gerar_excels(df, "2026-11-07", "2026-11-10", "saida")

As datas devem ser as MESMAS usadas na query (data inicial e data final).

Cores:
    ANTES : vermelho = será excluída (L/B) | amarelo = J terá percentual alterado | azul = data irá para o dia útil
    DEPOIS: verde = incluída pela rotina   | amarelo = J com percentual alterado  | azul = data levada para o dia útil
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

import tratamento_fluxos as tf


def _escrever_aba(excel, df: pd.DataFrame, nome: str, cores: list | None = None) -> None:
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    df.to_excel(excel, sheet_name=nome, index=False)
    ws = excel.sheets[nome]
    for j, col in enumerate(df.columns, start=1):
        letra = get_column_letter(j)
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            textos = [str(col), "00/00/0000"]
        else:
            textos = [str(col)] + [str(v) for v in df[col].head(500) if pd.notna(v)]
        ws.column_dimensions[letra].width = min(max(len(t) for t in textos) + 3, 70)
        ws.cell(1, j).font = Font(bold=True)

        formato = None
        if col == tf.COL_PERCENTUAL or str(col).startswith("Percentual"):
            formato = "0.0000000000"
        elif pd.api.types.is_datetime64_any_dtype(df[col]):
            formato = "DD/MM/YYYY"
        if formato:
            for i in range(2, len(df) + 2):
                ws.cell(i, j).number_format = formato

    for i, cor in enumerate(cores or [], start=2):
        if cor is not None:
            for j in range(1, len(df.columns) + 1):
                ws.cell(i, j).fill = cor
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def gerar_excels(
    df_query: pd.DataFrame,
    data_inicial,
    data_final,
    pasta_saida: str | Path = ".",
    levar_para_dia_util: bool = True,
) -> tuple[Path, Path, tf.ResultadoProcessamento]:
    """
    Aplica o tratamento ao DataFrame da query e salva:
        fluxo_ANTES_<ini>_a_<fim>.xlsx  -> dados como vieram da query
        fluxo_DEPOIS_<ini>_a_<fim>.xlsx -> fluxo final + log, diagnóstico, pendências, resumo
    Retorna (caminho_antes, caminho_depois, resultado).
    """
    from openpyxl.styles import PatternFill

    antes = tf.preparar_dados(df_query).reset_index(drop=True)  # só normaliza tipos
    resultado = tf.executar(df_query, data_inicial, data_final, levar_para_dia_util=levar_para_dia_util)

    cores = {
        tf.MARCA_INCLUIDA: PatternFill("solid", fgColor="C6EFCE"),    # verde
        tf.MARCA_J_ALTERADO: PatternFill("solid", fgColor="FFEB9C"),  # amarelo
        tf.MARCA_DATA: PatternFill("solid", fgColor="BDD7EE"),        # azul
        tf.MARCA_EXCLUIDA: PatternFill("solid", fgColor="FFC7CE"),    # vermelho
    }
    legenda = pd.DataFrame({
        "Cor": ["Verde", "Amarelo", "Azul", "Vermelho"],
        "Significado": [
            "Linha incluída pela rotina (I, ou J + I de lastro sem evento)",
            "J com percentual alterado para 0,0000000001 (a data também pode ter ido para o dia útil — ver log)",
            "Evento com data levada para o dia útil (data cadastrada em data_evento_original)",
            "Linha que será excluída (L ou B) — só aparece no arquivo ANTES",
        ],
    })

    pasta = Path(pasta_saida)
    pasta.mkdir(parents=True, exist_ok=True)
    sufixo = f"{pd.Timestamp(data_inicial):%Y-%m-%d}_a_{pd.Timestamp(data_final):%Y-%m-%d}"
    caminho_antes = pasta / f"fluxo_ANTES_{sufixo}.xlsx"
    caminho_depois = pasta / f"fluxo_DEPOIS_{sufixo}.xlsx"

    with pd.ExcelWriter(caminho_antes, engine="openpyxl") as excel:
        _escrever_aba(excel, antes, "Fluxo Original", [cores.get(m) for m in resultado.marcas_antes])
        _escrever_aba(excel, legenda, "Legenda")

    with pd.ExcelWriter(caminho_depois, engine="openpyxl") as excel:
        _escrever_aba(excel, resultado.fluxo_tratado, "Fluxo Tratado",
                      [cores.get(m) for m in resultado.marcas_depois])
        _escrever_aba(excel, resultado.log_alteracoes, "Log de Alterações")
        _escrever_aba(excel, resultado.diagnostico, "Diagnóstico")
        _escrever_aba(excel, resultado.pendencias, "Pendências")
        _escrever_aba(excel, pd.DataFrame(list(resultado.resumo.items()), columns=["Item", "Valor"]), "Resumo")
        _escrever_aba(excel, legenda, "Legenda")

    return caminho_antes.resolve(), caminho_depois.resolve(), resultado
