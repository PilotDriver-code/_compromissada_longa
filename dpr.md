# De-para dos privados no Cravar PU: passo a passo

Guia para colocar na Central a lógica do **de-para dos privados**: o consolidado dos
`VCRAPRF.txt` de todas as bases, que o Cravar PU precisa para rodar.

## Como vai funcionar

O de-para fica em `setup\Config\de_para_privados.xlsx` e é gerado pelo botão
**Gerar de-para** da tela Cravar PU, a partir dos `VCRAPRF.txt` que o usuário baixa e
coloca em `setup\Arquivos Conciliacao\SAC\<BASE>\`.

A tela mostra a situação do de-para:

| Situação | Quando | Na tela | No Processar |
|---|---|---|---|
| **Em dia** | O de-para existe e nenhum VCRAPRF é mais novo que ele | Verde, com a data em que foi gerado | Roda normalmente |
| **Desatualizado** | Algum VCRAPRF foi trocado depois de gerar | Amarelo, com quais bases têm arquivo novo | Roda, com aviso no console |
| **Não encontrado** | Ainda não foi gerado | Vermelho | **Bloqueia** até gerar |

Embaixo do campo, uma linha mostra cada base: **verde com ✓** quando o `VCRAPRF.txt` está na
pasta e **vermelha com ✕** quando falta. A tela confere sozinha a cada 4 segundos.

São 6 passos. Os passos 1 a 3 preparam a configuração, o 4 cria o arquivo que recebe a
sua lógica, o 5 muda a tela e o 6 liga o de-para ao seu Cravar PU.

---

## Passo 1: `config.py`

No **final** do arquivo, cole:

```python
# --------------------------------------------------------------------------
# De-para dos privados (Cravar PU)
# --------------------------------------------------------------------------
# Consolidado dos VCRAPRF de todas as bases, gerado pelo botão "Gerar de-para"
# da tela Cravar PU. Fica em setup/Config.
NOME_DE_PARA = "de_para_privados.xlsx"
# Arquivo que o usuário baixa e coloca em setup/<PASTA_SAC>/<BASE>/
NOME_VCRAPRF = "VCRAPRF.txt"
PASTA_SAC = "Arquivos Conciliacao/SAC"
# Bases que entram no consolidado (todas precisam ter o VCRAPRF para gerar)
BASES_DE_PARA = ["LZ", "XZ", "BN7"]
```

> Confira se o nome do arquivo (`VCRAPRF.txt`) e as bases estão certos.

---

## Passo 2: `core/configuracoes.py`

**2a.** No topo, junto dos outros imports:

```python
from datetime import datetime
```

**2b.** No **final** do arquivo:

```python
# De-para dos privados (Cravar PU) -------------------------------------------
def arquivo_de_para() -> Path:
    return pasta("config") / config.NOME_DE_PARA


def arquivo_vcraprf(base: str) -> Path:
    """setup/Arquivos Conciliacao/SAC/<BASE>/VCRAPRF.txt"""
    return pasta_raiz() / config.PASTA_SAC / base / config.NOME_VCRAPRF


@dataclass
class SituacaoDePara:
    estado: str                                   # "ok" | "desatualizado" | "ausente"
    gerado_em: datetime | None = None             # data de gravação do de-para
    vcraprf: dict = field(default_factory=dict)   # base -> Path (só os que existem)
    faltando: list = field(default_factory=list)  # bases sem VCRAPRF na pasta
    mais_novos: list = field(default_factory=list)  # bases com VCRAPRF mais novo que o de-para


