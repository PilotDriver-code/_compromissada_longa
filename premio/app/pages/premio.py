"""
Tela Lançamento de prêmio (MTCAIXA, lançamento 960).

A lógica fica em tasks/premio (o botão "Gerar MTCAIXA" chama tasks.premio.premio.executar).
Esta tela só monta os parâmetros e mostra o resultado em 4 abas:
    Títulos do dia | Radar | Sem operação | Execução
"""

from datetime import datetime
from decimal import Decimal
from pathlib import Path

import config
from core import aws
from core import configuracoes as cfg

from .. import icons, theme
from ..qt import QtGui, QtWidgets, Qt, Signal
from ..widgets import (ChipGroup, Field, GhostButton, IconButton, LogConsole, Panel, PrimaryButton,
                       Segmented, SwitchRow, hline, label, open_path)
from .base import BasePage

W = QtWidgets
AL_R = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
AL_C = Qt.AlignmentFlag.AlignCenter

# Ícone do menu (se ainda não existir no app/icons.py)
icons._PATHS.setdefault("award", '<circle cx="12" cy="9" r="6"/><path d="M8.6 13.8 7 21.5l5-2.8 5 2.8-1.6-7.7"/>')


def _cores(t: dict) -> tuple[dict, dict]:
    forte = {"ok": t["success"], "warn": t["warn"], "error": t["danger"], "info": t["ink_muted"]}
    suave = {"ok": t["success_soft"], "warn": t["warn_soft"], "error": t["danger_soft"], "info": t["field"]}
    return forte, suave


def _brl(v) -> str:
    from tasks.premio.calculo import fmt_num
    return f"R$ {fmt_num(v)}"


# ---------------------------------------------------------------------------
# Peças da tela
# ---------------------------------------------------------------------------
class StatTile(W.QFrame):
    """Quadro de número (Lançados, Não lançados...)."""

    def __init__(self, titulo: str, tom: str):
        super().__init__()
        self.setObjectName("Panel")
        self._tom = tom
        lay = W.QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(2)
        topo = W.QHBoxLayout()
        topo.setSpacing(6)
        self._dot = W.QLabel()
        self._dot.setFixedSize(8, 8)
        topo.addWidget(self._dot)
        topo.addWidget(label(titulo, "FieldLabel"))
        topo.addStretch(1)
        lay.addLayout(topo)
        self.valor = label("—", "StatValue")
        self.sub = label("", "Hint")
        lay.addWidget(self.valor)
        lay.addWidget(self.sub)
        self.restyle()

    def set(self, valor, sub: str = ""):
        self.valor.setText(str(valor))
        self.sub.setText(sub)

    def restyle(self):
        t = theme.current()
        cor = {"ok": t["success"], "warn": t["warn"], "error": t["danger"],
               "info": t["ink_faint"], "accent": t["accent"]}[self._tom]
        self._dot.setStyleSheet(f"background:{cor}; border-radius:4px;")


class Filtros(W.QWidget):
    """Pílulas de filtro. Cada grupo escolhe uma opção; clicar de novo na marcada desmarca."""

    changed = Signal()

    def __init__(self, grupos: list[list[str]], obrigatorio: list[bool]):
        super().__init__()
        lay = W.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(label("Mostrar:", "Hint"))
        self._grupos: list[list[W.QPushButton]] = []
        self._obrig = obrigatorio
        self._seps = []
        for gi, opcoes in enumerate(grupos):
            if gi:
                sep = W.QFrame()
                sep.setFixedSize(1, 18)
                self._seps.append(sep)
                lay.addWidget(sep)
            botoes = []
            for chave in opcoes:
                b = W.QPushButton(chave)
                b.setObjectName("Chip")
                b.setCheckable(True)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.setProperty("chave", chave)
                b.clicked.connect(lambda checked, g=gi, bt=b: self._clicou(g, bt, checked))
                botoes.append(b)
                lay.addWidget(b)
            if obrigatorio[gi]:
                botoes[0].setChecked(True)
            self._grupos.append(botoes)
        self.extras = W.QHBoxLayout()
        self.extras.setSpacing(8)
        lay.addStretch(1)
        lay.addLayout(self.extras)
        self.restyle()

    def _clicou(self, g: int, botao, checked: bool):
        for b in self._grupos[g]:
            if b is not botao:
                b.setChecked(False)
        if not checked and self._obrig[g]:
            botao.setChecked(True)
        # "Todos" do 1º grupo limpa os outros grupos
        if g == 0 and botao is self._grupos[0][0]:
            for outros in self._grupos[1:]:
                for b in outros:
                    b.setChecked(False)
        self.changed.emit()

    def escolha(self, g: int) -> str | None:
        for b in self._grupos[g]:
            if b.isChecked():
                return b.property("chave")
        return None

    def contar(self, g: int, contagem: dict):
        """Atualiza o texto das pílulas com a quantidade (ex.: "LZ 7")."""
        for b in self._grupos[g]:
            chave = b.property("chave")
            n = contagem.get(chave)
            b.setText(chave if n is None else f"{chave} {n}")

    def resetar(self):
        for g, botoes in enumerate(self._grupos):
            for i, b in enumerate(botoes):
                b.setChecked(self._obrig[g] and i == 0)

    def restyle(self):
        t = theme.current()
        for s in self._seps:
            s.setStyleSheet(f"background:{t['border']};")


class Vazio(W.QStackedWidget):
    """Mostra um aviso no lugar do conteúdo enquanto não há resultado."""

    def __init__(self, conteudo: W.QWidget, texto: str):
        super().__init__()
        self.aviso = label(texto, "Hint", wrap=True)
        self.aviso.setAlignment(AL_C)
        self.addWidget(self.aviso)
        self.addWidget(conteudo)

    def set_vazio(self, vazio: bool, texto: str | None = None):
        if texto:
            self.aviso.setText(texto)
        self.setCurrentIndex(0 if vazio else 1)


