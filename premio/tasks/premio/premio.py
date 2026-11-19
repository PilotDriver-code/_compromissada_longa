"""
Lançamento de prêmio: rotina chamada pelo botão "Gerar MTCAIXA" da tela Prêmio.

params = {
    "bases":        ["LZ", "XZ", "BN7"],                 # bases marcadas na tela
    "arquivos":     {"LZ": "...Operacoes_...txt", "XZ": "...operacoes_xz_...txt"},
    "bloquear":     False,   # True: base com alerta não grava o MTCAIXA dela
    "gravar_radar": True,    # grava o RADAR_PREMIO_<data_hora>.csv
    "resultado":    {},      # a rotina coloca aqui o Resultado (a tela lê no fim)
}

Console em 4 blocos: [1] Leitura, [2] Posição (Athena), [3] Radar, [4] Resultado.
"""

from decimal import Decimal
from pathlib import Path

from app.worker import Falha
from . import parametros as P
from .aws.posicao import buscar_posicao
from .calculo import ROTULO, cruzar, fmt_num, montar_titulos
from .leitura import ler_operacoes
from .saida import apagar_anteriores, gravar_mtcaixa, gravar_radar, pasta_saida

MAX_AVISOS = 8   # quantas linhas de aviso listar no console antes de resumir


def _listar(ctx, itens: list[str], nivel: str = "warn"):
    for txt in itens[:MAX_AVISOS]:
        ctx.log(txt, nivel)
    if len(itens) > MAX_AVISOS:
        ctx.log(f"... e mais {len(itens) - MAX_AVISOS} (veja o radar)", nivel)


def executar(params: dict, ctx) -> str:
    bases = [b for b in P.BASES if b in params["bases"]]
    if not bases:
        raise Falha("Marque pelo menos uma base.")
    saida = pasta_saida()

    # [1] Leitura -------------------------------------------------------------------
    ctx.section("[1] Leitura")
    for p in apagar_anteriores(saida, bases):
        ctx.log(f"Apagado o arquivo anterior: {p.name}", "step")

    leituras, linhas = {}, []
    for arquivo, caminho in params["arquivos"].items():
        if not caminho:
            ctx.log(f"Sem arquivo de operações do {arquivo}: os títulos dele ficam de fora.", "warn")
            continue
        leitura = ler_operacoes(caminho, arquivo)
        leituras[arquivo] = leitura
        linhas += leitura.linhas
        ctx.log(f"{Path(caminho).name}: {len(leitura.linhas)} linha(s) de prêmio "
                f"de {leitura.total_linhas}", "step")
        if leitura.invalidas:
            ctx.log(f"{arquivo}: {len(leitura.invalidas)} linha(s) inválida(s), não lançadas", "warn")
            _listar(ctx, [f"   linha {n}: {motivo}" for n, motivo in leitura.invalidas])
        for tipo, qtd in leitura.variacoes.items():
            ctx.log(f"{arquivo}: {qtd} linha(s) de \"{tipo}\" ficaram de fora", "warn")
        ctx.check()
    if not leituras:
        raise Falha("Escolha pelo menos um arquivo de operações.")
    if not linhas:
        raise Falha("Nenhuma linha de PAGAMENTO DE PRÊMIO nos arquivos escolhidos.")

    titulos = montar_titulos(linhas)
    repetidos = sum(1 for t in titulos.values() if len(t.contas) > 1)
    ctx.log(f"Títulos do dia: {len(titulos)} ({repetidos} nos dois arquivos)", "ok")
    _listar(ctx, [f"{t.codigo}: {t.motivo}. Não será lançado." for t in titulos.values() if t.bloqueado])
    ctx.progress(20)

    # [2] Posição -------------------------------------------------------------------
    ctx.section("[2] Posição (Athena)")
    posicao, janela = buscar_posicao(P.BASES, sorted(titulos), ctx)
    ctx.check()
    if posicao.empty:
        ctx.log("O Athena não trouxe posição para os títulos do dia.", "warn")
    else:
        por_base = posicao.groupby(posicao["codigo_sistema"].astype(str).str.strip().str.upper())
        ctx.log(f"{len(posicao)} trade(s) lido(s): " + ", ".join(
            f"{b} {g['sigla_carteira'].nunique()} carteira(s)" for b, g in por_base), "ok")
    ctx.progress(60)

    # [3] Radar ---------------------------------------------------------------------
    ctx.section("[3] Radar")
    res = cruzar(linhas, posicao, bases)
    res.leituras, res.janela = leituras, janela
    params["resultado"]["res"] = res

    for base in bases:
        rows = res.linhas_da_base(base)
        lanc = [r for r in rows if r.lanca]
        div = [r for r in lanc if r.status in ("DIVERGE QTD", "DIVERGE VALOR")]
        nao = [r for r in rows if not r.lanca]
        sem = [s for s in res.sem_operacao if s.base == base]
        total = sum((r.valor_lancado for r in lanc), Decimal(0))
        tabela = [("Lançados", f"{len(lanc)}  ·  R$ {fmt_num(total)}")]
        if base not in P.BASES_TEORICO:
            tabela += [("Com divergência", len(div)), ("Não lançados", len(nao)),
                       ("Posição sem operação", len(sem))]
        elif nao:
            tabela += [("Não lançados", len(nao))]
        ctx.table(f"Base {base}" + ("  (valor teórico)" if base in P.BASES_TEORICO else ""), tabela)
    nao_lancados = [r for r in res.radar if not r.lanca]
    if nao_lancados:
        ctx.log(f"{len(nao_lancados)} linha(s) não lançada(s):", "warn")
        _listar(ctx, [f"   {r.base} {r.conta} {r.titulo}: {ROTULO[r.status]}" for r in nao_lancados])
    ctx.progress(80)

    # [4] Resultado -----------------------------------------------------------------
    ctx.section("[4] Resultado")
    gerados, situacao = [], []
    for base in bases:
        alertas = res.alertas(base)
        n_lanc = sum(1 for r in res.linhas_da_base(base) if r.lanca)
        if params.get("bloquear") and alertas:
            res.bloqueados.append(base)
            situacao.append((f"{base}  ·  bloqueado ({len(alertas)} alerta(s))", "NÃO GRAVADO"))
            continue
        caminho = gravar_mtcaixa(base, res.radar, saida)
        if caminho is None:
            situacao.append((f"{base}  ·  nada a lançar", "NÃO GRAVADO"))
            continue
        res.gerados[base] = caminho
        gerados.append(caminho)
        situacao.append((f"{base}  ·  {n_lanc} lançamento(s)", "COM DIVERGÊNCIA" if alertas else "OK"))
    ctx.table("MTCAIXA por base", situacao)

    if params.get("gravar_radar", True) and res.radar:
        res.radar_csv = gravar_radar(res.radar, saida)
        gerados.append(res.radar_csv)
    if gerados:
        ctx.files(gerados)
    ctx.progress(100)

    if not res.gerados:
        motivo = "bloqueio por divergência" if res.bloqueados else "nada a lançar"
        raise Falha(f"Nenhum MTCAIXA gravado ({motivo}). Veja o radar.")
    n_lanc = sum(1 for r in res.radar if r.lanca and r.base in res.gerados)
    msg = f"{len(res.gerados)} MTCAIXA gravado(s): {n_lanc} lançamento(s)"
    if any(res.alertas(b) for b in res.gerados) or res.bloqueados:
        msg += ", com alertas"
    return msg + "."