def situacao_de_para() -> SituacaoDePara:
    """Confere o de-para e os VCRAPRF de que ele depende.

    ok            -> o de-para existe e nenhum VCRAPRF é mais novo que ele
    desatualizado -> o de-para existe, mas algum VCRAPRF foi trocado depois que ele foi gerado
    ausente       -> o de-para ainda não foi gerado
    """
    vcraprf, faltando = {}, []
    for base in config.BASES_DE_PARA:
        p = arquivo_vcraprf(base)
        if p.is_file():
            vcraprf[base] = p
        else:
            faltando.append(base)

    de_para = arquivo_de_para()
    if not de_para.is_file():
        return SituacaoDePara("ausente", None, vcraprf, faltando)

    gerado_em = datetime.fromtimestamp(de_para.stat().st_mtime)
    mais_novos = [b for b, p in vcraprf.items()
                  if datetime.fromtimestamp(p.stat().st_mtime) > gerado_em]
    estado = "desatualizado" if mais_novos else "ok"
    return SituacaoDePara(estado, gerado_em, vcraprf, faltando, mais_novos)
```

---

## Passo 3: `app/theme.py`

Logo abaixo da linha `#Hint[tone="error"] { color: $danger; }`, acrescente:

```
#Hint[tone="warn"] { color: $warn; }
```

### ✅ Teste dos passos 1 a 3

Rode `python main.py`. A Central deve abrir normalmente, sem nada novo na tela ainda.

---

## Passo 4: Criar `tasks/cravar_pu/de_para.py`

Arquivo novo, ao lado do seu `cravar_pu.py`. **A sua lógica entra na função `consolidar()`.**

```python
"""
De-para dos privados: consolida os VCRAPRF de todas as bases num Excel só.

Quem chama: o botão "Gerar de-para" da tela Cravar PU.
Onde grava: setup/Config/de_para_privados.xlsx (config.NOME_DE_PARA)
De onde lê:  setup/Arquivos Conciliacao/SAC/<BASE>/VCRAPRF.txt, para cada base de config.BASES_DE_PARA

>>> A SUA LÓGICA ENTRA NA FUNÇÃO consolidar(), MAIS ABAIXO. <<<
O resto deste arquivo (conferência dos arquivos, gravação, mensagens na tela) já está pronto.
"""

import contextlib
import io
from pathlib import Path

import pandas as pd

from app.worker import Falha


# ============================================================================
# SUA LÓGICA
# ============================================================================
def consolidar(arquivos: dict[str, Path], destino: Path):
    """
    Recebe:
        arquivos -> {"LZ": Path(".../SAC/LZ/VCRAPRF.txt"), "XZ": ..., "BN7": ...}
                    (todos já conferidos: existem)
        destino  -> Path do Excel final (setup/Config/de_para_privados.xlsx)

    Devolva UMA destas duas coisas:
        a) o DataFrame consolidado  -> a Central grava em `destino` para você; ou
        b) None, se o seu código já grava o Excel sozinho -> nesse caso grave em `destino`.

    print() aparece no console da tela, então pode manter os prints que você já usa.

    Exemplo do formato (apague quando colar o seu código):
        partes = []
        for base, caminho in arquivos.items():
            df = pd.read_csv(caminho, sep=";", dtype=str, encoding="latin-1")
            df["BASE"] = base
            partes.append(df)
        return pd.concat(partes, ignore_index=True)
    """
    raise NotImplementedError


# ============================================================================
# Daqui para baixo: ligação com a tela (não precisa mexer)
# ============================================================================
class _ParaConsole(io.TextIOBase):
    """Manda cada print() da sua lógica para o console da tela."""

    def __init__(self, ctx):
        self.ctx, self._buf = ctx, ""

    def write(self, texto):
        self._buf += texto
        while "\n" in self._buf:
            linha, self._buf = self._buf.split("\n", 1)
            if linha.strip():
                nivel = "error" if linha.lower().startswith("erro") else "step"
                self.ctx.log(linha.strip(), nivel)
        return len(texto)


def gerar(params: dict, ctx) -> str:
    """Chamado pela tela. params = {"bases": [...], "arquivos": {base: caminho}, "destino": caminho}"""
    bases = params["bases"]
    arquivos = {b: Path(c) for b, c in params["arquivos"].items()}
    destino = Path(params["destino"])

    # 1. Conferência: todas as bases precisam do VCRAPRF ---------------------------
    ctx.table("Arquivos VCRAPRF", [
        (base, "OK" if arquivos[base].is_file() else "ERRO") for base in bases
    ])
    faltando = [b for b in bases if not arquivos[b].is_file()]
    if faltando:
        for base in faltando:
            ctx.log(f"{base}: coloque o arquivo em {arquivos[base].parent}", "warn")
        raise Falha(f"Falta o VCRAPRF de: {', '.join(faltando)}. "
                    "Coloque os arquivos nas pastas indicadas e clique em Gerar de-para de novo.")
    ctx.progress(10)
    ctx.check()

    # 2. Consolidação (a sua lógica) ---------------------------------------------
    ctx.log("Consolidando os VCRAPRF...", "step")
    marca_antes = destino.stat().st_mtime if destino.exists() else None
    try:
        with contextlib.redirect_stdout(_ParaConsole(ctx)):
            resultado = consolidar(arquivos, destino)
    except NotImplementedError:
        raise Falha("A lógica do de-para ainda não foi colocada. "
                    "Cole o seu código na função consolidar() de tasks/cravar_pu/de_para.py.") from None
    ctx.progress(80)
    ctx.check()

    # 3. Gravação ------------------------------------------------------------------
    if isinstance(resultado, pd.DataFrame):
        if resultado.empty:
            raise Falha("O de-para ficou vazio. Confira o conteúdo dos VCRAPRF.")
        # grava num arquivo temporário e só depois troca: se der erro no meio,
        # o de-para anterior continua inteiro
        temporario = destino.with_name(destino.stem + "_gerando" + destino.suffix)
        try:
            resultado.to_excel(temporario, index=False)
            temporario.replace(destino)
        except PermissionError:
            raise Falha(f"Não foi possível gravar {destino.name}. "
                        "Se ele estiver aberto no Excel, feche e tente de novo.") from None
        linhas = len(resultado)
    else:
        # o seu código gravou sozinho: confere se o arquivo foi mesmo (re)gravado
        if not destino.exists() or destino.stat().st_mtime == marca_antes:
            raise Falha(f"consolidar() devolveu None, mas {destino.name} não foi gravado. "
                        "Devolva o DataFrame ou grave em `destino`.")
        linhas = None

    ctx.progress(100)
    ctx.files([destino], "De-para gerado")
    if linhas is not None:
        ctx.table("Resumo", [("Bases consolidadas", ", ".join(bases)), ("Linhas", linhas)])
        return f"De-para dos privados gerado com {linhas} linha(s)."
    return "De-para dos privados gerado."
```

