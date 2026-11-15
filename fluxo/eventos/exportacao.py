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

import numpy as np
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


def resumo_em_linhas(resultado: tf.ResultadoProcessamento, info_execucao: dict | None = None) -> list[tuple]:
    """Resumo como lista de (seção, item, valor): base do terminal e da aba Resumo."""
    linhas = [("Execução", item, valor) for item, valor in (info_execucao or {}).items()]
    for secao, itens in resultado.resumo.items():
        linhas += [(secao, item, valor) for item, valor in itens.items()]
    return linhas


def formatar_resumo_terminal(resultado: tf.ResultadoProcessamento, info_execucao: dict | None = None) -> str:
    """Resumo pronto para imprimir no terminal (ou mostrar numa tela)."""
    linhas = resumo_em_linhas(resultado, info_execucao)
    largura = max(len(str(item)) for _, item, _ in linhas) + 3
    saida, secao_atual = ["=" * 60, "RESUMO DO PROCESSAMENTO", "=" * 60], None
    for secao, item, valor in linhas:
        if secao != secao_atual:
            saida.append(f"\n{secao.upper()}")
            secao_atual = secao
        saida.append(f"  {str(item).ljust(largura, '.')} {valor}")
    return "\n".join(saida)


def formatar_alerta_divergencias(resultado: tf.ResultadoProcessamento) -> str:
    """Aviso em destaque para o terminal quando há divergência na soma de I. Vazio se não houver."""
    v = resultado.validacao_lastros
    if v.empty:
        return ""
    erros = v[v["Status"] == tf.STATUS_ERRO]
    if erros.empty:
        return ""
    fora_txt = erros[erros[tf.COL_ABA] == tf.ABA_DIVERGENCIA]
    sem_alt = erros[erros[tf.COL_ABA] == "Fluxo Sem Alteração"]

    def linha(r):
        return (f"    lastro {r[tf.COL_LASTRO]} | ativo {r[tf.COL_ATIVO]} | "
                f"soma de I = {np.format_float_positional(float(r['Soma I Depois']), trim='-')}")

    saida = ["", "!" * 60, "ATENÇÃO: DIVERGÊNCIA NA SOMA DAS AMORTIZAÇÕES (I)", "!" * 60]
    if len(fora_txt):
        saida.append(f"{len(fora_txt)} lastro(s) RETIRADO(S) DO TXT "
                     f"(ver aba '{tf.ABA_DIVERGENCIA}' no Excel DEPOIS):")
        saida += [linha(r) for _, r in fora_txt.iterrows()]
    if len(sem_alt):
        saida.append(f"{len(sem_alt)} lastro(s) sem alteração já vêm com divergência da origem "
                     "(não sobem de qualquer forma):")
        saida += [linha(r) for _, r in sem_alt.iterrows()]
    saida.append("!" * 60)
    return "\n".join(saida)


