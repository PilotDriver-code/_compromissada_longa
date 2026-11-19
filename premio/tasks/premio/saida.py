"""
Arquivos gerados pelo Lançamento de prêmio (pasta setup/Premio/Saida).

    MTCAIXA_<BASE>.txt              lançamentos válidos da base (1 arquivo por base)
    MTCAIXA_ESPECIAIS_<BASE>.txt    posições sem operação, com o valor teórico (botão na aba)
    RADAR_PREMIO_<data_hora>.csv    radar completo (CETIP x posição)
    POSICAO_SEM_OPERACAO_<...>.csv  posições sem operação, uma linha por trade

>>> O LAYOUT DO MTCAIXA ESTÁ NA FUNÇÃO linha_mtcaixa(). <<<
Formato de data, separador decimal e encoding ficam em parametros.py.
"""

import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from app.worker import Falha
from core import configuracoes as cfg
from . import parametros as P
from .calculo import fmt_num, fmt_qtd, ROTULO


def pasta_saida() -> Path:
    """setup/Premio/Saida. Funciona mesmo sem a entrada "premio_saida" no config.SUBPASTAS."""
    try:
        pasta = cfg.pasta("premio_saida")
    except KeyError:
        pasta = cfg.pasta_raiz() / "Premio" / "Saida"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def carimbo() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _valor(v: Decimal) -> str:
    txt = f"{v:.2f}"
    return txt.replace(".", P.SEP_DECIMAL)


# ---------------------------------------------------------------------------
# Layout do MTCAIXA (18 colunas, separadas por TAB)
# ---------------------------------------------------------------------------
def linha_mtcaixa(seq: int, carteira: str, tipo_ativo: str, titulo: str, operacao: str,
                  valor: Decimal, data_liq) -> list[str]:
    dt = data_liq.strftime(P.FORMATO_DATA)
    descricao = f"{P.DESC_EVENTO} {tipo_ativo} {titulo} {operacao}".strip()
    v = _valor(valor)
    return [
        str(seq),          # 1  sequencial
        dt,                # 2  data de lançamento
        carteira,          # 3  sigla da carteira
        "MT",              # 4
        P.COD_LANC,        # 5  960
        descricao,         # 6  PAGAMENTO DE PRÊMIO <tipo_ativo> <título> <operação>
        v,                 # 7  valor
        "", "", "",        # 8, 9, 10
        "N",               # 11
        dt,                # 12 data de liquidação
        "N",               # 13
        "N",               # 14
        "REAL",            # 15
        v,                 # 16 valor
        "",                # 17
        "5",               # 18
    ]


def _gravar_txt(caminho: Path, linhas: list[list[str]]) -> None:
    temporario = caminho.with_name(caminho.stem + "_gerando" + caminho.suffix)
    try:
        with open(temporario, "w", encoding=P.ENCODING_MTCAIXA, errors="replace", newline="\r\n") as fh:
            for campos in linhas:
                fh.write("\t".join(campos) + "\n")
        temporario.replace(caminho)
    except PermissionError:
        temporario.unlink(missing_ok=True)
        raise Falha(f"Não foi possível gravar {caminho.name}. Se ele estiver aberto, feche e tente de novo.") from None


def apagar_anteriores(pasta: Path, bases: list[str]) -> list[Path]:
    """Apaga MTCAIXA e MTCAIXA_ESPECIAIS anteriores das bases (evita usar arquivo velho)."""
    apagados = []
    for base in bases:
        for nome in (P.NOME_MTCAIXA, P.NOME_ESPECIAIS):
            p = pasta / nome.format(base=base)
            if p.exists():
                try:
                    p.unlink()
                except PermissionError:
                    raise Falha(f"{p.name} está aberto. Feche o arquivo e rode de novo.") from None
                apagados.append(p)
    return apagados


def gravar_mtcaixa(base: str, linhas_radar: list, pasta: Path) -> Path | None:
    """MTCAIXA_<BASE>.txt com as linhas que lançam, ordenado por carteira e título."""
    validas = sorted((r for r in linhas_radar if r.base == base and r.lanca),
                     key=lambda r: (r.carteira, r.titulo))
    if not validas:
        return None
    caminho = pasta / P.NOME_MTCAIXA.format(base=base)
    _gravar_txt(caminho, [linha_mtcaixa(i, r.carteira, r.tipo_ativo, r.titulo, r.operacao,
                                        r.valor_lancado, r.data_liq)
                          for i, r in enumerate(validas, start=1)])
    return caminho