---

## Passo 5: `app/pages/cravar_pu.py` (a tela)

**5a. Imports.** No topo, deixe os imports assim:

```python
import config
from core import configuracoes as cfg

from .. import theme
from ..qt import QtCore, QtWidgets, Qt
from ..widgets import ChipGroup, Field, GhostButton, PathDisplay, SwitchRow, hline, label, repolish
from .base import BasePage

W = QtWidgets
```

**5b.** No `__init__`, logo abaixo de `super().__init__(parent)`:

```python
        self._tarefa = None  # "cravar" ou "de_para": qual rotina está rodando no console
```

**5c.** Ainda no `__init__`, **logo depois** de `form.addWidget(self.f_feeder)` e **antes** da
linha da "Pasta de saída", cole:

```python
        # De-para dos privados: caminho + botão na mesma linha, situação embaixo ---------
        self.de_para_display = PathDisplay("file")
        self.btn_de_para = GhostButton("Gerar de-para", "rotate")
        self.btn_de_para.clicked.connect(self._gerar_de_para)
        linha = W.QWidget()
        lay = W.QHBoxLayout(linha)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(self.de_para_display, 1)
        lay.addWidget(self.btn_de_para)
        self.f_de_para = Field("De-para dos privados", linha)
        form.addWidget(self.f_de_para)
        self.lbl_vcraprf = label("", "Hint", wrap=True)   # quais VCRAPRF estão na pasta
        self.lbl_vcraprf.setTextFormat(Qt.TextFormat.RichText)  # permite cor por base
        form.addWidget(self.lbl_vcraprf)
```