def gerar_excels(
    df_query: pd.DataFrame,
    data_inicial,
    data_final,
    pasta_saida: str | Path = ".",
    levar_para_dia_util: bool = True,
    tipos_ativo: list[str] | None = None,
    excluir_compromissada: bool = True,
    info_execucao: dict | None = None,
) -> tuple[Path, Path, tf.ResultadoProcessamento]:
    """
    Aplica o tratamento ao DataFrame da query e salva:
        fluxo_ANTES_<ini>_a_<fim>.xlsx  -> dados como vieram da query
        fluxo_DEPOIS_<ini>_a_<fim>.xlsx -> fluxo tratado, fluxo sem alteração, validações e as
                                           abas dos lastros separados, log, diagnóstico, resumo
    tipos_ativo: lista dos tipos que ENTRAM na análise (None = sem filtro).
    info_execucao: itens extras para o topo do resumo (período, janela de posição, tipos...).
    Retorna (caminho_antes, caminho_depois, resultado).
    """
    from openpyxl.styles import PatternFill

    antes = tf.preparar_dados(df_query).reset_index(drop=True)  # só normaliza tipos
    resultado = tf.executar(df_query, data_inicial, data_final, levar_para_dia_util=levar_para_dia_util,
                            tipos_ativo=tipos_ativo, excluir_compromissada=excluir_compromissada)

    cores = {
        tf.MARCA_INCLUIDA: PatternFill("solid", fgColor="C6EFCE"),        # verde
        tf.MARCA_J_ALTERADO: PatternFill("solid", fgColor="FFEB9C"),      # amarelo
        tf.MARCA_DATA: PatternFill("solid", fgColor="BDD7EE"),            # azul
        tf.MARCA_EXCLUIDA: PatternFill("solid", fgColor="FFC7CE"),        # vermelho
        tf.MARCA_PENDENCIA: PatternFill("solid", fgColor="D9D9D9"),       # cinza
        tf.MARCA_COMPROMISSADA: PatternFill("solid", fgColor="F2CEEF"),   # rosa
        tf.MARCA_FORA_ANALISE: PatternFill("solid", fgColor="E4DFEC"),    # lilás
        tf.MARCA_VENCENDO: PatternFill("solid", fgColor="FCE4D6"),        # laranja
        tf.MARCA_TITULO_PUBLICO: PatternFill("solid", fgColor="DAEEF3"),  # azul-claro
    }
    legenda = pd.DataFrame([
        ("Verde", "Linha incluída pela rotina (I, ou J + I de lastro sem evento)"),
        ("Amarelo", f"J com percentual alterado para {MINIMO_TXT} "
                    "(a data também pode ter ido para o dia útil — ver log)"),
        ("Azul", "Fluxo Tratado: data levada para o dia útil (data cadastrada em data_evento_original). "
                 "Fluxo Sem Alteração: data em fim de semana/feriado, mantida (dia útil em "
                 "data_evento_ajustada, só para consulta)"),
        ("Vermelho", "ANTES: linha que será excluída (L ou B). Aba Validações: divergência na soma de I "
                     f"(se o lastro era do Fluxo Tratado, ele está na aba {tf.ABA_DIVERGENCIA} e fora do TXT)"),
        ("Cinza", "ANTES: lastro em pendência (abas Pendências e Fluxo Pendências)"),
        ("Rosa", "ANTES: compromissada (aba Compromissadas)"),
        ("Lilás", "ANTES: tipo de ativo não configurado (aba Fora da Análise)"),
        ("Laranja", "ANTES: vencendo no intervalo, sem atuação (aba Lastros Vencendo)"),
        ("Azul-claro", "ANTES: título público (aba Títulos Públicos)"),
    ], columns=["Cor", "Significado"])
    resumo = pd.DataFrame(resumo_em_linhas(resultado, info_execucao), columns=["Seção", "Item", "Valor"])

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
        _escrever_aba(excel, resultado.fluxo_sem_alteracao, "Fluxo Sem Alteração",
                      [cores.get(m) for m in resultado.marcas_sem_alteracao])
        _escrever_aba(excel, resultado.fluxo_divergencia, tf.ABA_DIVERGENCIA,
                      [cores.get(m) for m in resultado.marcas_divergencia])
        _escrever_validacoes(excel, resultado.validacao_consolidada, resultado.validacao_lastros,
                             cores[tf.MARCA_INCLUIDA], cores[tf.MARCA_EXCLUIDA])
        _escrever_aba(excel, resultado.pendencias, "Pendências")
        _escrever_aba(excel, resultado.fluxo_pendencias, "Fluxo Pendências")
        _escrever_aba(excel, resultado.fluxo_vencendo, "Lastros Vencendo")
        _escrever_aba(excel, resultado.fluxo_compromissadas, "Compromissadas")
        _escrever_aba(excel, resultado.fluxo_fora_analise, "Fora da Análise")
        _escrever_aba(excel, resultado.fluxo_titulos_publicos, "Títulos Públicos")
        _escrever_aba(excel, resultado.log_alteracoes, "Log de Alterações")
        _escrever_aba(excel, resultado.diagnostico, "Diagnóstico")
        _escrever_aba(excel, resumo, "Resumo")
        _escrever_aba(excel, legenda, "Legenda")

    return caminho_antes.resolve(), caminho_depois.resolve(), resultado


