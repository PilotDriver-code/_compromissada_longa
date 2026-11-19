# Prêmio: lista de versões dos arquivos com o visual da Central

A lista que abre ao clicar no arquivo do LZ/XZ passa a ter:

- **abre embaixo da caixa**, sem cobrir a caixa, e sem as faixas pretas nem a moldura do Windows;
- **cantos arredondados**, fundo e borda nas cores do tema (claro e escuro);
- cada versão em colunas alinhadas: **hora | etiqueta | nome do arquivo**;
- etiqueta **"1ª do dia"** em laranja e **"mais recente"** em cinza;
- a versão marcada em **negrito com ✓**, e destaque suave ao passar o mouse;
- largura do tamanho do maior nome (nome muito grande é cortado no meio com "...").

Mudam 2 arquivos: `tasks\premio\versoes.py` e `app\pages\premio.py`.

---

## Passo 1: `tasks\premio\versoes.py`

Troque a função `rotulo` inteira (é a última do arquivo) por estas duas.
A nova `partes` devolve hora, etiqueta e nome separados, para a lista desenhar cada um com seu estilo:

```python
def partes(versoes: list[tuple[Path, datetime]], i: int, hoje: date | None = None) -> tuple[str, str, str]:
    """(hora, marca, nome) de um item da lista. Hora vira "dd/mm hh:mm" quando não é de hoje."""
    hoje = hoje or date.today()
    caminho, quando = versoes[i]
    de_hoje = [j for j, (_, q) in enumerate(versoes) if q.date() == hoje]
    quando_txt = quando.strftime("%H:%M") if quando.date() == hoje else quando.strftime("%d/%m %H:%M")
    marca = ""
    if de_hoje and i == de_hoje[0]:
        marca = "1ª do dia"
    elif i == len(versoes) - 1 and len(versoes) > 1:
        marca = "mais recente"
    return quando_txt, marca, caminho.name


def rotulo(versoes: list[tuple[Path, datetime]], i: int, hoje: date | None = None) -> str:
    """Texto do item (aparece na caixa fechada): hora, marca e nome do arquivo."""
    return "   ".join(x for x in partes(versoes, i, hoje) if x)
```

---

## Passo 2: `app\pages\premio.py`, a lista nova

Cole este bloco **logo antes** da linha `class SeletorArquivo(W.QWidget):`.
Ele cria a `ComboVersoes` (a caixa) e o `_VersaoDelegate` (quem desenha cada linha da lista):

