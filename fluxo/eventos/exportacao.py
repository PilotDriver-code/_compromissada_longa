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

from eventos import tratamento_fluxo as tf

# Casas decimais dos percentuais: suficientes para mostrar o PERCENTUAL_MINIMO
_CASAS = max(10, len(f"{tf.PERCENTUAL_MINIMO:.20f}".rstrip("0").split(".")[1]))
FORMATO_PCT = "0." + "0" * _CASAS
MINIMO_TXT = f"{tf.PERCENTUAL_MINIMO:.{_CASAS}f}".replace(".", ",")


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
        if col == tf.COL_PERCENTUAL or str(col).startswith(("Percentual", "Soma", "Diferença")):
            formato = FORMATO_PCT
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


def _escrever_validacoes(excel, consolidado: dict, por_lastro: pd.DataFrame, cor_ok, cor_erro) -> None:
    """Aba Validações: bloco consolidado no topo e, abaixo, uma linha por lastro."""
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    nome = "Validações"
    formato_pct = FORMATO_PCT
    bloco = pd.DataFrame(list(consolidado.items()), columns=["Validação consolidada", "Valor"])
    bloco.to_excel(excel, sheet_name=nome, index=False, startrow=0)
    linha_cab = len(bloco) + 3                          # linha (1-based) do cabeçalho por lastro
    por_lastro.to_excel(excel, sheet_name=nome, index=False, startrow=linha_cab - 1)
    ws = excel.sheets[nome]

    for celula in ws[1]:
        celula.font = Font(bold=True)
    for celula in ws[linha_cab]:
        celula.font = Font(bold=True)

    for i, (item, valor) in enumerate(consolidado.items(), start=2):
        celula = ws.cell(i, 2)
        if item in ("Soma esperada", "Soma encontrada", "Diferença", "Tolerância usada"):
            celula.number_format = formato_pct
        if item == "Status":
            celula.fill = cor_ok if valor == tf.STATUS_OK else cor_erro
            celula.font = Font(bold=True)

    primeira, ultima = linha_cab + 1, linha_cab + len(por_lastro)
    for j, col in enumerate(por_lastro.columns, start=1):
        if str(col).startswith(("Soma", "Diferença")):
            for i in range(primeira, ultima + 1):
                ws.cell(i, j).number_format = formato_pct
    for k, status in enumerate(por_lastro["Status"]):
        if status == tf.STATUS_ERRO:
            for j in range(1, len(por_lastro.columns) + 1):
                ws.cell(primeira + k, j).fill = cor_erro

    for j in range(1, max(len(por_lastro.columns), 2) + 1):
        letra = get_column_letter(j)
        textos = [str(c.value) for c in ws[letra] if c.value is not None]
        ws.column_dimensions[letra].width = min(max([len(t) for t in textos] + [10]) + 3, 45)
    if len(por_lastro):
        ws.auto_filter.ref = f"A{linha_cab}:{get_column_letter(len(por_lastro.columns))}{ultima}"


def gerar_excels(
    df_query: pd.DataFrame,
    data_inicial,
    data_final,
    pasta_saida: str | Path = ".",
    levar_para_dia_util: bool = True,
    tipos_ativo: list[str] | None = None,
    excluir_compromissada: bool = True,
) -> tuple[Path, Path, tf.ResultadoProcessamento]:
    """
    Aplica o tratamento ao DataFrame da query e salva:
        fluxo_ANTES_<ini>_a_<fim>.xlsx  -> dados como vieram da query
        fluxo_DEPOIS_<ini>_a_<fim>.xlsx -> fluxo final + validações, pendências, vencendo,
                                           fora da análise, log, diagnóstico, resumo
    tipos_ativo: lista dos tipos que ENTRAM na análise (None = sem filtro).
    Retorna (caminho_antes, caminho_depois, resultado).
    """
    from openpyxl.styles import PatternFill

    antes = tf.preparar_dados(df_query).reset_index(drop=True)  # só normaliza tipos
    resultado = tf.executar(df_query, data_inicial, data_final, levar_para_dia_util=levar_para_dia_util,
                            tipos_ativo=tipos_ativo, excluir_compromissada=excluir_compromissada)

    cores = {
        tf.MARCA_INCLUIDA: PatternFill("solid", fgColor="C6EFCE"),    # verde
        tf.MARCA_J_ALTERADO: PatternFill("solid", fgColor="FFEB9C"),  # amarelo
        tf.MARCA_DATA: PatternFill("solid", fgColor="BDD7EE"),        # azul
        tf.MARCA_EXCLUIDA: PatternFill("solid", fgColor="FFC7CE"),    # vermelho
        tf.MARCA_PENDENCIA: PatternFill("solid", fgColor="D9D9D9"),   # cinza
        tf.MARCA_FORA_ANALISE: PatternFill("solid", fgColor="E4DFEC"),  # lilás
        tf.MARCA_VENCENDO: PatternFill("solid", fgColor="FCE4D6"),      # laranja
    }
    legenda = pd.DataFrame({
        "Cor": ["Verde", "Amarelo", "Azul", "Vermelho", "Cinza", "Lilás", "Laranja"],
        "Significado": [
            "Linha incluída pela rotina (I, ou J + I de lastro sem evento)",
            f"J com percentual alterado para {MINIMO_TXT} (a data também pode ter ido para o dia útil — ver log)",
            "Evento com data levada para o dia útil (data cadastrada em data_evento_original)",
            "Linha que será excluída (L ou B) — só aparece no arquivo ANTES. "
            "Na aba Validações: lastro com divergência na soma de I",
            "Lastro em pendência: fica fora do arquivo final (ver abas Pendências e Fluxo Pendências) "
            "— só aparece no arquivo ANTES",
            "Lastro fora da análise: tipo de ativo fora do filtro ou compromissada (ver aba Fora da Análise) "
            "— só aparece no arquivo ANTES",
            "Lastro vencendo no intervalo: sem atuação (ver aba Lastros Vencendo) — só aparece no arquivo ANTES",
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
        _escrever_validacoes(excel, resultado.validacao_consolidada, resultado.validacao_lastros,
                             cores[tf.MARCA_INCLUIDA], cores[tf.MARCA_EXCLUIDA])
        _escrever_aba(excel, resultado.pendencias, "Pendências")
        _escrever_aba(excel, resultado.fluxo_pendencias, "Fluxo Pendências")
        _escrever_aba(excel, resultado.fluxo_vencendo, "Lastros Vencendo")
        _escrever_aba(excel, resultado.fluxo_fora_analise, "Fora da Análise")
        _escrever_aba(excel, resultado.log_alteracoes, "Log de Alterações")
        _escrever_aba(excel, resultado.diagnostico, "Diagnóstico")
        _escrever_aba(excel, pd.DataFrame(list(resultado.resumo.items()), columns=["Item", "Valor"]), "Resumo")
        _escrever_aba(excel, legenda, "Legenda")

    return caminho_antes.resolve(), caminho_depois.resolve(), resultado