# ---------------------------------------------------------------------------
# Arquivo TXT de upload (só o Fluxo Tratado)
# ---------------------------------------------------------------------------
TXT_SEPARADOR = "\t"
TXT_QUEBRA_LINHA = "\r\n"          # Windows (CRLF)
TXT_CODIFICACAO = "utf-8"
TXT_PRIMEIRA_COLUNA = "E"
TXT_FORMATO_DATA = "%d/%m/%Y"


def _txt_lastro(valor) -> str:
    """Código do lastro como texto (sem '.0' se vier numérico)."""
    if isinstance(valor, (float, np.floating)) and float(valor).is_integer():
        return str(int(valor))
    return str(valor).strip()


def _txt_percentual(valor) -> str:
    """
    Percentual com ponto decimal. O mínimo sai em notação científica (ex.: 1e-14),
    como o sistema espera; os demais em decimal comum, sem zeros sobrando
    (100, 0.48, 0.486755057).
    """
    numero = float(valor)
    if numero == tf.PERCENTUAL_MINIMO:
        return repr(tf.PERCENTUAL_MINIMO)
    return np.format_float_positional(numero, trim="-")


def linhas_txt(fluxo: pd.DataFrame) -> list[str]:
    """Uma linha por evento: E, lastro, data, sigla do evento, percentual (sem cabeçalho)."""
    return [
        TXT_SEPARADOR.join([
            TXT_PRIMEIRA_COLUNA,
            _txt_lastro(lastro),
            pd.Timestamp(data).strftime(TXT_FORMATO_DATA),
            str(evento).strip(),
            _txt_percentual(percentual),
        ])
        for lastro, data, evento, percentual in zip(
            fluxo[tf.COL_LASTRO], fluxo[tf.COL_DATA], fluxo[tf.COL_EVENTO], fluxo[tf.COL_PERCENTUAL])
    ]


def gerar_arquivos_upload(
    resultado: tf.ResultadoProcessamento,
    data_inicial,
    data_final,
    pasta_upload: str | Path,
) -> list[Path]:
    """
    Gera o TXT de upload a partir do Fluxo Tratado (fluxo completo dos lastros
    com alteração). Um arquivo por base (sigla_sistema_origem), cada um na
    sua pasta:  <pasta_upload>/<BASE>/fluxo_<BASE>_<ini>_a_<fim>.txt
    Sem lastros tratados, nenhum arquivo é gerado.
    """
    fluxo = resultado.fluxo_tratado
    if fluxo.empty:
        return []

    sufixo = f"{pd.Timestamp(data_inicial):%Y-%m-%d}_a_{pd.Timestamp(data_final):%Y-%m-%d}"
    if tf.COL_SISTEMA in fluxo.columns:
        bases = fluxo[tf.COL_SISTEMA].fillna("SEM_BASE").astype(str).str.strip().replace("", "SEM_BASE")
    else:
        bases = pd.Series("SEM_BASE", index=fluxo.index)

    caminhos = []
    for base, parte in fluxo.groupby(bases, sort=True):
        pasta = Path(pasta_upload) / base
        pasta.mkdir(parents=True, exist_ok=True)
        caminho = pasta / f"fluxo_{base}_{sufixo}.txt"
        conteudo = TXT_QUEBRA_LINHA.join(linhas_txt(parte)) + TXT_QUEBRA_LINHA
        with open(caminho, "w", encoding=TXT_CODIFICACAO, newline="") as arquivo:
            arquivo.write(conteudo)
        caminhos.append(caminho.resolve())
    return caminhos
