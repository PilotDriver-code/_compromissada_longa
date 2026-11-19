"""
Cálculo do prêmio: títulos do dia, cruzamento CETIP x posição (radar) e posições sem operação.

Regras
------
* Títulos do dia: junta os dois arquivos de operações. Título repetido aparece uma vez.
  Se o PU ou a data de liquidação não baterem (entre os arquivos ou dentro de um deles),
  o título fica bloqueado: não lança em nenhuma base (status PU DIFERENTE).
* Teórico: TRUNC(soma das quantidades de todos os trades x PU do prêmio, 2). Trunca uma vez só.
* LZ e XZ: uma linha por conta + título da CETIP (soma as linhas repetidas).
  Cruza com a posição por conta (CD_CETIP) + título. Lança o valor da CETIP.
      OK             quantidade e valor batem
      DIVERGE QTD    quantidade da posição diferente da CETIP        (lança)
      DIVERGE VALOR  |CETIP - teórico| > tolerância                  (lança)
      AMBIGUA        conta + título em mais de uma carteira          (não lança)
      SEM POSICAO    linha da CETIP sem posição                      (não lança)
* BN7: uma linha por carteira + título da posição. Lança sempre o teórico (status CALCULADO).
  Não é comparado com a CETIP.
* Posição sem operação: posição de LZ/XZ em título do dia cuja conta não está na CETIP.
  Não entra no MTCAIXA; tem o teórico para conferência e para o MTCAIXA_ESPECIAIS.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_DOWN, Decimal

import pandas as pd

from . import parametros as P
from .leitura import LinhaCetip, so_digitos

CENTAVO = Decimal("0.01")

# status -> (tom na tela, lança?)
STATUS = {
    "OK": ("ok", True),
    "DIVERGE QTD": ("warn", True),
    "DIVERGE VALOR": ("warn", True),
    "CALCULADO": ("info", True),
    "CARTEIRA AMBIGUA": ("error", False),
    "SEM POSICAO": ("error", False),
    "PU DIFERENTE": ("error", False),
}
ROTULO = {"OK": "OK", "DIVERGE QTD": "Diverge qtd", "DIVERGE VALOR": "Diverge valor",
          "CALCULADO": "Calculado", "CARTEIRA AMBIGUA": "Ambígua",
          "SEM POSICAO": "Sem posição", "PU DIFERENTE": "PU diferente"}


def truncar(valor: Decimal) -> Decimal:
    return valor.quantize(CENTAVO, rounding=ROUND_DOWN)


def teorico(qtd: Decimal, pu: Decimal | None) -> Decimal | None:
    return None if pu is None else truncar(qtd * pu)


# ---------------------------------------------------------------------------
# Estruturas
# ---------------------------------------------------------------------------
@dataclass
class TituloDia:
    codigo: str
    pus: set = field(default_factory=set)
    datas: set = field(default_factory=set)
    contas: dict = field(default_factory=lambda: defaultdict(set))   # arquivo -> {contas}
    tipo_ativo: str = ""
    bases_posicao: set = field(default_factory=set)

    @property
    def bloqueado(self) -> bool:
        return len(self.pus) > 1 or len(self.datas) > 1

    @property
    def pu(self) -> Decimal | None:
        return None if self.bloqueado else next(iter(self.pus))

    @property
    def data_liq(self) -> date | None:
        return None if self.bloqueado else next(iter(self.datas))

    @property
    def motivo(self) -> str:
        partes = []
        if len(self.pus) > 1:
            partes.append("PU " + " | ".join(fmt_num(p, 8) for p in sorted(self.pus)))
        if len(self.datas) > 1:
            partes.append("data " + " | ".join(d.strftime("%d/%m/%Y") for d in sorted(self.datas)))
        return ", ".join(partes)


@dataclass
class Trade:
    operacao: str
    qtd: Decimal
    conta: str


@dataclass
class LinhaRadar:
    base: str
    conta: str
    titulo: str
    carteira: str
    qtd_cetip: Decimal | None
    qtd_pos: Decimal | None
    valor_cetip: Decimal | None
    teorico: Decimal | None
    status: str
    pu: Decimal | None
    data_liq: date | None
    tipo_ativo: str = ""
    trades: list = field(default_factory=list)       # [Trade]
    obs: str = ""

    @property
    def lanca(self) -> bool:
        return STATUS[self.status][1]

    @property
    def valor_lancado(self) -> Decimal | None:
        if not self.lanca:
            return None
        return self.teorico if self.base in P.BASES_TEORICO else self.valor_cetip

    @property
    def operacao(self) -> str:
        """Operação usada no MTCAIXA: a de maior quantidade."""
        if not self.trades:
            return ""
        return max(self.trades, key=lambda t: t.qtd).operacao

    @property
    def dif_qtd(self) -> Decimal | None:
        if self.qtd_cetip is None or self.qtd_pos is None:
            return None
        return self.qtd_pos - self.qtd_cetip


@dataclass
class SemOperacao:
    base: str
    carteira: str
    titulo: str
    contas: list
    trades: list            # [Trade]
    qtd: Decimal
    pu: Decimal | None
    teorico: Decimal | None
    tipo_ativo: str
    data_liq: date | None

    @property
    def operacao(self) -> str:
        return max(self.trades, key=lambda t: t.qtd).operacao if self.trades else ""


@dataclass
class Resultado:
    bases: list
    titulos: list = field(default_factory=list)       # [TituloDia]
    radar: list = field(default_factory=list)         # [LinhaRadar]
    sem_operacao: list = field(default_factory=list)  # [SemOperacao]
    leituras: dict = field(default_factory=dict)      # arquivo -> Leitura
    janela: str = ""
    gerados: dict = field(default_factory=dict)       # base -> Path do MTCAIXA
    bloqueados: list = field(default_factory=list)    # bases com MTCAIXA não gravado por bloqueio
    radar_csv: object = None

    def linhas_da_base(self, base: str) -> list:
        return [r for r in self.radar if r.base == base]

    def alertas(self, base: str) -> list:
        return [r for r in self.linhas_da_base(base) if r.status not in ("OK", "CALCULADO")]


# ---------------------------------------------------------------------------
# Formatação (tela e arquivos)
# ---------------------------------------------------------------------------
def fmt_num(valor, casas: int = 2) -> str:
    if valor is None:
        return "—"
    txt = f"{Decimal(valor):,.{casas}f}"
    return txt.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_conta(digitos: str) -> str:
    """23854006 -> 2385400-6 (formato da conta na CETIP)."""
    return f"{digitos[:-1]}-{digitos[-1]}" if len(digitos) > 1 else digitos


def fmt_qtd(valor) -> str:
    if valor is None:
        return "—"
    v = Decimal(valor)
    casas = 0 if v == v.to_integral_value() else max(0, -v.normalize().as_tuple().exponent)
    return fmt_num(v, casas)


# ---------------------------------------------------------------------------
# 1) Títulos do dia
# ---------------------------------------------------------------------------
def montar_titulos(linhas: list[LinhaCetip]) -> dict[str, TituloDia]:
    titulos: dict[str, TituloDia] = {}
    for l in linhas:
        t = titulos.setdefault(l.titulo, TituloDia(l.titulo))
        t.pus.add(l.pu)
        t.datas.add(l.data_liq)
        t.contas[l.arquivo].add(l.conta)
    return titulos


def consolidar_cetip(linhas: list[LinhaCetip]) -> list[dict]:
    """Uma entrada por arquivo + conta + título, somando quantidade e valor."""
    grupos: dict[tuple, dict] = {}
    for l in linhas:
        g = grupos.setdefault((l.arquivo, l.conta, l.titulo), {
            "arquivo": l.arquivo, "conta": l.conta, "conta_fmt": l.conta_fmt, "titulo": l.titulo,
            "qtd": Decimal(0), "valor": Decimal(0), "n": 0})
        g["qtd"] += l.qtd
        g["valor"] += l.valor
        g["n"] += 1
    return list(grupos.values())


# ---------------------------------------------------------------------------
# 2) Posição
# ---------------------------------------------------------------------------
def preparar_posicao(df: pd.DataFrame, titulos: dict[str, TituloDia]) -> list[dict]:
    """Uma entrada por trade, só com quantidade > 0 e títulos do dia. Usa qtd_total."""
    trades = []
    for reg in df.to_dict("records"):
        titulo = str(reg["clearing"] or "").strip().upper()
        if titulo not in titulos:
            continue
        try:
            qtd = Decimal(str(reg["qtd_total"]).strip())
        except Exception:  # noqa: BLE001 - quantidade vazia/estranha: ignora o trade
            continue
        if not qtd.is_finite() or qtd <= 0:
            continue
        operacao = str(reg["codigo_operacao"]).strip()
        if operacao.endswith(".0"):
            operacao = operacao[:-2]
        trades.append({
            "base": str(reg["codigo_sistema"]).strip().upper(),
            "carteira": str(reg["sigla_carteira"]).strip(),
            "conta": so_digitos(reg["cd_cetip"]),
            "titulo": titulo,
            "operacao": operacao,
            "tipo_ativo": str(reg["tipo_ativo"] or "").strip(),
            "qtd": qtd,
        })
    return trades


# ---------------------------------------------------------------------------
# 3) Cruzamento
# ---------------------------------------------------------------------------
def cruzar(linhas: list[LinhaCetip], posicao: pd.DataFrame, bases: list[str]) -> Resultado:
    res = Resultado(bases=list(bases))
    titulos = montar_titulos(linhas)
    trades = preparar_posicao(posicao, titulos)

    # posição agrupada por conta + título -> {(base, carteira): [trades]}
    por_conta: dict[tuple, dict] = defaultdict(lambda: defaultdict(list))
    for tr in trades:
        por_conta[(tr["conta"], tr["titulo"])][(tr["base"], tr["carteira"])].append(tr)
        t = titulos[tr["titulo"]]
        t.bases_posicao.add(tr["base"])
        t.tipo_ativo = t.tipo_ativo or tr["tipo_ativo"]

    usados = set()          # (base, carteira, conta, titulo) cobertos pela CETIP

    # --- LZ e XZ: a partir das linhas da CETIP ---------------------------------
    for g in consolidar_cetip(linhas):
        tit = titulos[g["titulo"]]
        achados = por_conta.get((g["conta"], g["titulo"]), {})
        base_arq = g["arquivo"]

        if len(achados) == 1:
            (base, carteira), trs = next(iter(achados.items()))
            usados.add((base, carteira, g["conta"], g["titulo"]))
            if base in P.BASES_TEORICO:
                continue            # é conta de BN7: o BN7 é montado pela posição, mais abaixo
        else:
            base, carteira, trs = base_arq, "", []
            for (b, c), lista in achados.items():
                usados.add((b, c, g["conta"], g["titulo"]))

        qtd_pos = sum((tr["qtd"] for tr in trs), Decimal(0)) if trs else (Decimal(0) if not achados else None)
        linha = LinhaRadar(
            base=base, conta=g["conta_fmt"], titulo=g["titulo"], carteira=carteira,
            qtd_cetip=g["qtd"], qtd_pos=qtd_pos, valor_cetip=g["valor"],
            teorico=teorico(qtd_pos, tit.pu) if trs else None, status="OK",
            pu=tit.pu, data_liq=tit.data_liq or min(tit.datas),
            tipo_ativo=trs[0]["tipo_ativo"] if trs else tit.tipo_ativo,
            trades=[Trade(tr["operacao"], tr["qtd"], tr["conta"]) for tr in trs])

        if tit.bloqueado:
            linha.status, linha.obs = "PU DIFERENTE", f"Título com {tit.motivo} nos arquivos"
        elif not achados:
            linha.status, linha.obs = "SEM POSICAO", "Conta + título sem posição no SAC"
        elif len(achados) > 1:
            linha.status = "CARTEIRA AMBIGUA"
            linha.qtd_pos = None
            linha.obs = "Conta + título em mais de uma carteira: " + ", ".join(
                f"{b} {c}" for b, c in sorted(achados))
        elif linha.qtd_pos != linha.qtd_cetip:
            linha.status = "DIVERGE QTD"
        elif abs(linha.valor_cetip - linha.teorico) > P.TOLERANCIA_VALOR:
            linha.status = "DIVERGE VALOR"
        res.radar.append(linha)

    # --- BN7 (e outras bases do teórico): a partir da posição ---------------------
    conta_cetip = {(g["conta"], g["titulo"]): g["conta_fmt"] for g in consolidar_cetip(linhas)}
    grupos_teo: dict[tuple, list] = defaultdict(list)
    for tr in trades:
        if tr["base"] in P.BASES_TEORICO:
            grupos_teo[(tr["base"], tr["carteira"], tr["titulo"])].append(tr)
    for (base, carteira, titulo), trs in grupos_teo.items():
        tit = titulos[titulo]
        qtd = sum((tr["qtd"] for tr in trs), Decimal(0))
        contas = sorted({tr["conta"] for tr in trs})
        conta = next((conta_cetip[(c, titulo)] for c in contas if (c, titulo) in conta_cetip),
                     fmt_conta(contas[0]) if contas else "")
        linha = LinhaRadar(
            base=base, conta=conta, titulo=titulo, carteira=carteira,
            qtd_cetip=None, qtd_pos=qtd, valor_cetip=None, teorico=teorico(qtd, tit.pu),
            status="CALCULADO", pu=tit.pu, data_liq=tit.data_liq or min(tit.datas),
            tipo_ativo=trs[0]["tipo_ativo"],
            trades=[Trade(tr["operacao"], tr["qtd"], tr["conta"]) for tr in trs])
        if tit.bloqueado:
            linha.status, linha.obs = "PU DIFERENTE", f"Título com {tit.motivo} nos arquivos"
        res.radar.append(linha)

    # --- Posição sem operação (LZ/XZ) ---------------------------------------------
    sobras: dict[tuple, list] = defaultdict(list)
    for tr in trades:
        if tr["base"] in P.BASES_TEORICO:
            continue
        if (tr["base"], tr["carteira"], tr["conta"], tr["titulo"]) in usados:
            continue
        sobras[(tr["base"], tr["carteira"], tr["titulo"])].append(tr)
    for (base, carteira, titulo), trs in sobras.items():
        tit = titulos[titulo]
        qtd = sum((tr["qtd"] for tr in trs), Decimal(0))
        res.sem_operacao.append(SemOperacao(
            base=base, carteira=carteira, titulo=titulo,
            contas=sorted({tr["conta"] for tr in trs}),
            trades=[Trade(tr["operacao"], tr["qtd"], tr["conta"]) for tr in trs],
            qtd=qtd, pu=tit.pu, teorico=teorico(qtd, tit.pu),
            tipo_ativo=trs[0]["tipo_ativo"], data_liq=tit.data_liq))

    # --- Só as bases marcadas, em ordem -------------------------------------------
    ordem = {b: i for i, b in enumerate(P.BASES)}
    sel = set(bases)
    prioridade = {"DIVERGE QTD": 0, "DIVERGE VALOR": 1, "PU DIFERENTE": 2, "CARTEIRA AMBIGUA": 3,
                  "SEM POSICAO": 4, "CALCULADO": 5, "OK": 6}
    res.radar = sorted((r for r in res.radar if r.base in sel),
                       key=lambda r: (prioridade[r.status], ordem.get(r.base, 9), r.carteira, r.titulo))
    res.sem_operacao = sorted((s for s in res.sem_operacao if s.base in sel),
                              key=lambda s: (ordem.get(s.base, 9), s.carteira, s.titulo))
    res.titulos = sorted(titulos.values(), key=lambda t: (not t.bloqueado, t.codigo))
    return res