**5d.** No **final** do `__init__`, depois de `form.addWidget(self.sw_carteiras)`:

```python
        # Enquanto a tela está aberta, confere a cada 4 s se o usuário colocou/trocou VCRAPRF
        self._relogio = QtCore.QTimer(self)
        self._relogio.setInterval(4000)
        self._relogio.timeout.connect(self._atualizar_de_para)

        self._atualizar_de_para()
```

**5e.** Logo abaixo do `__init__`, cole as duas funções do de-para. É aqui que fica a cor
de cada base (verde/vermelho):

```python
    # De-para -----------------------------------------------------------------
    def _atualizar_de_para(self) -> cfg.SituacaoDePara:
        """Mostra a situação do de-para (OK / desatualizado / não encontrado) e dos VCRAPRF."""
        s = cfg.situacao_de_para()
        self.de_para_display.set_path(cfg.arquivo_de_para())

        if s.estado == "ok":
            self.f_de_para.set_hint(f"Em dia. Gerado em {s.gerado_em:%d/%m/%Y às %H:%M}.", "ok")
        elif s.estado == "desatualizado":
            self.f_de_para.set_hint(
                f"Desatualizado: há VCRAPRF mais novo de {', '.join(s.mais_novos)} "
                f"(de-para gerado em {s.gerado_em:%d/%m/%Y às %H:%M}). "
                "Gere de novo para usar os arquivos novos.", "warn")
        else:
            self.f_de_para.set_hint("Ainda não gerado. Clique em Gerar de-para antes de processar.", "error")

        # Linha dos VCRAPRF: cada base em verde (✓ tem o arquivo) ou vermelho (✕ falta)
        t = theme.current()
        marcas = "&nbsp;&nbsp;&nbsp;".join(
            f'<span style="color:{t["success"]}; font-weight:600;">{b} ✓</span>' if b in s.vcraprf
            else f'<span style="color:{t["danger"]}; font-weight:600;">{b} ✕</span>'
            for b in config.BASES_DE_PARA)
        texto = f"Arquivos {config.NOME_VCRAPRF}:&nbsp;&nbsp;&nbsp;{marcas}"
        if s.faltando:
            pasta = "setup\\" + config.PASTA_SAC.replace("/", "\\") + "\\&lt;BASE&gt;"
            texto += (f'<br><span style="color:{t["warn"]};">Para gerar, coloque o arquivo de '
                      f'{", ".join(s.faltando)} em {pasta}.</span>')
        self.lbl_vcraprf.setText(texto)

        self.btn_de_para.setText("Gerar de-para" if s.estado == "ausente" else "Gerar de novo")
        self.btn_de_para.setEnabled(not self.is_busy())
        return s

    def _gerar_de_para(self):
        if self.is_busy() or not self.ensure_ready():
            return
        params = {
            "bases": list(config.BASES_DE_PARA),
            "arquivos": {b: str(cfg.arquivo_vcraprf(b)) for b in config.BASES_DE_PARA},
            "destino": str(cfg.arquivo_de_para()),
        }
        from tasks.cravar_pu import de_para  # só carrega quando clicar
        self._tarefa = "de_para"
        self.btn_de_para.setEnabled(False)
        self.start_task(de_para.gerar, params, "Gerar de-para dos privados")
```

**5f.** Troque a função `_on_done` inteira por esta (o interruptor "Feeder atualizado" só
desliga depois do Cravar PU, não depois de gerar o de-para):

```python
    def _on_done(self, status: str, message: str):
        super()._on_done(status, message)
        if self._tarefa == "cravar":
            # Cada processamento "gasta" a confirmação: para rodar de novo, confirmar de novo
            self.sw_feeder.setChecked(False)
        self._tarefa = None
        self._atualizar_de_para()
```

**5g.** Troque a função `on_shown` por este bloco (ela + `refresh_icons` + `hideEvent`):