def gravar_especiais(sem_operacao: list, pasta: Path | None = None) -> list[Path]:
    """MTCAIXA_ESPECIAIS_<BASE>.txt: todas as posições sem operação com teórico, um arquivo por base."""
    pasta = pasta or pasta_saida()
    gerados = []
    por_base: dict[str, list] = {}
    for s in sem_operacao:
        if s.teorico is not None and s.teorico > 0:
            por_base.setdefault(s.base, []).append(s)
    for base, itens in por_base.items():
        itens.sort(key=lambda s: (s.carteira, s.titulo))
        caminho = pasta / P.NOME_ESPECIAIS.format(base=base)
        _gravar_txt(caminho, [linha_mtcaixa(i, s.carteira, s.tipo_ativo, s.titulo, s.operacao,
                                            s.teorico, s.data_liq)
                              for i, s in enumerate(itens, start=1)])
        gerados.append(caminho)
    return gerados


# ---------------------------------------------------------------------------
# CSVs (separador ";", cp1252: abre direto no Excel)
# ---------------------------------------------------------------------------
def _gravar_csv(caminho: Path, cabecalho: list[str], linhas: list[list]) -> Path:
    try:
        with open(caminho, "w", encoding="cp1252", errors="replace", newline="") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(cabecalho)
            w.writerows(linhas)
    except PermissionError:
        raise Falha(f"Não foi possível gravar {caminho.name}. Se ele estiver aberto, feche e tente de novo.") from None
    return caminho


def gravar_radar(radar: list, pasta: Path | None = None) -> Path:
    pasta = pasta or pasta_saida()
    cab = ["base", "conta", "titulo", "carteira", "qt_cetip", "qt_pos", "dif_qt", "valor_cetip",
           "teorico", "dif_valor", "pu_premio", "n_trades", "operacoes", "status", "lancado",
           "valor_lancado", "obs"]
    linhas = []
    for r in radar:
        dif_valor = (r.valor_cetip - r.teorico) if (r.valor_cetip is not None and r.teorico is not None) else None
        linhas.append([
            r.base, r.conta, r.titulo, r.carteira,
            "" if r.qtd_cetip is None else fmt_qtd(r.qtd_cetip),
            "" if r.qtd_pos is None else fmt_qtd(r.qtd_pos),
            "" if r.dif_qtd is None else fmt_qtd(r.dif_qtd),
            "" if r.valor_cetip is None else fmt_num(r.valor_cetip),
            "" if r.teorico is None else fmt_num(r.teorico),
            "" if dif_valor is None else fmt_num(dif_valor),
            "" if r.pu is None else fmt_num(r.pu, 8),
            len(r.trades),
            " | ".join(f"{t.operacao}:{fmt_qtd(t.qtd)}" for t in r.trades),
            ROTULO[r.status], "S" if r.lanca else "N",
            "" if r.valor_lancado is None else fmt_num(r.valor_lancado),
            r.obs,
        ])
    return _gravar_csv(pasta / P.NOME_RADAR.format(carimbo=carimbo()), cab, linhas)


def gravar_sem_operacao(sem_operacao: list, pasta: Path | None = None) -> Path:
    """Uma linha por trade, com a quantidade e o teórico da carteira + título repetidos."""
    pasta = pasta or pasta_saida()
    cab = ["base", "carteira", "titulo", "conta_cetip", "codigo_operacao", "qtd_total",
           "qtd_carteira_titulo", "pu_premio", "teorico_carteira_titulo"]
    linhas = []
    for s in sem_operacao:
        for t in s.trades:
            linhas.append([s.base, s.carteira, s.titulo, t.conta, t.operacao, fmt_qtd(t.qtd),
                           fmt_qtd(s.qtd), "" if s.pu is None else fmt_num(s.pu, 8),
                           "" if s.teorico is None else fmt_num(s.teorico)])
    return _gravar_csv(pasta / P.NOME_SEM_OPERACAO.format(carimbo=carimbo()), cab, linhas)
