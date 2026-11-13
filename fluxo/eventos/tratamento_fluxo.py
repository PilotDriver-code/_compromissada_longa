"""
Tratamento de Fluxos de Ativos — lógica Python sobre o resultado da query.

Entrada: DataFrame com o resultado de `aws/query_eventos.py` (Athena),
mais a data inicial e a data final usadas na query.

REGRAS
------
R0. Intervalo e dia útil
    - Só são tratados os eventos cadastrados entre a data inicial e a data
      final (inclusive). As demais datas do fluxo ficam como estão.
    - Cada evento é associado ao seu dia útil: a própria data se for dia útil
      ANBIMA; se for fim de semana ou feriado, o próximo dia útil.
    - Por lastro, os eventos do MESMO dia útil são analisados juntos
      (ex.: sáb + dom + seg). Dias úteis diferentes são analisados separados.

Para cada grupo (lastro + codigo_clearing + dia útil):
R1. Eventos L e B são sempre excluídos.
R2. O grupo sempre termina com um I. Se não houver, inclui-se um I com
    0,00000000000001. Se já houver, nada é incluído e ele mantém seu percentual.
R3. Se havia L ou B e existe J, o percentual do J vai para 0,00000000000001.
    M é sempre mantido.
R4. A nova linha I copia a linha J do grupo. Sem J, copia a primeira linha
    do grupo.

Lastro irmão sem evento:
R5. Para cada ativo (codigo_clearing) e dia útil em que algum lastro dele tem
    evento, todo outro lastro do mesmo ativo presente nos dados que não tenha
    evento nesse dia útil recebe J + I, ambos com 0,00000000000001.
    Demais colunas: do cadastro do próprio lastro.
    (A exigência de posição para os dois lastros já é aplicada na query.)

Data das linhas (opção `levar_para_dia_util`):
R9. Ligada (padrão):
      - Eventos do intervalo que caem em fim de semana/feriado passam a ter a
        data do dia útil (ex.: J de sáb 07/11 -> 09/11). Fica registrado no
        log como ALTERACAO_DATA.
      - Linhas novas (I e J + I) nascem com a data do dia útil.
      - Coluna `data_evento_original` guarda a data cadastrada (vazia nas
        linhas incluídas pela rotina).
    Desligada:
      - Datas cadastradas são mantidas.
      - Linha nova I usa a data do J copiado; o par J + I usa a data do J do
        irmão (o mais antigo) ou, sem J, a do primeiro evento do irmão.

Pendências — o lastro INTEIRO fica fora do fluxo final, sem nenhuma
alteração (nem data), e não recebe par J + I como irmão:
R6. Evento repetido no mesmo grupo (não deveria ocorrer: erro de dados).
R7. Código de evento fora de I, J, M, L, B.
R8. Lastro sem codigo_clearing (sem cadastro).
    Basta uma pendência em um dia útil para o lastro todo sair.

Fora da análise e vencendo — o lastro INTEIRO fica fora do tratamento e do
fluxo final, sem nenhuma alteração, e não recebe nem gera par J + I:
R11. tipo_ativo fora da lista configurada (config/filtros.json: tipos que ENTRAM).
R12. indicador_compromissada = 'S' (cadastro do lastro).
     R11 e R12 vão para a aba "Fora da Análise", com o motivo.
R13. data_vencimento dentro do intervalo do evento: lastro vencendo, não é
     erro e não precisa de atuação -> aba "Lastros Vencendo".
     Lastros sem cadastro continuam como pendência (R8).

Validação de amortização (após todo o tratamento):
R10. Para cada lastro do fluxo final, a soma do percentual de TODOS os
     eventos I (fluxo completo) deve ser 100, com tolerância de 0,000001
     (os I de 0,00000000000001 não pesam). Consolidado: soma de todos os lastros
     = quantidade de lastros x 100. Lastros em pendência não entram.
     Nada é ajustado: divergências só são sinalizadas.

Saída:
- Fluxo tratado = fluxo FINAL completo dos lastros que sobem para o arquivo
  (eventos excluídos não aparecem; ficam só no log).
- Fluxo das pendências (como veio da query), validação por lastro e
  consolidada.
- Log de alterações, diagnóstico por grupo, pendências e resumo.
- Percentuais em pontos percentuais (100 = 100%).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import pandas as pd

# ---------------------------------------------------------------------------
# Colunas (mesmos nomes da query)
# ---------------------------------------------------------------------------
COL_LASTRO = "codigo_lastro"
COL_DATA = "data_evento"
COL_EVENTO = "sigla_evento"
COL_PERCENTUAL = "percentual_juros_evento"
COL_SISTEMA = "sigla_sistema_origem"
COL_TIPO = "tipo_ativo"
COL_VENCIMENTO = "data_vencimento"
COL_ATIVO = "codigo_clearing"
COL_ORIGEM = "origem_selecao"
COL_COMPROMISSADA = "indicador_compromissada"
COL_DATA_ORIGINAL = "data_evento_original"   # criada quando levar_para_dia_util=True
COL_MOTIVO = "Motivo"                         # aba Fora da Análise

COLUNAS_OBRIGATORIAS = [COL_LASTRO, COL_DATA, COL_EVENTO, COL_PERCENTUAL, COL_ATIVO]
# Colunas que descrevem o evento; todas as outras são dados do lastro (cadastro).
COLUNAS_DO_EVENTO = [COL_DATA, COL_EVENTO, COL_PERCENTUAL]

# Identificação do ativo/lastro.
CHAVE_ATIVO = [COL_LASTRO, COL_ATIVO]

# Colunas internas (removidas da saída)
_ORDEM = "_ordem"
_DIA_UTIL = "_dia_util"
_MARCA = "_marca"

PERCENTUAL_MINIMO = 1e-14

EVENTO_I, EVENTO_J, EVENTO_M, EVENTO_L, EVENTO_B = "I", "J", "M", "L", "B"
EVENTOS_CONHECIDOS = {EVENTO_I, EVENTO_J, EVENTO_M, EVENTO_L, EVENTO_B}
EVENTOS_EXCLUIDOS = {EVENTO_L, EVENTO_B}

CASO_1 = "CASO_1"  # J            -> inclui I
CASO_2 = "CASO_2"  # J + M        -> inclui I
CASO_3 = "CASO_3"  # I + J (+ M)  -> sem alteração de eventos
CASO_4 = "CASO_4"  # J + L + B    -> exclui L e B, J = mínimo, inclui I
CASO_5 = "CASO_5"  # J + L        -> exclui L, J = mínimo, inclui I
REGRA_GERAL = "REGRA_GERAL"              # outra combinação, tratada por R1-R3
LASTRO_SEM_EVENTO = "LASTRO_SEM_EVENTO"  # R5
PENDENCIA = "PENDENCIA"

CASOS_DOCUMENTADOS: dict[frozenset[str], str] = {
    frozenset({EVENTO_J}): CASO_1,
    frozenset({EVENTO_J, EVENTO_M}): CASO_2,
    frozenset({EVENTO_I, EVENTO_J}): CASO_3,
    frozenset({EVENTO_I, EVENTO_J, EVENTO_M}): CASO_3,
    frozenset({EVENTO_J, EVENTO_L, EVENTO_B}): CASO_4,
    frozenset({EVENTO_J, EVENTO_L}): CASO_5,
}

# Validação de amortização
PERCENTUAL_TOTAL = 100.0
TOLERANCIA_AMORTIZACAO = 1e-6    # pontos percentuais, por lastro
STATUS_OK, STATUS_ERRO = "OK", "ERRO"

TIPO_INCLUSAO = "INCLUSAO"
TIPO_EXCLUSAO = "EXCLUSAO"
TIPO_ALTERACAO = "ALTERACAO_PERCENTUAL"
TIPO_ALTERACAO_DATA = "ALTERACAO_DATA"

# Marcas por linha (usadas para colorir o Excel)
MARCA_INCLUIDA = "incluida"
MARCA_EXCLUIDA = "excluida"
MARCA_J_ALTERADO = "j_alterado"
MARCA_DATA = "data_alterada"
MARCA_PENDENCIA = "pendencia"
MARCA_FORA_ANALISE = "fora_analise"
MARCA_VENCENDO = "vencendo"

COL_LOG_DIA_UTIL = "Dia Útil"
COLUNAS_LOG = [
    COL_ATIVO, COL_LASTRO, "Data Original", "Data Final", COL_LOG_DIA_UTIL, "Caso",
    "Tipo de Alteração", "Evento Original", "Evento Final", "Percentual Original", "Percentual Final",
]
COLUNAS_DIAGNOSTICO = [
    COL_ATIVO, COL_LASTRO, COL_LOG_DIA_UTIL, "Datas Cadastradas",
    "Eventos Originais", "Eventos Finais", "Caso", "Ações", "Observação",
]


# ---------------------------------------------------------------------------
# Calendário
# ---------------------------------------------------------------------------
class Calendario(Protocol):
    def proximo_dia_util(self, data: pd.Timestamp) -> pd.Timestamp: ...


class CalendarioANBIMA:
    """Calendário de dias úteis ANBIMA (biblioteca `bizdays`)."""

    def __init__(self) -> None:
        from bizdays import Calendar
        self._cal = Calendar.load(name="ANBIMA")

    def proximo_dia_util(self, data: pd.Timestamp) -> pd.Timestamp:
        """A própria data, se for dia útil; senão, o próximo dia útil."""
        return pd.Timestamp(self._cal.following(pd.Timestamp(data).strftime("%Y-%m-%d")))


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------
@dataclass
class ResultadoProcessamento:
    fluxo_tratado: pd.DataFrame
    log_alteracoes: pd.DataFrame
    diagnostico: pd.DataFrame
    pendencias: pd.DataFrame
    fluxo_pendencias: pd.DataFrame = field(default_factory=pd.DataFrame)  # fluxo dos lastros em pendência
    fluxo_fora_analise: pd.DataFrame = field(default_factory=pd.DataFrame)  # tipo fora do filtro / compromissada
    fluxo_vencendo: pd.DataFrame = field(default_factory=pd.DataFrame)      # vencimento dentro do intervalo
    filtros: dict = field(default_factory=dict)                             # quais filtros foram aplicados
    validacao_lastros: pd.DataFrame = field(default_factory=pd.DataFrame)
    validacao_consolidada: dict = field(default_factory=dict)
    resumo: dict = field(default_factory=dict)
    # Marca de cada linha (para colorir o Excel):
    #   marcas_antes  -> alinhada às linhas do DataFrame de entrada (mesma ordem)
    #   marcas_depois -> alinhada às linhas de fluxo_tratado
    marcas_antes: list = field(default_factory=list)
    marcas_depois: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Preparação
# ---------------------------------------------------------------------------
def _eh_linha_vazia(df: pd.DataFrame) -> pd.Series:
    """Linha de lastro sem nenhum evento (vem da query só com dados de cadastro)."""
    return df[COLUNAS_DO_EVENTO].isna().all(axis=1)


def preparar_dados(df: pd.DataFrame) -> pd.DataFrame:
    """Valida a estrutura e normaliza tipos, sem alterar conteúdo de negócio."""
    faltantes = [c for c in COLUNAS_OBRIGATORIAS if c not in df.columns]
    if faltantes:
        raise ValueError(f"Colunas obrigatórias ausentes: {faltantes}")

    dados = df.copy()
    dados[COL_EVENTO] = dados[COL_EVENTO].astype("string").str.strip().str.upper()
    dados[COL_DATA] = pd.to_datetime(dados[COL_DATA])
    if dados[COL_DATA].dt.tz is not None:          # timestamp com fuso -> sem fuso
        dados[COL_DATA] = dados[COL_DATA].dt.tz_localize(None)
    # o Athena pode devolver DECIMAL como objetos Decimal -> float
    dados[COL_PERCENTUAL] = pd.to_numeric(
        dados[COL_PERCENTUAL].map(lambda v: float(v) if v is not None and pd.notna(v) else None),
        errors="raise",
    ).astype(float)

    if dados[COL_LASTRO].isna().any():
        raise ValueError("Existem linhas sem codigo_lastro.")

    vazia = _eh_linha_vazia(dados)
    incompleta = dados[[COL_DATA, COL_EVENTO]].isna().any(axis=1) & ~vazia
    if incompleta.any():
        raise ValueError(
            "Linhas com evento incompleto (data ou sigla vazia): "
            f"{list(dados.index[incompleta])}"
        )
    return dados


# ---------------------------------------------------------------------------
# Regras de grupo
# ---------------------------------------------------------------------------
def classificar_grupo(eventos: list[str]) -> tuple[str, str]:
    """Classifica os eventos de um grupo. Retorna (caso, motivo)."""
    desconhecidos = sorted(set(eventos) - EVENTOS_CONHECIDOS)
    if desconhecidos:
        return PENDENCIA, f"Evento(s) desconhecido(s): {desconhecidos}"

    repetidos = sorted({e for e in eventos if eventos.count(e) > 1})
    if repetidos:
        return PENDENCIA, f"Evento(s) repetido(s) no mesmo dia útil (verificar dados): {repetidos}"

    return CASOS_DOCUMENTADOS.get(frozenset(eventos), REGRA_GERAL), ""


def _entrada_log(linha, dia_util, caso, tipo, data_orig, data_final,
                 ev_orig, ev_final, perc_orig=None, perc_final=None) -> dict:
    return {
        COL_ATIVO: linha[COL_ATIVO],
        COL_LASTRO: linha[COL_LASTRO],
        "Data Original": data_orig,
        "Data Final": data_final,
        COL_LOG_DIA_UTIL: dia_util,
        "Caso": caso,
        "Tipo de Alteração": tipo,
        "Evento Original": ev_orig,
        "Evento Final": ev_final,
        "Percentual Original": perc_orig,
        "Percentual Final": perc_final,
    }


def _datas_txt(datas) -> str:
    return ", ".join(sorted({pd.Timestamp(d).strftime("%d/%m/%Y") for d in datas}))


def _nova_linha(modelo: pd.Series, data, evento: str, ordem: float) -> dict:
    nova = modelo.to_dict()
    nova[COL_DATA] = data
    nova[COL_EVENTO] = evento
    nova[COL_PERCENTUAL] = PERCENTUAL_MINIMO
    nova[COL_DATA_ORIGINAL] = pd.NaT
    nova[_ORDEM] = ordem
    nova[_MARCA] = MARCA_INCLUIDA
    return nova


# ---------------------------------------------------------------------------
# Separação: fora da análise e vencendo
# ---------------------------------------------------------------------------
def _separar_lastros(trabalho, ini, fim, tipos_ativo, excluir_compromissada):
    """
    Decide, por lastro, quem NÃO passa pelo tratamento:
      - fora da análise: tipo_ativo fora da lista configurada, ou
        indicador_compromissada = 'S';
      - vencendo: data_vencimento dentro do intervalo do evento.
    Lastros sem cadastro (sem codigo_clearing) não entram aqui: continuam
    como pendência (R8).
    Retorna (motivos_fora {lastro: motivo}, lastros_vencendo {set}, filtros {dict}).
    """
    cadastro = trabalho[trabalho[COL_ATIVO].notna()].drop_duplicates(COL_LASTRO).set_index(COL_LASTRO)
    filtros = {}

    tipos = None
    if tipos_ativo is not None:
        if COL_TIPO not in trabalho.columns:
            raise ValueError(f"Filtro de tipos configurado, mas a coluna {COL_TIPO} não veio na query.")
        tipos = {str(t).strip() for t in tipos_ativo}
        filtros["Filtro de tipos de ativo"] = f"aplicado ({', '.join(sorted(tipos))})"
    else:
        filtros["Filtro de tipos de ativo"] = "não aplicado"

    aplicar_compromissada = excluir_compromissada and COL_COMPROMISSADA in trabalho.columns
    if excluir_compromissada and not aplicar_compromissada:
        print(f"ATENÇÃO: a coluna {COL_COMPROMISSADA} não veio na query; "
              "o filtro de compromissada NÃO foi aplicado.")
    filtros["Filtro de compromissada"] = ("aplicado" if aplicar_compromissada
                                          else "NÃO aplicado (coluna ausente)" if excluir_compromissada
                                          else "não aplicado")

    motivos_fora: dict = {}
    for lastro, linha in cadastro.iterrows():
        motivos = []
        if tipos is not None:
            tipo = linha[COL_TIPO]
            if pd.isna(tipo) or str(tipo).strip() not in tipos:
                motivos.append(f"tipo_ativo '{tipo}' fora do filtro")
        if aplicar_compromissada and str(linha[COL_COMPROMISSADA]).strip().upper() == "S":
            motivos.append("compromissada (indicador_compromissada = S)")
        if motivos:
            motivos_fora[lastro] = "; ".join(motivos)

    lastros_vencendo: set = set()
    if COL_VENCIMENTO in trabalho.columns:
        venc = pd.to_datetime(cadastro[COL_VENCIMENTO], errors="coerce").dt.normalize()
        no_intervalo = venc.between(ini, fim) & ~venc.index.isin(list(motivos_fora))
        lastros_vencendo = set(venc.index[no_intervalo])
    else:
        print(f"ATENÇÃO: a coluna {COL_VENCIMENTO} não veio na query; lastros vencendo não foram separados.")

    return motivos_fora, lastros_vencendo, filtros


# ---------------------------------------------------------------------------
# Processamento
# ---------------------------------------------------------------------------
def processar_eventos(
    dados: pd.DataFrame,
    data_inicial,
    data_final,
    calendario: Calendario | None = None,
    levar_para_dia_util: bool = True,
    tipos_ativo: list[str] | None = None,
    excluir_compromissada: bool = True,
) -> ResultadoProcessamento:
    ini = pd.Timestamp(data_inicial).normalize()
    fim = pd.Timestamp(data_final).normalize()
    if ini > fim:
        raise ValueError("A data inicial é maior que a data final.")
    calendario = calendario or CalendarioANBIMA()

    trabalho = dados.reset_index(drop=True)  # posição = ordem das linhas de entrada
    trabalho[_ORDEM] = range(len(trabalho))
    trabalho[_MARCA] = None
    trabalho[COL_DATA_ORIGINAL] = trabalho[COL_DATA]
    vazia = _eh_linha_vazia(trabalho)
    sem_ativo = trabalho[COL_ATIVO].isna()

    # --- R11/R12: fora da análise (tipo fora do filtro / compromissada) -----
    # --- R13: lastros vencendo no intervalo ---------------------------------
    motivos_fora, lastros_vencendo, filtros = _separar_lastros(
        trabalho, ini, fim, tipos_ativo, excluir_compromissada)
    fora_do_tratamento = trabalho[COL_LASTRO].isin(set(motivos_fora) | lastros_vencendo)

    no_intervalo = trabalho[
        ~vazia & ~fora_do_tratamento & trabalho[COL_DATA].dt.normalize().between(ini, fim)
    ].copy()
    mapa_dia_util = {d: calendario.proximo_dia_util(d) for d in no_intervalo[COL_DATA].dt.normalize().unique()}
    no_intervalo[_DIA_UTIL] = no_intervalo[COL_DATA].dt.normalize().map(mapa_dia_util)

    indices_excluir: list = []
    alteracoes_percentual: dict = {}
    alteracoes_data: dict = {}
    novas_linhas: list[dict] = []
    log: list[dict] = []
    diagnostico: list[dict] = []

    # --- R8: lastros sem codigo_clearing -> pendência, sem alteração --------
    for lastro, _ in trabalho[sem_ativo].groupby(COL_LASTRO, sort=False):
        ev = no_intervalo[no_intervalo[COL_LASTRO] == lastro]
        diagnostico.append({
            COL_ATIVO: None, COL_LASTRO: lastro, COL_LOG_DIA_UTIL: None,
            "Datas Cadastradas": _datas_txt(ev[COL_DATA]),
            "Eventos Originais": "+".join(sorted(ev[COL_EVENTO])),
            "Eventos Finais": "+".join(sorted(ev[COL_EVENTO])),
            "Caso": PENDENCIA, "Ações": "nenhuma",
            "Observação": "Lastro sem codigo_clearing (sem cadastro)",
        })

    grupos_validos = no_intervalo[no_intervalo[COL_ATIVO].notna()]

    # --- Pendência vale para o lastro INTEIRO: ele sai do fluxo final -------
    lastros_pendencia: set = set(trabalho.loc[sem_ativo, COL_LASTRO])
    classificacao: dict = {}
    for chave, grupo in grupos_validos.groupby(CHAVE_ATIVO + [_DIA_UTIL], sort=False):
        classificacao[chave] = classificar_grupo(grupo[COL_EVENTO].tolist())
        if classificacao[chave][0] == PENDENCIA:
            lastros_pendencia.add(chave[0])

    # --- R1-R4 (+ R9): regras por (lastro, ativo, dia útil) ----------------
    for (lastro, ativo, dia_util), grupo in grupos_validos.groupby(CHAVE_ATIVO + [_DIA_UTIL], sort=False):
        eventos = grupo[COL_EVENTO].tolist()
        caso, motivo = classificacao[(lastro, ativo, dia_util)]
        em_pendencia = lastro in lastros_pendencia
        if em_pendencia and caso != PENDENCIA:
            motivo = "Lastro fora do arquivo final: pendência em outro dia útil"
        acoes: list[str] = []

        if not em_pendencia:
            tem_l_ou_b = bool(EVENTOS_EXCLUIDOS & set(eventos))
            linhas_j = grupo[grupo[COL_EVENTO] == EVENTO_J]

            def data_final_de(linha):
                return dia_util if levar_para_dia_util else linha[COL_DATA]

            # R1: exclui L e B
            for idx, linha in grupo[grupo[COL_EVENTO].isin(EVENTOS_EXCLUIDOS)].iterrows():
                indices_excluir.append(idx)
                acoes.append(f"exclui {linha[COL_EVENTO]}")
                log.append(_entrada_log(linha, dia_util, caso, TIPO_EXCLUSAO, linha[COL_DATA], None,
                                        linha[COL_EVENTO], None, linha[COL_PERCENTUAL], None))

            # R3: J = mínimo
            if tem_l_ou_b and not linhas_j.empty:
                idx_j = linhas_j.index[0]
                linha_j = grupo.loc[idx_j]
                alteracoes_percentual[idx_j] = PERCENTUAL_MINIMO
                acoes.append("J = mínimo")
                log.append(_entrada_log(linha_j, dia_util, caso, TIPO_ALTERACAO,
                                        linha_j[COL_DATA], data_final_de(linha_j), EVENTO_J, EVENTO_J,
                                        linha_j[COL_PERCENTUAL], PERCENTUAL_MINIMO))

            # R9: datas de fim de semana/feriado -> dia útil
            if levar_para_dia_util:
                movidas = 0
                for idx, linha in grupo[~grupo[COL_EVENTO].isin(EVENTOS_EXCLUIDOS)].iterrows():
                    if linha[COL_DATA].normalize() != dia_util:
                        alteracoes_data[idx] = dia_util
                        movidas += 1
                        log.append(_entrada_log(linha, dia_util, caso, TIPO_ALTERACAO_DATA,
                                                linha[COL_DATA], dia_util, linha[COL_EVENTO], linha[COL_EVENTO]))
                if movidas:
                    acoes.append(f"data -> {dia_util:%d/%m/%Y} ({movidas} evento(s))")

            # R2/R4: garante I
            if EVENTO_I not in eventos:
                modelo = linhas_j.iloc[0] if not linhas_j.empty else grupo.iloc[0]
                data_i = data_final_de(modelo)
                novas_linhas.append(_nova_linha(modelo, data_i, EVENTO_I, grupo[_ORDEM].max() + 0.5))
                acoes.append("inclui I")
                log.append(_entrada_log(modelo, dia_util, caso, TIPO_INCLUSAO, None, data_i,
                                        None, EVENTO_I, None, PERCENTUAL_MINIMO))

        if em_pendencia:
            finais = eventos
        else:
            finais = [e for e in eventos if e not in EVENTOS_EXCLUIDOS]
            if EVENTO_I not in finais:
                finais = finais + [EVENTO_I]

        diagnostico.append({
            COL_ATIVO: ativo, COL_LASTRO: lastro, COL_LOG_DIA_UTIL: dia_util,
            "Datas Cadastradas": _datas_txt(grupo[COL_DATA]),
            "Eventos Originais": "+".join(sorted(eventos)),
            "Eventos Finais": "+".join(sorted(finais)),
            "Caso": caso,
            "Ações": ", ".join(acoes) if acoes else "nenhuma",
            "Observação": motivo,
        })

    # --- R5: lastro irmão sem evento no dia útil -----------------------------
    lastros_por_ativo = (
        trabalho[~sem_ativo & ~fora_do_tratamento].sort_values(_ORDEM)
        .groupby(COL_ATIVO, sort=False)[COL_LASTRO].unique()
    )
    proxima_ordem = float(len(trabalho))

    for (ativo, dia_util), grupo_ativo in grupos_validos.groupby([COL_ATIVO, _DIA_UTIL], sort=False):
        com_evento = set(grupo_ativo[COL_LASTRO])
        faltantes = [l for l in lastros_por_ativo[ativo]
                     if l not in com_evento and l not in lastros_pendencia]
        if not faltantes:
            continue

        if levar_para_dia_util:
            data_par = dia_util
        else:
            js = grupo_ativo[grupo_ativo[COL_EVENTO] == EVENTO_J]
            data_par = (js[COL_DATA].min() if not js.empty
                        else grupo_ativo.sort_values([COL_DATA, _ORDEM])[COL_DATA].iloc[0])
        irmaos = sorted(com_evento, key=str)

        for lastro in faltantes:
            modelo = trabalho[(trabalho[COL_LASTRO] == lastro) & (trabalho[COL_ATIVO] == ativo)].sort_values(_ORDEM).iloc[0]
            for evento in (EVENTO_J, EVENTO_I):
                novas_linhas.append(_nova_linha(modelo, data_par, evento, proxima_ordem))
                proxima_ordem += 1
                log.append(_entrada_log(modelo, dia_util, LASTRO_SEM_EVENTO, TIPO_INCLUSAO, None, data_par,
                                        None, evento, None, PERCENTUAL_MINIMO))
            diagnostico.append({
                COL_ATIVO: ativo, COL_LASTRO: lastro, COL_LOG_DIA_UTIL: dia_util,
                "Datas Cadastradas": "",
                "Eventos Originais": "",
                "Eventos Finais": "I+J",
                "Caso": LASTRO_SEM_EVENTO,
                "Ações": f"inclui J e I em {pd.Timestamp(data_par):%d/%m/%Y}",
                "Observação": f"Sem evento no dia útil; irmão(s) com evento: {', '.join(map(str, irmaos))}",
            })

    # --- Marcas das linhas de entrada (Excel ANTES) -------------------------
    for idx in alteracoes_data:
        trabalho.loc[idx, _MARCA] = MARCA_DATA
    for idx in alteracoes_percentual:
        trabalho.loc[idx, _MARCA] = MARCA_J_ALTERADO
    for idx in indices_excluir:
        trabalho.loc[idx, _MARCA] = MARCA_EXCLUIDA
    trabalho.loc[trabalho[COL_LASTRO].isin(lastros_pendencia) & ~vazia, _MARCA] = MARCA_PENDENCIA
    trabalho.loc[trabalho[COL_LASTRO].isin(set(motivos_fora)), _MARCA] = MARCA_FORA_ANALISE
    trabalho.loc[trabalho[COL_LASTRO].isin(lastros_vencendo), _MARCA] = MARCA_VENCENDO
    marcas_antes = trabalho[_MARCA].where(trabalho[_MARCA].notna(), None).tolist()
    trabalho.loc[indices_excluir, _MARCA] = None
    trabalho.loc[trabalho[_MARCA].isin([MARCA_PENDENCIA, MARCA_FORA_ANALISE, MARCA_VENCENDO]), _MARCA] = None

    # --- Fora da análise e vencendo: saem do fluxo final, sem alteração ----
    def _fluxo_bruto(mascara: pd.Series) -> pd.DataFrame:
        return (trabalho[mascara]
                .sort_values([COL_ATIVO, COL_LASTRO, COL_DATA, _ORDEM], kind="stable", na_position="last")
                .drop(columns=[_ORDEM, _MARCA, COL_DATA_ORIGINAL])
                .reset_index(drop=True))

    fluxo_fora_analise = _fluxo_bruto(trabalho[COL_LASTRO].isin(set(motivos_fora)))
    fluxo_fora_analise.insert(0, COL_MOTIVO, fluxo_fora_analise[COL_LASTRO].map(motivos_fora))
    fluxo_vencendo = _fluxo_bruto(trabalho[COL_LASTRO].isin(lastros_vencendo))
    trabalho = trabalho[~fora_do_tratamento]
    vazia = _eh_linha_vazia(trabalho)

    # --- Lastros em pendência: saem do fluxo final, sem nenhuma alteração ---
    em_pend = trabalho[COL_LASTRO].isin(lastros_pendencia)
    fluxo_pendencias = (
        trabalho[em_pend & ~vazia]
        .sort_values([COL_ATIVO, COL_LASTRO, COL_DATA, _ORDEM], kind="stable", na_position="last")
        .drop(columns=[_ORDEM, _MARCA, COL_DATA_ORIGINAL])
        .reset_index(drop=True)
    )
    trabalho = trabalho[~em_pend]

    # --- Montagem do fluxo final -------------------------------------------
    for idx, valor in alteracoes_percentual.items():
        trabalho.loc[idx, COL_PERCENTUAL] = valor
    for idx, nova_data in alteracoes_data.items():
        trabalho.loc[idx, COL_DATA] = nova_data
    trabalho = trabalho.drop(index=indices_excluir)
    trabalho = trabalho[~_eh_linha_vazia(trabalho)]  # linhas só de cadastro saem
    if novas_linhas:
        trabalho = pd.concat(
            [trabalho, pd.DataFrame(novas_linhas, columns=trabalho.columns)],
            ignore_index=True,
        )
    trabalho = trabalho.sort_values([COL_ATIVO, COL_LASTRO, COL_DATA, _ORDEM],
                                    kind="stable", na_position="last")
    marcas_depois = trabalho[_MARCA].where(trabalho[_MARCA].notna(), None).tolist()

    fluxo_tratado = trabalho.drop(columns=[_ORDEM, _MARCA]).reset_index(drop=True)
    fluxo_tratado[COL_EVENTO] = fluxo_tratado[COL_EVENTO].astype("string")
    if levar_para_dia_util:
        colunas = list(fluxo_tratado.columns)
        colunas.remove(COL_DATA_ORIGINAL)
        colunas.insert(colunas.index(COL_DATA) + 1, COL_DATA_ORIGINAL)
        fluxo_tratado = fluxo_tratado[colunas]
        fluxo_tratado[COL_DATA_ORIGINAL] = pd.to_datetime(fluxo_tratado[COL_DATA_ORIGINAL])
    else:
        fluxo_tratado = fluxo_tratado.drop(columns=[COL_DATA_ORIGINAL])

    df_diag = pd.DataFrame(diagnostico, columns=COLUNAS_DIAGNOSTICO)
    pendencias = df_diag[df_diag["Caso"] == PENDENCIA].reset_index(drop=True)

    return ResultadoProcessamento(
        fluxo_tratado=fluxo_tratado,
        log_alteracoes=registrar_alteracoes(log),
        diagnostico=df_diag,
        pendencias=pendencias,
        fluxo_pendencias=fluxo_pendencias,
        fluxo_fora_analise=fluxo_fora_analise,
        fluxo_vencendo=fluxo_vencendo,
        filtros=filtros,
        marcas_antes=marcas_antes,
        marcas_depois=marcas_depois,
    )


def registrar_alteracoes(entradas: list[dict]) -> pd.DataFrame:
    """Converte as entradas de log em DataFrame com colunas padronizadas."""
    return pd.DataFrame(entradas, columns=COLUNAS_LOG)


# ---------------------------------------------------------------------------
# Validação de amortização (Etapa 3)
# ---------------------------------------------------------------------------
def validar_amortizacoes(
    fluxo_tratado: pd.DataFrame,
    dados_originais: pd.DataFrame,
    tolerancia: float = TOLERANCIA_AMORTIZACAO,
) -> tuple[pd.DataFrame, dict]:
    """
    Soma o percentual de TODOS os eventos I do fluxo completo de cada lastro
    do fluxo final e compara com 100 (com tolerância). Também faz a validação
    consolidada: soma de todos os lastros = quantidade de lastros x 100.

    Lastros em pendência não estão no fluxo final, então ficam de fora.
    Nenhum percentual é ajustado: apenas sinaliza.
    """
    def soma_i(df: pd.DataFrame) -> pd.Series:
        return df[df[COL_EVENTO] == EVENTO_I].groupby(CHAVE_ATIVO)[COL_PERCENTUAL].sum()

    colunas_id = CHAVE_ATIVO + ([COL_ORIGEM] if COL_ORIGEM in fluxo_tratado.columns else [])
    validacao = fluxo_tratado[colunas_id].drop_duplicates(CHAVE_ATIVO).reset_index(drop=True)

    originais = dados_originais[~_eh_linha_vazia(dados_originais)]
    antes = soma_i(originais).rename("Soma I Antes")
    depois = soma_i(fluxo_tratado).rename("Soma I Depois")
    validacao = (validacao
                 .merge(antes, left_on=CHAVE_ATIVO, right_index=True, how="left")
                 .merge(depois, left_on=CHAVE_ATIVO, right_index=True, how="left"))
    validacao[["Soma I Antes", "Soma I Depois"]] = validacao[["Soma I Antes", "Soma I Depois"]].fillna(0.0)
    validacao["Diferença p/ 100"] = validacao["Soma I Depois"] - PERCENTUAL_TOTAL
    validacao["Status"] = [STATUS_OK if abs(d) <= tolerancia else STATUS_ERRO
                           for d in validacao["Diferença p/ 100"]]

    qtd = len(validacao)
    esperado = qtd * PERCENTUAL_TOTAL
    encontrado = float(validacao["Soma I Depois"].sum())
    tolerancia_total = qtd * tolerancia
    consolidado = {
        "Lastros validados": qtd,
        "Soma esperada": esperado,
        "Soma encontrada": encontrado,
        "Diferença": encontrado - esperado,
        "Tolerância usada": tolerancia_total,
        "Status": STATUS_OK if abs(encontrado - esperado) <= tolerancia_total else STATUS_ERRO,
        "Lastros com divergência": int((validacao["Status"] == STATUS_ERRO).sum()),
    }
    return validacao, consolidado


# ---------------------------------------------------------------------------
# Resumo
# ---------------------------------------------------------------------------
def gerar_resumo(resultado: ResultadoProcessamento) -> dict:
    log = resultado.log_alteracoes
    diag = resultado.diagnostico

    def contar(tipo, col=None, evento=None, caso=None):
        m = log["Tipo de Alteração"] == tipo
        if col is not None:
            m &= log[col] == evento
        if caso is not None:
            m &= log["Caso"] == caso
        return int(m.sum())

    def lastros(mascara) -> set:
        return set(diag.loc[mascara, COL_LASTRO])

    regras = ~diag["Caso"].isin([LASTRO_SEM_EVENTO])
    todos = lastros(pd.Series(True, index=diag.index))
    com_pendencia = lastros(diag["Caso"] == PENDENCIA)
    com_acao = lastros(diag["Ações"] != "nenhuma")

    return {
        "Lastros com evento no intervalo": len(lastros(regras)),
        "Grupos analisados (lastro x dia útil)": int(regras.sum()),
        "Eventos I adicionados (regras)": (contar(TIPO_INCLUSAO, "Evento Final", EVENTO_I)
                                           - contar(TIPO_INCLUSAO, "Evento Final", EVENTO_I, LASTRO_SEM_EVENTO)),
        "Eventos L removidos": contar(TIPO_EXCLUSAO, "Evento Original", EVENTO_L),
        "Eventos B removidos": contar(TIPO_EXCLUSAO, "Evento Original", EVENTO_B),
        "Eventos J alterados": contar(TIPO_ALTERACAO, "Evento Original", EVENTO_J),
        "Eventos com data levada para o dia útil": contar(TIPO_ALTERACAO_DATA),
        "Lastros que receberam J + I (sem evento no dia útil)": len(lastros(diag["Caso"] == LASTRO_SEM_EVENTO)),
        "Pares J + I incluídos": contar(TIPO_INCLUSAO, "Evento Final", EVENTO_J, LASTRO_SEM_EVENTO),
        "Lastros sem necessidade de alteração": len(todos - com_acao - com_pendencia),
        "Lastros com pendência (fora do arquivo final)": len(com_pendencia),
        "Lastros fora da análise (tipo de ativo / compromissada)":
            resultado.fluxo_fora_analise[COL_LASTRO].nunique() if len(resultado.fluxo_fora_analise) else 0,
        "Lastros vencendo no intervalo (sem atuação)":
            resultado.fluxo_vencendo[COL_LASTRO].nunique() if len(resultado.fluxo_vencendo) else 0,
        "Lastros no arquivo final": resultado.validacao_consolidada.get("Lastros validados"),
        "Lastros com divergência no percentual de amortização":
            resultado.validacao_consolidada.get("Lastros com divergência"),
        "Validação consolidada de amortização": resultado.validacao_consolidada.get("Status"),
        **resultado.filtros,
    }


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------
def executar(df_query: pd.DataFrame, data_inicial, data_final,
             calendario: Calendario | None = None,
             levar_para_dia_util: bool = True,
             tipos_ativo: list[str] | None = None,
             excluir_compromissada: bool = True) -> ResultadoProcessamento:
    """
    preparar -> processar -> validar -> resumo.
    tipos_ativo: lista dos tipos que ENTRAM na análise (None = sem filtro).
    """
    dados = preparar_dados(df_query)
    resultado = processar_eventos(dados, data_inicial, data_final, calendario, levar_para_dia_util,
                                  tipos_ativo, excluir_compromissada)
    resultado.validacao_lastros, resultado.validacao_consolidada = validar_amortizacoes(
        resultado.fluxo_tratado, dados)
    resultado.resumo = gerar_resumo(resultado)
    return resultado


