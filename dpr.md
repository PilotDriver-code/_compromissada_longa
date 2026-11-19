# Prêmio: vigiar a pasta CETIP (versões novas dos arquivos de operações)

Enquanto a tela **Prêmio** está aberta, a Central confere a pasta `setup\Arquivos Conciliacao\CETIP`
**a cada 4 segundos**, igual ao Cravar PU com o de-para.

- **Versão nova:** entra na lista com a marca "mais recente". A versão marcada **não muda sozinha**,
  continua a que você escolheu (por padrão, a 1ª do dia). Embaixo dos arquivos aparece, em laranja:
  `XZ: nova versão às 13:38, não selecionada.`
- **Arquivo marcado sumiu** (apagado ou renomeado): a lista volta para a 1ª do dia e aparece, em vermelho:
  `LZ: a versão marcada saiu da pasta (Operacoes_19112026_0742.txt). Confira a escolha.`
- O aviso some quando você escolhe uma versão na lista daquela base.
- Com a lista aberta, a Central não mexe nela: confere de novo no ciclo seguinte.
- A conferência para quando você sai da tela e enquanto o MTCAIXA está sendo gerado.

Todas as mudanças são em **`app\pages\premio.py`**.

---

## Passo 1: import do QtCore

No topo do arquivo, troque:

```python
from ..qt import QtGui, QtWidgets, Qt, Signal
```

por:

```python
from ..qt import QtCore, QtGui, QtWidgets, Qt, Signal
```

---

## Passo 2: texto padrão e intervalo

Logo abaixo dos imports, antes de `# Ícone do menu`, acrescente:

```python
HINT_ARQUIVOS = ("Padrão: a 1ª versão do dia. Os dois juntos formam a lista de "
                 "títulos do dia, que vale para LZ, XZ e BN7.")
INTERVALO_VIGIA_MS = 4000   # de quanto em quanto tempo a tela confere a pasta CETIP
```

---

## Passo 3: classe `SeletorArquivo`

### 3a. Memória dos arquivos que já estavam na pasta

No `__init__`, troque:

```python
        self._extra: Path | None = None   # arquivo escolhido fora da pasta CETIP
        self.restyle()
```

por:

```python
        self._extra: Path | None = None   # arquivo escolhido fora da pasta CETIP
        self._conhecidos: set | None = None   # arquivos que já estavam na pasta (para achar versão nova)
        self.restyle()
```

### 3b. `recarregar` passa a dizer o que mudou

Troque o começo do método, de `def recarregar(self):` até `self.combo.blockSignals(True)`:

```python
    def recarregar(self):
        from tasks.premio import versoes as V

        atual = self.caminho()
        versoes = V.listar_versoes(self._pasta_fn(), self.base)
        self.combo.blockSignals(True)
```

por:

```python
    def recarregar(self) -> dict:
        """Relista as versões sem trocar a escolhida.

        Devolve {"novas": [(caminho, quando)], "sumiu": nome ou None}:
        novas = versões que apareceram desde a última conferência;
        sumiu = a versão marcada não existe mais (a lista volta para a 1ª do dia).
        """
        from tasks.premio import versoes as V

        atual = self.caminho()
        versoes = V.listar_versoes(self._pasta_fn(), self.base)
        caminhos = {str(p) for p, _ in versoes}
        anteriores = self._conhecidos
        sumiu = Path(atual).name if atual and not Path(atual).is_file() else None
        if anteriores is not None and caminhos == anteriores and not sumiu:
            return {"novas": [], "sumiu": None}          # nada mudou na pasta
        if self.combo.view().isVisible():
            return {"novas": [], "sumiu": None}          # lista aberta: não mexe agora, confere no próximo ciclo
        self._conhecidos = caminhos
        novas = [] if anteriores is None else [(p, q) for p, q in versoes if str(p) not in anteriores]

        self.combo.blockSignals(True)
```

> Quando a pasta não mudou, o método sai logo no começo e não remonta a lista.
> Por isso a conferência a cada 4 s não pisca a tela nem perde a sua escolha.

### 3c. Fim do `recarregar`

No fim do método, depois de `self._tooltip()`, acrescente o `return`:

```python
        self.combo.setCurrentIndex(max(i, 0))
        self.combo.blockSignals(False)
        self._tooltip()
        return {"novas": novas, "sumiu": sumiu}
```

### 3d. Botão de pasta (escolher outro arquivo)

No método `_escolher`, troque:

```python
        self._extra = Path(caminho)
        self.recarregar()
```

por:

```python
        self._extra = Path(caminho)
        self._conhecidos = None   # força montar a lista de novo, já com o arquivo escolhido
        self.recarregar()
```