```python
    def on_shown(self):
        super().on_shown()
        self._check_feeder()
        self._atualizar_de_para()
        self._relogio.start()

    def refresh_icons(self):
        super().refresh_icons()
        self._atualizar_de_para()  # ao trocar o tema, refaz as cores da linha dos VCRAPRF

    def hideEvent(self, event):  # noqa: N802 - para de conferir quando sai da tela
        self._relogio.stop()
        super().hideEvent(event)
```

**5h. No `run()`.** Logo **depois** do bloco `if not self._check_feeder(): ... return`, acrescente:

```python
        situacao = self._atualizar_de_para()
        if situacao.estado == "ausente":
            self.toast("Gere o de-para dos privados antes de processar.", "error")
            return
```

No dicionário `params`, acrescente uma linha:

```python
            "de_para": str(cfg.arquivo_de_para()),
```

E troque o final do `run()` (o import e o `start_task`) por:

```python
        from tasks.cravar_pu import cravar_pu  # só carrega quando clicar em Processar
        self._tarefa = "cravar"
        self.btn_de_para.setEnabled(False)
        self.start_task(cravar_pu.executar, params, "Cravar PU")
        if situacao.estado == "desatualizado":
            # deixa rodar, mas registra no console que o de-para é anterior aos VCRAPRF atuais
            self.console.log(
                f"O de-para dos privados está desatualizado (há VCRAPRF mais novo de "
                f"{', '.join(situacao.mais_novos)}). O processamento usa o de-para de "
                f"{situacao.gerado_em:%d/%m/%Y às %H:%M}.", "warn")
```

### ✅ Teste dos passos 4 e 5

Abra o Cravar PU:

1. **De-para dos privados** aparece em vermelho, com "Ainda não gerado". A linha dos VCRAPRF
   mostra cada base em vermelho com ✕.
2. **Processar** é bloqueado, com o aviso "Gere o de-para…".
3. **Gerar de-para sem os VCRAPRF:** o console lista o que falta e em qual pasta colocar.
4. Coloque os `VCRAPRF.txt` nas pastas: em até 4 segundos cada base fica verde com ✓.
5. **Gerar de-para** agora mostra "A lógica do de-para ainda não foi colocada". Isso é
   esperado até você colar o seu código.

---

## Passo 6: Ligar o de-para ao seu Cravar PU

No seu `tasks/cravar_pu/cravar_pu.py`, a variável `arquivo_de_para_PRIVADOS` precisa vir do
caminho que a tela manda, lida **dentro do `executar`**:

```python
def executar(params: dict, ctx) -> str:
    # se a sua variável guarda o CAMINHO do arquivo:
    arquivo_de_para_PRIVADOS = params["de_para"]
    # ou, se ela guarda o Excel já lido:
    # arquivo_de_para_PRIVADOS = pd.read_excel(params["de_para"])
    ...
```

Depois apague a definição fixa que está no topo do arquivo.

---

## Quando você tiver o código do de-para

Cole no lugar do `raise NotImplementedError`, dentro de `consolidar()` em
`tasks/cravar_pu/de_para.py`:

- **Se o seu código monta um DataFrame:** termine com `return df`. A Central grava o Excel.
- **Se ele já salva o Excel sozinho:** salve em `destino` e termine com `return None`.
- **Os seus `print`** continuam aparecendo no console da tela.

Daí em diante, o botão gera o arquivo e a situação fica verde, com "Em dia".

---

## Para ajustar depois

| O quê | Onde |
|---|---|
| Bases que entram no de-para | `BASES_DE_PARA` no `config.py` |
| Nome do VCRAPRF ou do de-para | `NOME_VCRAPRF` / `NOME_DE_PARA` no `config.py` |
| Cores do ✓ e do ✕ | `success` e `danger` em `LIGHT` / `DARK` no `app/theme.py` |
| Intervalo da conferência automática | `self._relogio.setInterval(4000)` (em milissegundos) |
| Bloquear também quando estiver desatualizado | No `run()`, troque `if situacao.estado == "ausente":` por `if situacao.estado != "ok":` |