class _CorNaSelecao(W.QStyledItemDelegate):
    """Mantém a cor do texto (status verde/vermelho...) quando a linha está selecionada."""

    def initStyleOption(self, option, index):  # noqa: N802 - API Qt
        super().initStyleOption(option, index)
        cor = index.data(Qt.ItemDataRole.ForegroundRole)
        if cor is not None:
            pincel = cor if isinstance(cor, QtGui.QBrush) else QtGui.QBrush(QtGui.QColor(cor))
            option.palette.setBrush(QtGui.QPalette.ColorRole.HighlightedText, pincel)
        else:
            option.palette.setColor(QtGui.QPalette.ColorRole.HighlightedText,
                                    QtGui.QColor(theme.current()["ink"]))


def nova_tabela(colunas: list[str]) -> W.QTableWidget:
    tb = W.QTableWidget(0, len(colunas))
    tb.setItemDelegate(_CorNaSelecao(tb))
    tb.setHorizontalHeaderLabels(colunas)
    tb.verticalHeader().hide()
    tb.setShowGrid(False)
    tb.setWordWrap(False)
    tb.setSelectionBehavior(W.QAbstractItemView.SelectionBehavior.SelectRows)
    tb.setSelectionMode(W.QAbstractItemView.SelectionMode.SingleSelection)
    tb.setEditTriggers(W.QAbstractItemView.EditTrigger.NoEditTriggers)
    tb.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    tb.verticalHeader().setDefaultSectionSize(31)
    tb.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    tb.horizontalHeader().setHighlightSections(False)
    return tb


def estilo_tabela(tb: W.QTableWidget):
    t = theme.current()
    tb.setStyleSheet(f"""
        QTableWidget {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 8px;
                        font-size: 12px; color: {t['ink']}; selection-background-color: {t['hover']}; }}
        QHeaderView::section {{ background: {t['field']}; color: {t['ink_muted']}; border: none;
                        border-bottom: 1px solid {t['border']}; padding: 6px 6px; font-weight: 600; font-size: 11px; }}
        QTableWidget::item {{ padding: 0 6px; border-bottom: 1px solid {t['border']}; }}
    """)


def larguras(tb: W.QTableWidget, ws: list[int], esticar: int):
    hh = tb.horizontalHeader()
    for c, w in enumerate(ws):
        if w:
            hh.setSectionResizeMode(c, W.QHeaderView.ResizeMode.Interactive)
            tb.setColumnWidth(c, w)
    hh.setSectionResizeMode(esticar, W.QHeaderView.ResizeMode.Stretch)


def item(texto, alinhar=None, cor=None, fundo=None, negrito=False, italico=False) -> W.QTableWidgetItem:
    it = W.QTableWidgetItem(str(texto))
    if alinhar is not None:
        it.setTextAlignment(alinhar)
    if cor:
        it.setForeground(QtGui.QColor(cor))
    if fundo:
        it.setBackground(QtGui.QColor(fundo))
    if negrito or italico:
        f = it.font()
        f.setBold(negrito)
        f.setItalic(italico)
        it.setFont(f)
    return it


class Caixa(W.QLabel):
    """Quadro de texto (explicação no topo das abas, regra do valor)."""

    def __init__(self, html_fn, tom: str = "field"):
        super().__init__()
        self._html_fn, self._tom = html_fn, tom
        self.setWordWrap(True)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.restyle()

    def restyle(self):
        t = theme.current()
        fundo = t["accent_soft"] if self._tom == "accent" else t["field"]
        borda = t["accent_soft"] if self._tom == "accent" else t["border"]
        self.setStyleSheet(f"background:{fundo}; border:1px solid {borda}; border-radius:8px;"
                           f"padding:9px 12px; font-size:12px;")
        self.setText(self._html_fn(t))