Sem essa linha, o arquivo escolhido fora da pasta não entraria na lista, porque o conteúdo da pasta não mudou.

---

## Passo 4: classe `PremioPage`, no `__init__`

### 4a. Guardar os avisos

Logo depois de `self._tarefa = ""`:

```python
        self._avisos: dict[str, tuple[str, str]] = {}   # base -> (texto, tom) do aviso dos arquivos
```

### 4b. O relógio

Logo depois de `self._limpar_resultado()` (última linha do `__init__`):

```python
        # Enquanto a tela está aberta, confere a pasta CETIP a cada 4 s (versão nova, arquivo que sumiu)
        self._relogio = QtCore.QTimer(self)
        self._relogio.setInterval(INTERVALO_VIGIA_MS)
        self._relogio.timeout.connect(self._vigiar_arquivos)
```

---

## Passo 5: `_painel_parametros`

Troque:

```python
        self.f_arquivos = Field("Arquivos de operações CETIP", caixa,
                                "Padrão: a 1ª versão do dia. Os dois juntos formam a lista de "
                                "títulos do dia, que vale para LZ, XZ e BN7.")
```

por:

```python
        for base, s in self.seletores.items():
            s.combo.activated.connect(lambda _, b=base: self._limpar_aviso(b))   # o usuário escolheu
        self.f_arquivos = Field("Arquivos de operações CETIP", caixa, HINT_ARQUIVOS)
```

> O `activated` só dispara quando **você** escolhe na lista; a atualização automática não dispara.
> Assim o aviso some só quando você mesmo olhou e escolheu.

---

## Passo 6: ligar e desligar a conferência + os métodos novos

Troque o `on_shown` inteiro:

```python
    def on_shown(self):
        super().on_shown()
        for s in self.seletores.values():
            s.recarregar()
        self._status_aws()
```

por:

```python
    def on_shown(self):
        super().on_shown()
        self._vigiar_arquivos()
        self._relogio.start()
        self._status_aws()

    def hideEvent(self, event):  # noqa: N802 - para de conferir quando sai da tela
        self._relogio.stop()
        super().hideEvent(event)

    # Vigia da pasta CETIP -------------------------------------------------------
    def _vigiar_arquivos(self):
        if self.is_busy():
            return
        for base, s in self.seletores.items():
            r = s.recarregar()
            if r["sumiu"]:
                self._avisos[base] = (f"{base}: a versão marcada saiu da pasta ({r['sumiu']}). "
                                      f"Confira a escolha.", "error")
            elif r["novas"]:
                p, quando = r["novas"][-1]
                self._avisos[base] = (f"{base}: nova versão às {quando:%H:%M}, não selecionada.", "warn")
        self._mostrar_avisos()

    def _limpar_aviso(self, base: str):
        self._avisos.pop(base, None)
        self._mostrar_avisos()

    def _mostrar_avisos(self):
        if not self._avisos:
            self.f_arquivos.set_hint(HINT_ARQUIVOS)
            return
        tom = "error" if any(t == "error" for _, t in self._avisos.values()) else "warn"
        self.f_arquivos.set_hint("\n".join(txt for txt, _ in self._avisos.values()), tom)
```

---

## Passo 7: `run()`

No `run`, troque:

```python
            self.toast(f"Arquivo de operações não encontrado: {', '.join(faltando)}. Escolha de novo.", "error")
            for s in self.seletores.values():
                s.recarregar()
            return
        self.f_arquivos.set_hint("Padrão: a 1ª versão do dia. Os dois juntos formam a lista de "
                                 "títulos do dia, que vale para LZ, XZ e BN7.")
```

por:

```python
            self.toast(f"Arquivo de operações não encontrado: {', '.join(faltando)}. Escolha de novo.", "error")
            self._vigiar_arquivos()
            return
        self._mostrar_avisos()
```

Assim, clicar em **Gerar MTCAIXA** não apaga um aviso de versão nova que ainda está valendo.

---

## Teste

1. Abra a tela **Prêmio** e veja a versão marcada de cada base.
2. Com a tela aberta, coloque uma versão nova do `operacoes_xz` na pasta CETIP.
3. Em até 4 segundos aparece `XZ: nova versão às HH:MM, não selecionada.`, e a versão marcada continua a mesma.
4. Abra a lista do XZ: a versão nova está lá com a marca "mais recente". Escolha qualquer versão e o aviso
   some.
5. Renomeie o arquivo marcado do LZ: em até 4 segundos aparece o aviso vermelho, e a lista volta para a 1ª do
   dia.

Para mudar o intervalo, troque o `INTERVALO_VIGIA_MS` (em milissegundos) do Passo 2.