```python
PARTES_ROLE = Qt.ItemDataRole.UserRole + 1   # (hora, marca, nome) de cada versão, para desenhar a lista


class _VersaoDelegate(W.QStyledItemDelegate):
    """Desenha cada versão da lista: hora | etiqueta (1ª do dia / mais recente) | nome do arquivo | ✓."""

    ALTURA = 34

    def __init__(self, combo: W.QComboBox):
        super().__init__(combo)
        self.combo = combo

    def _partes(self, index):
        partes = index.data(PARTES_ROLE)
        return partes if partes else ("", "", index.data(Qt.ItemDataRole.DisplayRole) or "")

    def _largura_hora(self, fm) -> int:
        horas = [self._partes(self.combo.model().index(r, 0))[0] for r in range(self.combo.count())]
        return max([fm.horizontalAdvance(h) for h in horas if h] or [0])

    def _largura_etiqueta(self, fonte: QtGui.QFont) -> int:
        """Espaço reservado para a etiqueta, igual em todas as linhas (os nomes ficam alinhados)."""
        fme = QtGui.QFontMetrics(self._fonte_etiqueta(fonte))
        marcas = [self._partes(self.combo.model().index(r, 0))[1] for r in range(self.combo.count())]
        larguras = [fme.horizontalAdvance(m) + 14 for m in marcas if m]
        return max(larguras) + 10 if larguras else 0

    @staticmethod
    def _fonte_etiqueta(base: QtGui.QFont) -> QtGui.QFont:
        f = QtGui.QFont(base)
        f.setPointSizeF(max(7.0, base.pointSizeF() - 1.5))
        f.setBold(True)
        return f

    def sizeHint(self, option, index):  # noqa: N802 - API Qt
        hora, marca, nome = self._partes(index)
        fm = option.fontMetrics
        w = 12 + self._largura_hora(fm) + 12 + self._largura_etiqueta(option.font)
        w += fm.horizontalAdvance(nome) + 12 + 16 + 12
        return QtCore.QSize(w, self.ALTURA)

    def paint(self, painter, option, index):
        t = theme.current()
        hora, marca, nome = self._partes(index)
        r = option.rect.adjusted(4, 2, -4, -2)
        ativo = bool(option.state & (W.QStyle.StateFlag.State_MouseOver | W.QStyle.StateFlag.State_Selected))
        marcado = index.row() == self.combo.currentIndex()

        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        if ativo:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QtGui.QColor(t["hover"]))
            painter.drawRoundedRect(QtCore.QRectF(r), 6, 6)

        fm = option.fontMetrics
        x = r.left() + 10
        meio = r.center().y()
        alto = fm.height()

        # hora
        painter.setFont(option.font)
        painter.setPen(QtGui.QColor(t["ink_muted"]))
        larg_hora = self._largura_hora(fm)
        if hora:
            painter.drawText(QtCore.QRect(x, meio - alto // 2, larg_hora, alto),
                             int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), hora)
            x += larg_hora + 12

        # etiqueta (o espaço é reservado mesmo sem etiqueta, para alinhar os nomes)
        x_nome = x + self._largura_etiqueta(option.font)
        if marca:
            fe = self._fonte_etiqueta(option.font)
            fme = QtGui.QFontMetrics(fe)
            pill = QtCore.QRectF(x, meio - 9, fme.horizontalAdvance(marca) + 14, 18)
            if marca == "1ª do dia":
                fundo, cor, borda = t["accent_soft"], t["accent_text"], t["accent_soft"]
            else:
                fundo, cor, borda = t["field"], t["ink_muted"], t["border"]
            painter.setPen(QtGui.QPen(QtGui.QColor(borda), 1))
            painter.setBrush(QtGui.QColor(fundo))
            painter.drawRoundedRect(pill, 9, 9)
            painter.setFont(fe)
            painter.setPen(QtGui.QColor(cor))
            painter.drawText(pill, int(Qt.AlignmentFlag.AlignCenter), marca)
        x = x_nome

        # nome do arquivo (corta com "..." se faltar espaço) e ✓ na versão marcada
        painter.setFont(option.font)
        fim = r.right() - 12 - (16 if marcado else 0)
        texto = fm.elidedText(nome, Qt.TextElideMode.ElideMiddle, max(0, fim - x))
        painter.setPen(QtGui.QColor(t["ink"]))
        f = QtGui.QFont(option.font)
        f.setBold(marcado)
        painter.setFont(f)
        painter.drawText(QtCore.QRect(x, meio - alto // 2, max(0, fim - x), alto),
                         int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), texto)
        if marcado:
            painter.setPen(QtGui.QColor(t["accent"]))
            painter.drawText(QtCore.QRect(r.right() - 24, meio - alto // 2, 16, alto),
                             int(Qt.AlignmentFlag.AlignCenter), "✓")
        painter.restore()


class ComboVersoes(W.QComboBox):
    """Lista de versões com o visual da Central: abre embaixo da caixa, cantos arredondados, sem moldura do Windows."""

    def __init__(self):
        super().__init__()
        lista = W.QListView()
        lista.setUniformItemSizes(True)
        lista.setMouseTracking(True)
        lista.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setView(lista)
        lista.setItemDelegate(_VersaoDelegate(self))
        self.setMaxVisibleItems(8)
        janela = lista.window()   # a "caixinha" que segura a lista aberta
        janela.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
                              | Qt.WindowType.NoDropShadowWindowHint)
        janela.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def showPopup(self):  # noqa: N802 - API Qt
        # a lista aberta fica do tamanho do maior item (no mínimo, da largura da caixa)
        opcao = W.QStyleOptionViewItem()
        opcao.initFrom(self.view())
        delegate = self.view().itemDelegate()
        maior = max((delegate.sizeHint(opcao, self.model().index(r, 0)).width()
                     for r in range(self.count())), default=0)
        tela = self.screen().availableGeometry().width() if self.screen() else 1600
        self.view().setMinimumWidth(min(max(self.width(), maior + 16), tela - 40))
        super().showPopup()

```