class SeletorArquivo(W.QWidget):
    """Tag da base + lista das versões do arquivo de operações + botão para escolher outro."""

    def __init__(self, base: str, pasta_fn):
        super().__init__()
        self.base, self._pasta_fn = base, pasta_fn
        lay = W.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.tag = W.QLabel(base)
        self.tag.setFixedWidth(34)
        self.tag.setAlignment(AL_C)
        self.combo = W.QComboBox()
        self.combo.setMinimumWidth(120)
        self.combo.setSizeAdjustPolicy(W.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo.view().setTextElideMode(Qt.TextElideMode.ElideNone)
        self.combo.currentIndexChanged.connect(self._tooltip)
        self.bt = IconButton("folder", "Escolher outro arquivo", obj="FieldButton", size=15)
        self.bt.clicked.connect(self._escolher)
        lay.addWidget(self.tag)
        lay.addWidget(self.combo, 1)
        lay.addWidget(self.bt)
        self._extra: Path | None = None   # arquivo escolhido fora da pasta CETIP
        self.restyle()

    def caminho(self) -> str:
        dado = self.combo.currentData()
        return str(dado) if dado else ""

    def recarregar(self):
        from tasks.premio import versoes as V

        atual = self.caminho()
        versoes = V.listar_versoes(self._pasta_fn(), self.base)
        self.combo.blockSignals(True)
        self.combo.clear()
        for i, (p, _) in enumerate(versoes):
            self.combo.addItem(V.rotulo(versoes, i), str(p))
        if self._extra and self._extra.is_file() and self.combo.findData(str(self._extra)) < 0:
            quando = datetime.fromtimestamp(self._extra.stat().st_mtime).strftime("%d/%m %H:%M")
            self.combo.addItem(f"{quando}   escolhido   {self._extra.name}", str(self._extra))
        if self.combo.count() == 0:
            self.combo.addItem("Nenhum arquivo na pasta CETIP", "")
        i = self.combo.findData(atual) if atual else -1
        if i < 0:
            i = V.versao_padrao(versoes)
        self.combo.setCurrentIndex(max(i, 0))
        self.combo.blockSignals(False)
        self._tooltip()

    def _escolher(self):
        caminho, _ = W.QFileDialog.getOpenFileName(
            self, f"Arquivo de operações ({self.base})", str(self._pasta_fn()),
            "Arquivos de texto (*.txt);;Todos os arquivos (*)")
        if not caminho:
            return
        self._extra = Path(caminho)
        self.recarregar()
        self.combo.setCurrentIndex(self.combo.findData(str(self._extra)))

    def _tooltip(self):
        self.combo.setToolTip(self.caminho() or "Coloque os arquivos em " + str(self._pasta_fn()))

    def restyle(self):
        t = theme.current()
        self.tag.setStyleSheet(f"background:{t['field']}; border:1px solid {t['border']}; border-radius:6px;"
                               f"padding:6px 0; font-weight:600; color:{t['ink_muted']}; font-size:12px;")
        self.combo.setStyleSheet(f"""
            QComboBox {{ background: {t['field']}; border: 1px solid {t['border']}; border-radius: 8px;
                         padding: 6px 10px; color: {t['ink']}; font-size: 12px; min-height: 22px; }}
            QComboBox:hover {{ border-color: {t['border_strong']}; }}
            QComboBox::drop-down {{ border: none; width: 26px; }}
            QComboBox::down-arrow {{ image: url("{theme._svg_asset('chevron-down', t['ink_muted'])}");
                                     width: 12px; height: 12px; }}
            QComboBox QAbstractItemView {{ background: {t['surface']}; color: {t['ink']};
                         border: 1px solid {t['border_strong']}; padding: 4px; outline: 0; font-size: 12px;
                         selection-background-color: {t['accent_soft']}; selection-color: {t['accent_text']}; }}
        """)


# ---------------------------------------------------------------------------
# Tela
# ---------------------------------------------------------------------------
class PremioPage(BasePage):
    title = "Lançamento de prêmio"
    description = ("Gera o MTCAIXA do pagamento de prêmio (lançamento 960) a partir dos arquivos "
                   "de operações da CETIP e da posição do SAC.")
    nav_icon = "award"
    nav_label = "Prêmio"

    def __init__(self, parent=None):
        super().__init__(parent)
        from tasks.premio import parametros as P

        self.P = P
        self._res = None
        self._tarefa = ""
        root = W.QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)
        root.addWidget(self._painel_parametros())
        root.addLayout(self._painel_resultado(), 1)
        self._limpar_resultado()

    # ------------------------------------------------------------ parâmetros
    def _painel_parametros(self) -> W.QWidget:
        P = self.P
        p = Panel("Parâmetros", spacing=14)
        p.setFixedWidth(360)

        self.bases = ChipGroup(P.BASES)
        for c in self.bases._chips:
            c.setChecked(True)
        if self.bases._all:
            self.bases._all.setChecked(True)
        self.f_bases = Field("Bases", self.bases)
        self.bases.changed.connect(lambda _: self.f_bases.set_hint(""))
        p.body.addWidget(self.f_bases)

        caixa = W.QWidget()
        cl = W.QVBoxLayout(caixa)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(6)
        self.seletores = {}
        for base in P.ARQUIVOS_OPERACOES:
            s = SeletorArquivo(base, lambda: cfg.pasta("cetip"))
            self.seletores[base] = s
            cl.addWidget(s)
        self.f_arquivos = Field("Arquivos de operações CETIP", caixa,
                                "Padrão: a 1ª versão do dia. Os dois juntos formam a lista de "
                                "títulos do dia, que vale para LZ, XZ e BN7.")
        p.body.addWidget(self.f_arquivos)

        # Posição: sempre Athena
        self.box_pos = W.QFrame()
        self.box_pos.setObjectName("PremioPos")
        bl = W.QHBoxLayout(self.box_pos)
        bl.setContentsMargins(10, 8, 10, 8)
        bl.setSpacing(8)
        self.ic_pos = W.QLabel()
        self.lb_pos = W.QLabel()
        self.lb_pos.setTextFormat(Qt.TextFormat.RichText)
        self.lb_aws = W.QLabel()
        bl.addWidget(self.ic_pos)
        bl.addWidget(self.lb_pos, 1)
        bl.addWidget(self.lb_aws)
        p.body.addWidget(Field("Posição (SAC)", self.box_pos,
                               f"Última posição de cada carteira ({self.P.DIAS_POSICAO} dias úteis), por trade. "
                               "A conferência soma por conta + título, como a CETIP."))

        teo = ", ".join(sorted(P.BASES_TEORICO))
        self.box_valor = Caixa(lambda t: (
            f'<span style="color:{t["accent_text"]}; font-weight:600;">Valor:</span> '
            f'<span style="color:{t["ink_muted"]};">LZ e XZ lançam o valor da CETIP e conferem com o '
            f'teórico (quantidade da posição × PU do prêmio, truncado em 2 casas). '
            f'{teo} lança sempre o teórico.</span>'), "accent")
        p.body.addWidget(self.box_valor)

        p.body.addWidget(hline())
        self.sw_bloquear = SwitchRow("Bloquear se houver divergência",
                                     "Trava só o MTCAIXA da base que tiver alerta.")
        self.sw_radar = SwitchRow("Gravar radar em CSV")
        self.sw_radar.setChecked(True)
        p.body.addWidget(self.sw_bloquear)
        p.body.addWidget(self.sw_radar)
        p.body.addStretch(1)

        self._run_button = PrimaryButton("Gerar MTCAIXA", "play")
        self._run_button.setToolTip("Ctrl+Enter")
        self._run_button.clicked.connect(self.run)
        p.body.addWidget(self._run_button)
        return p

    # ------------------------------------------------------------- resultado
    def _painel_resultado(self) -> W.QLayout:
        col = W.QVBoxLayout()
        col.setSpacing(12)

        tiles = W.QHBoxLayout()
        tiles.setSpacing(12)
        self.t_titulos = StatTile("Títulos do dia", "accent")
        self.t_lanc = StatTile("Lançados", "ok")
        self.t_nao = StatTile("Não lançados", "error")
        self.t_sem = StatTile("Posição sem operação", "info")
        for tl in (self.t_titulos, self.t_lanc, self.t_nao, self.t_sem):
            tiles.addWidget(tl, 1)
        col.addLayout(tiles)

        card = Panel(None, margins=16, spacing=12)
        topo = W.QHBoxLayout()
        topo.setSpacing(8)
        self.abas = Segmented(["Títulos do dia", "Radar", "Sem operação", "Execução"])
        self.abas.setFixedWidth(520)
        topo.addWidget(self.abas)
        topo.addStretch(1)
        bt_pasta = IconButton("folder", "Abrir a pasta dos arquivos gerados", obj="FieldButton", size=16)
        bt_pasta.clicked.connect(self._abrir_pasta)
        topo.addWidget(bt_pasta)
        card.body.addLayout(topo)

        self.stack = W.QStackedWidget()
        self.stack.addWidget(self._aba_titulos())
        self.stack.addWidget(self._aba_radar())
        self.stack.addWidget(self._aba_sem_operacao())
        self.console = LogConsole()
        self.console.cancel_requested.connect(self.cancel)
        self.stack.addWidget(self.console)
        self.abas.changed.connect(self.stack.setCurrentIndex)
        card.body.addWidget(self.stack, 1)
        col.addWidget(card, 1)
        return col

    def _ir_para(self, aba: int):
        self.abas._group.button(aba).setChecked(True)
        self.stack.setCurrentIndex(aba)

    # Aba 1: títulos do dia ---------------------------------------------------
    def _aba_titulos(self) -> W.QWidget:
        w = W.QWidget()
        lay = W.QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        nomes = " e ".join(self.P.ARQUIVOS_OPERACOES[b].capitalize() if i == 0 else self.P.ARQUIVOS_OPERACOES[b]
                           for i, b in enumerate(self.P.ARQUIVOS_OPERACOES))
        self.cx_titulos = Caixa(lambda t: (
            f'<b style="color:{t["ink"]};">Títulos que pagam prêmio hoje, juntando {nomes}.</b><br>'
            f'<span style="color:{t["ink_muted"]};">Título repetido nos dois arquivos aparece uma vez só. É esta '
            f'lista que busca a posição no Athena (LZ, XZ e BN7). Se o PU ou a data não baterem entre os '
            f'arquivos, o título não é lançado.</span>'))
        lay.addWidget(self.cx_titulos)
        self.fil_titulos = Filtros([["Todos", "Nos dois arquivos", "PU diferente", "Sem posição"]], [True])
        self.fil_titulos.changed.connect(self._filtrar_titulos)
        lay.addWidget(self.fil_titulos)
        cols = ["Título", "Tipo", "PU do prêmio", "Liquidação"]
        cols += [self.P.ARQUIVOS_OPERACOES[b].capitalize() if i == 0 else self.P.ARQUIVOS_OPERACOES[b]
                 for i, b in enumerate(self.P.ARQUIVOS_OPERACOES)]
        cols += ["PU confere", "Posição no SAC"]
        self.tb_titulos = nova_tabela(cols)
        larguras(self.tb_titulos, [110, 60, 150, 86, 84, 98, 82, 0], len(cols) - 1)
        lay.addWidget(self.tb_titulos, 1)
        lay.addWidget(label("O PU e a data vêm da CETIP. Contas = quantas contas do arquivo pagam o título.", "Hint"))
        self.v_titulos = Vazio(w, "Gere o MTCAIXA para ver os títulos do dia.")
        return self.v_titulos

    # Aba 2: radar -------------------------------------------------------------
    def _aba_radar(self) -> W.QWidget:
        w = W.QWidget()
        lay = W.QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.fil_radar = Filtros([["Todos"] + self.P.BASES, ["OK", "Com divergência", "Não lançados"]],
                                 [True, False])
        self.fil_radar.changed.connect(self._filtrar_radar)
        lay.addWidget(self.fil_radar)
        cols = ["Base", "Conta", "Título", "Carteira", "Qtd CETIP", "Qtd posição", "Valor CETIP", "Teórico", "Status"]
        self.tb_radar = nova_tabela(cols)
        larguras(self.tb_radar, [46, 84, 112, 86, 66, 86, 88, 84, 0], 8)
        self.tb_radar.itemSelectionChanged.connect(self._detalhe)
        lay.addWidget(self.tb_radar, 1)

        self.det = W.QFrame()
        self.det.setObjectName("PremioDetalhe")
        dl = W.QVBoxLayout(self.det)
        dl.setContentsMargins(14, 10, 14, 10)
        dl.setSpacing(5)
        cab = W.QHBoxLayout()
        cab.setSpacing(10)
        self.det_titulo = label("", "PanelTitle")
        self.det_badge = W.QLabel()
        cab.addWidget(self.det_titulo)
        cab.addStretch(1)
        cab.addWidget(self.det_badge)
        dl.addLayout(cab)
        self.det_corpo = W.QLabel()
        self.det_corpo.setTextFormat(Qt.TextFormat.RichText)
        self.det_corpo.setWordWrap(True)
        self.det_corpo.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        dl.addWidget(self.det_corpo)
        lay.addWidget(self.det)

        self.lb_fechado = label("", "Hint")
        self.lb_fechado.setTextFormat(Qt.TextFormat.RichText)
        self.lb_fechado.setWordWrap(True)
        lay.addWidget(self.lb_fechado)
        self.v_radar = Vazio(w, "Gere o MTCAIXA para ver o radar.")
        return self.v_radar

    # Aba 3: sem operação --------------------------------------------------------
    def _aba_sem_operacao(self) -> W.QWidget:
        w = W.QWidget()
        lay = W.QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.cx_sem = Caixa(lambda t: (
            f'<b style="color:{t["ink"]};">Posições do SAC (Athena) em títulos do dia que não aparecem nos '
            f'arquivos de operações.</b><br><span style="color:{t["ink_muted"]};">Não entram no MTCAIXA da base. '
            f'O teórico é a soma das quantidades × PU do prêmio, truncado em 2 casas. Se precisar lançar, '
            f'gere o MTCAIXA_ESPECIAIS (um por base).</span>'))
        lay.addWidget(self.cx_sem)
        self.fil_sem = Filtros([["Todas"] + [b for b in self.P.BASES if b not in self.P.BASES_TEORICO]], [True])
        self.fil_sem.changed.connect(self._filtrar_sem)
        self.bt_csv = GhostButton("Exportar CSV", "external")
        self.bt_csv.clicked.connect(self._exportar_csv)
        self.bt_especiais = GhostButton("Gerar MTCAIXA_ESPECIAIS", "play")
        self.bt_especiais.setObjectName("PremioAccent")
        self.bt_especiais.clicked.connect(self._gerar_especiais)
        self.fil_sem.extras.addWidget(self.bt_csv)
        self.fil_sem.extras.addWidget(self.bt_especiais)
        lay.addWidget(self.fil_sem)
        cols = ["Base", "Carteira", "Título", "Trades", "Quantidade", "PU do prêmio", "Teórico"]
        self.tb_sem = nova_tabela(cols)
        larguras(self.tb_sem, [46, 96, 120, 70, 100, 110, 0], 6)
        lay.addWidget(self.tb_sem, 1)
        lay.addWidget(label("Exportar CSV: uma linha por trade. MTCAIXA_ESPECIAIS: mesmo layout do MTCAIXA, "
                            "com o valor teórico.", "Hint", wrap=True))
        self.v_sem = Vazio(w, "Gere o MTCAIXA para ver as posições sem operação.")
        return self.v_sem

    # ------------------------------------------------------------------ estado
    def on_shown(self):
        super().on_shown()
        for s in self.seletores.values():
            s.recarregar()
        self._status_aws()

    def _status_aws(self):
        t = theme.current()
        self.ic_pos.setPixmap(icons.pixmap("cloud", t["ink_muted"], 16))
        self.lb_pos.setText(f'<span style="color:{t["ink"]}; font-weight:600;">Athena</span>')
        quando = aws.ultima_atualizacao()
        if quando is None:
            txt, cor = "✕ sem credenciais", t["danger"]
        elif (datetime.now() - quando).total_seconds() > config.AWS_VALIDADE_HORAS * 3600:
            txt, cor = f"! AWS atualizada {aws.tempo_relativo(quando)}", t["warn"]
        else:
            txt, cor = f"✓ AWS atualizada {aws.tempo_relativo(quando)}", t["success"]
        self.lb_aws.setText(txt)
        self.lb_aws.setStyleSheet(f"color:{cor}; font-size:11px; font-weight:600;")
        self.lb_aws.setToolTip(str(cfg.arquivo_aws()))

    def refresh_icons(self):
        super().refresh_icons()
        self._restyle()

    def _restyle(self):
        t = theme.current()
        self.box_pos.setStyleSheet(f"#PremioPos {{ background:{t['field']}; border:1px solid {t['border']};"
                                   f"border-radius:8px; }}")
        self.det.setStyleSheet(f"#PremioDetalhe {{ background:{t['field']}; border:1px solid {t['border']};"
                               f"border-radius:8px; }}")
        self.bt_especiais.setStyleSheet(
            f"#PremioAccent {{ background:{t['accent_soft']}; color:{t['accent_text']}; border:1px solid {t['accent']};"
            f"border-radius:8px; padding:7px 14px; font-weight:600; }}"
            f"#PremioAccent:disabled {{ background:{t['field']}; color:{t['ink_faint']}; border-color:{t['border']}; }}")
        for w in (self.t_titulos, self.t_lanc, self.t_nao, self.t_sem, self.box_valor, self.cx_titulos,
                  self.cx_sem, self.fil_titulos, self.fil_radar, self.fil_sem, *self.seletores.values()):
            w.restyle()
        for tb in (self.tb_titulos, self.tb_radar, self.tb_sem):
            estilo_tabela(tb)
        self._status_aws()
        if self._res is not None:
            self._mostrar(self._res, manter_aba=True)

    # ---------------------------------------------------------------- execução
    def run(self):
        if self.is_busy() or not self.ensure_ready():
            return
        bases = self.bases.selected()
        if not bases:
            self.f_bases.set_hint("Marque pelo menos uma base.", "error")
            self.toast("Marque pelo menos uma base.", "error")
            return
        arquivos = {b: s.caminho() for b, s in self.seletores.items()}
        if not any(arquivos.values()):
            self.f_arquivos.set_hint(f"Nenhum arquivo de operações em {cfg.pasta('cetip')}.", "error")
            self.toast("Escolha os arquivos de operações da CETIP.", "error")
            return
        faltando = [b for b, c in arquivos.items() if c and not Path(c).is_file()]
        if faltando:
            self.toast(f"Arquivo de operações não encontrado: {', '.join(faltando)}. Escolha de novo.", "error")
            for s in self.seletores.values():
                s.recarregar()
            return
        self.f_arquivos.set_hint("Padrão: a 1ª versão do dia. Os dois juntos formam a lista de "
                                 "títulos do dia, que vale para LZ, XZ e BN7.")

        from tasks.premio.premio import executar  # import aqui: a Central abre mais rápido

        self._holder = {}
        params = {"bases": bases, "arquivos": arquivos, "bloquear": self.sw_bloquear.isChecked(),
                  "gravar_radar": self.sw_radar.isChecked(), "resultado": self._holder}
        self._tarefa = "mtcaixa"
        self._ir_para(3)
        self.start_task(executar, params, f"Lançamento de prêmio: {', '.join(bases)}")

    def _on_done(self, status: str, message: str):
        super()._on_done(status, message)
        if self._tarefa != "mtcaixa":
            return
        self._tarefa = ""
        res = getattr(self, "_holder", {}).get("res")
        if res is not None and status != "cancelled":
            self._mostrar(res)

    # ----------------------------------------------------------------- exibir
    def _limpar_resultado(self):
        self._res = None
        for v in (self.v_titulos, self.v_radar, self.v_sem):
            v.set_vazio(True)
        self.t_titulos.set("—", "")
        self.t_lanc.set("—", "")
        self.t_nao.set("—", "")
        self.t_sem.set("—", "")
        self._abas_texto(None)
        self.bt_csv.setEnabled(False)
        self.bt_especiais.setEnabled(False)

    def _abas_texto(self, res):
        nomes = ["Títulos do dia", "Radar", "Sem operação", "Execução"]
        if res is not None:
            nomes[0] += f"  {len(res.titulos)}"
            nomes[1] += f"  {len(res.radar)}"
            nomes[2] += f"  {len(res.sem_operacao)}"
        for i, n in enumerate(nomes):
            self.abas._group.button(i).setText(n)

    def _mostrar(self, res, manter_aba: bool = False):
        self._res = res
        lanc = [r for r in res.radar if r.lanca]
        nao = [r for r in res.radar if not r.lanca]
        por_base = {b: sum(1 for r in lanc if r.base == b) for b in res.bases}
        n_dif = sum(1 for t in res.titulos if t.bloqueado)
        n_rep = sum(1 for t in res.titulos if len(t.contas) > 1)
        tot_sem = sum((s.teorico for s in res.sem_operacao if s.teorico is not None), Decimal(0))

        self.t_titulos.set(len(res.titulos), f"{n_rep} repetidos  ·  {n_dif} com PU diferente")
        self.t_lanc.set(len(lanc), "  ·  ".join(f"{b} {n}" for b, n in por_base.items()))
        self.t_nao.set(len(nao), _brl(sum((r.valor_cetip or Decimal(0) for r in nao), Decimal(0))))
        self.t_sem.set(len(res.sem_operacao), f"teórico {_brl(tot_sem)}" if res.sem_operacao else "nenhuma")
        self._abas_texto(res)

        self._preencher_titulos(res)
        self._preencher_radar(res)
        self._preencher_sem(res)
        for v in (self.v_titulos, self.v_radar, self.v_sem):
            v.set_vazio(False)
        self.bt_csv.setEnabled(bool(res.sem_operacao))
        self.bt_especiais.setEnabled(any(s.teorico for s in res.sem_operacao))
        if not manter_aba:
            self._ir_para(1)

    # Títulos ---------------------------------------------------------------
    def _preencher_titulos(self, res):
        from tasks.premio.calculo import fmt_num

        t = theme.current()
        forte, suave = _cores(t)
        arquivos = list(self.P.ARQUIVOS_OPERACOES)
        tb = self.tb_titulos
        tb.setRowCount(len(res.titulos))
        for r, tit in enumerate(res.titulos):
            if len(tit.pus) > 1:   # PUs diferentes: sem zeros à direita, para caber ("5,10 | 5,11")
                pu = " | ".join(fmt_num(p, max(2, -p.normalize().as_tuple().exponent)) for p in sorted(tit.pus))
            else:
                pu = fmt_num(next(iter(tit.pus)), 8)
            data = " | ".join(d.strftime("%d/%m/%Y") for d in sorted(tit.datas))
            bases_pos = ", ".join(b for b in self.P.BASES if b in tit.bases_posicao)
            linha = [
                item(tit.codigo),
                item(tit.tipo_ativo or "—", AL_C, t["ink_faint"] if not tit.tipo_ativo else None),
                item(pu, AL_R, forte["error"] if len(tit.pus) > 1 else None),  # PUs diferentes: "5,10 | 5,11"
                item(data, AL_C, forte["error"] if len(tit.datas) > 1 else None),
            ]
            for arq in arquivos:
                n = len(tit.contas.get(arq, ()))
                linha.append(item(f"{n} conta" + ("s" if n > 1 else "") if n else "—", AL_C,
                                  None if n else t["ink_faint"]))
            if tit.bloqueado:
                linha.append(item("Diferente", AL_C, forte["error"], suave["error"], negrito=True))
            else:
                linha.append(item("✓", AL_C, forte["ok"], negrito=True))
            linha.append(item(bases_pos or "nenhuma", None, None if bases_pos else forte["error"]))
            for c, it in enumerate(linha):
                tb.setItem(r, c, it)
            tb.item(r, 0).setData(Qt.ItemDataRole.UserRole, {
                "rep": len(tit.contas) > 1, "dif": tit.bloqueado, "sem": not tit.bases_posicao})
        self.fil_titulos.contar(0, {"Todos": len(res.titulos),
                                    "Nos dois arquivos": sum(1 for x in res.titulos if len(x.contas) > 1),
                                    "PU diferente": sum(1 for x in res.titulos if x.bloqueado),
                                    "Sem posição": sum(1 for x in res.titulos if not x.bases_posicao)})
        self._filtrar_titulos()

    def _filtrar_titulos(self):
        escolha = self.fil_titulos.escolha(0)
        chave = {"Nos dois arquivos": "rep", "PU diferente": "dif", "Sem posição": "sem"}.get(escolha)
        for r in range(self.tb_titulos.rowCount()):
            dados = self.tb_titulos.item(r, 0).data(Qt.ItemDataRole.UserRole) or {}
            self.tb_titulos.setRowHidden(r, bool(chave) and not dados.get(chave))

    # Radar -----------------------------------------------------------------
    def _preencher_radar(self, res):
        from tasks.premio.calculo import ROTULO, STATUS, fmt_num, fmt_qtd

        t = theme.current()
        forte, suave = _cores(t)
        tb = self.tb_radar
        tb.blockSignals(True)
        tb.setRowCount(len(res.radar))
        for r, row in enumerate(res.radar):
            tom, lanca = STATUS[row.status]
            teorico_base = row.base in self.P.BASES_TEORICO
            dif = row.dif_qtd
            qtd_pos = fmt_qtd(row.qtd_pos)
            if dif not in (None, 0):
                qtd_pos += f" ({fmt_qtd(dif).replace('-', '−')})"
            v_cetip = item(fmt_num(row.valor_cetip), AL_R)
            v_teo = item(fmt_num(row.teorico), AL_R)
            if lanca:
                usado, outro = (v_teo, v_cetip) if teorico_base else (v_cetip, v_teo)
                f = usado.font()
                f.setBold(True)
                usado.setFont(f)
                outro.setForeground(QtGui.QColor(t["ink_muted"]))
            if row.status == "DIVERGE VALOR":
                v_teo.setForeground(QtGui.QColor(forte["warn"]))
            for it in (v_cetip, v_teo):
                if it.text() == "—":
                    it.setForeground(QtGui.QColor(t["ink_faint"]))
            linha = [
                item(row.base, AL_C, t["ink_muted"], negrito=True),
                item(row.conta or "—"),
                item(row.titulo),
                item(row.carteira or "—", None, None if row.carteira else t["ink_faint"]),
                item(fmt_qtd(row.qtd_cetip), AL_R, t["ink_faint"] if row.qtd_cetip is None else None),
                item(qtd_pos, AL_R, forte[tom] if dif not in (None, 0) else
                     (t["ink_faint"] if row.qtd_pos is None else None)),
                v_cetip,
                v_teo,
                item(ROTULO[row.status], AL_C, forte[tom], suave[tom], negrito=True),
            ]
            for c, it in enumerate(linha):
                tb.setItem(r, c, it)
            tb.item(r, 0).setData(Qt.ItemDataRole.UserRole, r)
        tb.blockSignals(False)

        cont_base = {"Todos": len(res.radar)}
        cont_base.update({b: sum(1 for x in res.radar if x.base == b) for b in self.P.BASES})
        self.fil_radar.contar(0, cont_base)
        self.fil_radar.contar(1, {
            "OK": sum(1 for x in res.radar if x.status in ("OK", "CALCULADO")),
            "Com divergência": sum(1 for x in res.radar if x.lanca and x.status not in ("OK", "CALCULADO")),
            "Não lançados": sum(1 for x in res.radar if not x.lanca)})

        # fechamento: CETIP (LZ + XZ) = lançado + não lançado; BN7 à parte
        cetip = [x for x in res.radar if x.base not in self.P.BASES_TEORICO and x.valor_cetip is not None]
        tot = sum((x.valor_cetip for x in cetip), Decimal(0))
        lanc = sum((x.valor_cetip for x in cetip if x.lanca), Decimal(0))
        nao = tot - lanc
        teo = sum((x.teorico for x in res.radar if x.base in self.P.BASES_TEORICO and x.lanca), Decimal(0))
        bases_cetip = " + ".join(b for b in res.bases if b not in self.P.BASES_TEORICO)
        partes = []
        if bases_cetip:
            partes.append(f'<span style="color:{forte["ok"]}; font-weight:600;">✓ {bases_cetip}:</span> '
                          f'CETIP <b>{_brl(tot)}</b> = lançado <b>{_brl(lanc)}</b> + não lançado <b>{_brl(nao)}</b>')
        for b in res.bases:
            if b in self.P.BASES_TEORICO:
                partes.append(f"{b} (teórico) <b>{_brl(teo)}</b>")
        partes.append("negrito = lançado")
        self.lb_fechado.setText("  ·  ".join(partes))

        self._filtrar_radar()
        if tb.rowCount():
            primeira = next((r for r in range(tb.rowCount()) if not tb.isRowHidden(r)), 0)
            tb.selectRow(primeira)
        self._detalhe()

    def _filtrar_radar(self):
        if self._res is None:
            return
        base = self.fil_radar.escolha(0)
        status = self.fil_radar.escolha(1)
        for r, row in enumerate(self._res.radar):
            ok = base in (None, "Todos") or row.base == base
            if status == "OK":
                ok = ok and row.status in ("OK", "CALCULADO")
            elif status == "Com divergência":
                ok = ok and row.lanca and row.status not in ("OK", "CALCULADO")
            elif status == "Não lançados":
                ok = ok and not row.lanca
            self.tb_radar.setRowHidden(r, not ok)

    def _detalhe(self):
        from tasks.premio.calculo import ROTULO, STATUS, fmt_num, fmt_qtd

        t = theme.current()
        forte, suave = _cores(t)
        linhas = self.tb_radar.selectionModel().selectedRows() if self.tb_radar.selectionModel() else []
        if self._res is None or not linhas:
            self.det.setVisible(False)
            return
        row = self._res.radar[linhas[0].row()]
        tom, lanca = STATUS[row.status]
        self.det.setVisible(True)
        titulo = f"{row.base}  /  {row.titulo}"
        if row.conta:
            titulo += f"  /  conta {row.conta}"
        if row.carteira:
            titulo += f"  /  {row.carteira}"
        self.det_titulo.setText(titulo)
        self.det_badge.setText(ROTULO[row.status])
        self.det_badge.setStyleSheet(f"background:{suave[tom]}; color:{forte[tom]}; border-radius:9px;"
                                     f"padding:2px 10px; font-size:11px; font-weight:600;")

        muted = t["ink_muted"]
        kv = []
        n = len(row.trades)
        conta_teo = (f"{fmt_qtd(row.qtd_pos)} ({n} trade{'s' if n != 1 else ''}) × PU {fmt_num(row.pu, 8)} "
                     f"= {fmt_num(row.teorico)} (truncado)") if row.teorico is not None else None
        if row.base in self.P.BASES_TEORICO:
            if conta_teo:
                kv.append(("Teórico", f"<b>{conta_teo}</b>  ·  é o valor lançado"))
            kv.append(("CETIP", "não é comparado (regra do BN7)"))
        else:
            if row.valor_cetip is not None:
                kv.append(("CETIP", f"<b>{fmt_num(row.valor_cetip)}</b>"
                                    + ("  ·  é o valor lançado" if lanca else "")
                                    + f"  ·  quantidade {fmt_qtd(row.qtd_cetip)}"))
            if conta_teo:
                kv.append(("Teórico", conta_teo))
            if row.status == "DIVERGE QTD":
                kv.append(("Quantidade", f'<span style="color:{forte["warn"]};">posição {fmt_qtd(row.qtd_pos)} x '
                                         f'CETIP {fmt_qtd(row.qtd_cetip)} ({fmt_qtd(row.dif_qtd)})</span>'))
            if row.valor_cetip is not None and row.teorico is not None:
                dif = row.valor_cetip - row.teorico
                cor = forte["warn"] if abs(dif) > self.P.TOLERANCIA_VALOR else forte["ok"]
                kv.append(("Diferença", f'<span style="color:{cor};">{fmt_num(dif)}</span>  ·  '
                                        f'tolerância {fmt_num(self.P.TOLERANCIA_VALOR)}'))
        if row.obs:
            kv.append(("Motivo", f'<span style="color:{forte[tom]};">{row.obs}</span>'))
        self.det_corpo.setText("<br>".join(
            f'<span style="color:{muted};">{k}:</span>&nbsp; <span style="color:{t["ink"]};">{v}</span>'
            for k, v in kv))

    # Sem operação -------------------------------------------------------------
    def _preencher_sem(self, res):
        from tasks.premio.calculo import fmt_num, fmt_qtd

        t = theme.current()
        tb = self.tb_sem
        itens = res.sem_operacao
        tb.setRowCount(len(itens) + (1 if itens else 0))
        for r, s in enumerate(itens):
            linha = [
                item(s.base, AL_C, t["ink_muted"], negrito=True),
                item(s.carteira),
                item(s.titulo),
                item(len(s.trades), AL_C, t["ink_muted"]),
                item(fmt_qtd(s.qtd), AL_R),
                item(fmt_num(s.pu, 8) if s.pu is not None else "PU diferente", AL_R,
                     None if s.pu is not None else t["danger"]),
                item(fmt_num(s.teorico), AL_R, None if s.teorico is not None else t["ink_faint"], negrito=True),
            ]
            for c, it in enumerate(linha):
                tb.setItem(r, c, it)
            tb.item(r, 0).setData(Qt.ItemDataRole.UserRole, s.base)
        if itens:
            self._total_sem()
        self.fil_sem.contar(0, {"Todas": len(itens), **{b: sum(1 for s in itens if s.base == b)
                                                        for b in self.P.BASES}})
        self._filtrar_sem()

    def _total_sem(self, base: str | None = None):
        from tasks.premio.calculo import fmt_num

        t = theme.current()
        itens = [s for s in self._res.sem_operacao if base in (None, "Todas") or s.base == base]
        total = sum((s.teorico for s in itens if s.teorico is not None), Decimal(0))
        r = self.tb_sem.rowCount() - 1
        for c in range(self.tb_sem.columnCount()):
            texto = {3: "Total", 6: fmt_num(total)}.get(c, "")
            self.tb_sem.setItem(r, c, item(texto, AL_R if c == 6 else None, fundo=t["field"], negrito=True))

    def _filtrar_sem(self):
        if self._res is None or not self._res.sem_operacao:
            return
        base = self.fil_sem.escolha(0)
        n = len(self._res.sem_operacao)
        for r in range(n):
            self.tb_sem.setRowHidden(r, base not in (None, "Todas") and self.tb_sem.item(r, 0).data(
                Qt.ItemDataRole.UserRole) != base)
        self._total_sem(base)

    # ----------------------------------------------------------------- botões
    def _abrir_pasta(self):
        from tasks.premio.saida import pasta_saida

        open_path(pasta_saida())

    def _exportar_csv(self):
        from app.worker import Falha
        from tasks.premio.saida import gravar_sem_operacao

        if not self._res or not self._res.sem_operacao:
            return
        try:
            caminho = gravar_sem_operacao(self._res.sem_operacao)
        except Falha as exc:
            self.toast(str(exc), "error")
            return
        self.console.log(json_files([caminho], "Posição sem operação exportada"), "files")
        self.toast(f"{caminho.name} gravado.", "ok")

    def _gerar_especiais(self):
        from app.worker import Falha
        from tasks.premio.saida import gravar_especiais

        if not self._res or not self._res.sem_operacao:
            return
        try:
            caminhos = gravar_especiais(self._res.sem_operacao)
        except Falha as exc:
            self.toast(str(exc), "error")
            return
        if not caminhos:
            self.toast("Nenhuma posição com teórico para gerar o MTCAIXA_ESPECIAIS.", "warn")
            return
        self.console.log(json_files(caminhos, "MTCAIXA_ESPECIAIS"), "files")
        self.toast(f"{len(caminhos)} MTCAIXA_ESPECIAIS gravado(s): "
                   + ", ".join(p.name for p in caminhos), "ok")


def json_files(caminhos, titulo: str) -> str:
    import json

    return json.dumps({"titulo": titulo, "caminhos": [str(c) for c in caminhos]}, ensure_ascii=False)