> Confira se o import do topo tem o `QtCore` (ele entrou no passo a passo da vigia da pasta):
> `from ..qt import QtCore, QtGui, QtWidgets, Qt, Signal`

---

## Passo 3: `SeletorArquivo.__init__`, usar a lista nova

Troque:

```python
        self.combo = W.QComboBox()
        self.combo.setMinimumWidth(120)
        self.combo.setSizeAdjustPolicy(W.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo.view().setTextElideMode(Qt.TextElideMode.ElideNone)
```

por:

```python
        self.combo = ComboVersoes()
        self.combo.setMinimumWidth(120)
        self.combo.setSizeAdjustPolicy(W.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
```

---

## Passo 4: `SeletorArquivo.recarregar`, mandar as partes de cada versão

Troque:

```python
        for i, (p, _) in enumerate(versoes):
            self.combo.addItem(V.rotulo(versoes, i), str(p))
        if self._extra and self._extra.is_file() and self.combo.findData(str(self._extra)) < 0:
            quando = datetime.fromtimestamp(self._extra.stat().st_mtime).strftime("%d/%m %H:%M")
            self.combo.addItem(f"{quando}   escolhido   {self._extra.name}", str(self._extra))
```

por:

```python
        for i, (p, _) in enumerate(versoes):
            self.combo.addItem(V.rotulo(versoes, i), str(p))
            self.combo.setItemData(self.combo.count() - 1, V.partes(versoes, i), PARTES_ROLE)
        if self._extra and self._extra.is_file() and self.combo.findData(str(self._extra)) < 0:
            quando = datetime.fromtimestamp(self._extra.stat().st_mtime).strftime("%d/%m %H:%M")
            self.combo.addItem(f"{quando}   escolhido   {self._extra.name}", str(self._extra))
            self.combo.setItemData(self.combo.count() - 1, (quando, "escolhido", self._extra.name), PARTES_ROLE)
```

(A caixa fechada continua mostrando o texto do `rotulo`; a lista aberta usa as partes.)

---

## Passo 5: `SeletorArquivo.restyle`, cores da caixa e da lista

Troque o método `restyle` da classe `SeletorArquivo` inteiro por:

```python
    def restyle(self):
        t = theme.current()
        self.tag.setStyleSheet(f"background:{t['field']}; border:1px solid {t['border']}; border-radius:6px;"
                               f"padding:6px 0; font-weight:600; color:{t['ink_muted']}; font-size:12px;")
        self.combo.setStyleSheet(f"""
            QComboBox {{ background: {t['field']}; border: 1px solid {t['border']}; border-radius: 8px;
                         padding: 6px 10px; color: {t['ink']}; font-size: 12px; min-height: 22px;
                         combobox-popup: 0; }}
            QComboBox:hover, QComboBox:on {{ border-color: {t['border_strong']}; }}
            QComboBox::drop-down {{ border: none; width: 26px; }}
            QComboBox::down-arrow {{ image: url("{theme._svg_asset('chevron-down', t['ink_muted'])}");
                                     width: 12px; height: 12px; }}
        """)
        # lista aberta: fundo, borda e cantos arredondados (a janela em volta é transparente)
        self.combo.view().setStyleSheet(f"""
            QListView {{ background: {t['surface']}; color: {t['ink']}; border: 1px solid {t['border_strong']};
                         border-radius: 10px; padding: 4px; outline: 0; font-size: 12px; }}
            QListView::item {{ border: none; }}
        """)
```

O que mudou nele:

- `combobox-popup: 0` faz a lista abrir **embaixo** da caixa (sem isso, ela abre por cima e o Windows
  desenha as faixas pretas de rolagem);
- o estilo da lista aberta saiu do `QComboBox QAbstractItemView` e foi para `self.combo.view()`, com borda
  arredondada; a seleção e o destaque agora são desenhados pelo `_VersaoDelegate`.

---

## Teste

1. Abra a tela **Prêmio** e clique no arquivo do XZ.
2. A lista abre embaixo da caixa, sem faixas pretas, com "1ª do dia" em laranja, "mais recente" em cinza e ✓
   na versão marcada.
3. Troque o tema (lua/sol no canto) e abra de novo: as cores acompanham.
