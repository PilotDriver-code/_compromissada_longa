# Prêmio: ignorar tipos de título e tirar a operação da descrição

Duas mudanças no Lançamento de prêmio:

1. **Só entram prêmios de CRI, CRA, DEB e NC**, pela coluna **"Tipo Título"** dos arquivos de operações.
   Prêmio de outro tipo (LF, CDB...) é ignorado: não busca posição, não aparece no radar e não entra no
   MTCAIXA. O console mostra quantos foram ignorados de cada tipo.
2. **A descrição do MTCAIXA não leva mais o código da operação.** Continua uma linha por carteira + título,
   com o valor somado de todos os trades.

```
antes:  PAGAMENTO DE PRÊMIO CRI-I CRI020118TT OP1102
depois: PAGAMENTO DE PRÊMIO CRI-I CRI020118TT
```

> Este passo a passo parte do **primeiro zip**, que ainda não ignorava tipos.
> Se você já copiou o zip das 12:31 (que ignora os tipos e acha a coluna "Tipo Título" sozinho), faça só o
> **Passo 6**. Nos dois casos, o mais fácil é copiar o zip novo inteiro por cima.

Arquivos alterados:

| Passo | Arquivo                       | O que muda                                  |
|-------|-------------------------------|---------------------------------------------|
| 1     | `tasks\premio\parametros.py`  | lista dos tipos aceitos                     |
| 2     | `tasks\premio\leitura.py`     | lê a coluna "Tipo Título" e filtra          |
| 3     | `tasks\premio\calculo.py`     | guarda o tipo no título do dia              |
| 4     | `tasks\premio\premio.py`      | aviso no console                            |
| 5     | `app\pages\premio.py`         | coluna Tipo da aba Títulos do dia           |
| 6     | `tasks\premio\saida.py`       | descrição do MTCAIXA sem a operação         |

---

## Passo 1: `tasks\premio\parametros.py`

Logo abaixo de `TIPOS_EVENTO = ["PAGAMENTO DE PREMIO"]`, acrescente:

```python
# Tipos de título que entram. Prêmio de outro tipo (LF, CDB...) é ignorado e aparece como aviso.
TIPOS_TITULO = ["CRI", "CRA", "DEB", "NC"]
```

Para aceitar outro tipo no futuro, é só acrescentar nessa lista.

---

## Passo 2: `tasks\premio\leitura.py`

### 2a. Coluna nova no dicionário `COLUNAS`

Acrescente a última linha:

```python
    "data_liq": "data liquidacao",
    "tipo_titulo": "tipo titulo",       # coluna "Tipo Título": CRI, CRA, DEB, NC...
}
```

Com isso, se o arquivo vier sem a coluna "Tipo Título", a Central para e mostra as colunas que encontrou.

### 2b. Campo novo na classe `LinhaCetip`

No fim da classe, depois de `data_liq: date`:

```python
    tipo_titulo: str = ""  # CRI, CRA, DEB, NC (coluna do arquivo)
```

### 2c. Campo novo na classe `Leitura`

No fim da classe, depois de `total_linhas: int`:

```python
    outros_tipos: dict = None   # tipo de título fora de TIPOS_TITULO -> quantidade (ignorados)
```

> Ele tem que ficar **depois** de `total_linhas`. Antes dele, o Python dá erro ao abrir
> ("non-default argument follows default argument").

### 2d. Na função `ler_operacoes`, a lista dos tipos aceitos

Logo depois da linha `col = {interna: por_nome[nome] for interna, nome in COLUNAS.items()}`:

```python
    tipos_ok = {sem_acento(t) for t in P.TIPOS_TITULO}
```

### 2e. Contador dos ignorados

Troque:

```python
    linhas, invalidas, variacoes = [], [], {}
```

por:

```python
    linhas, invalidas, variacoes, outros_tipos = [], [], {}, {}
```

### 2f. O filtro, dentro do `for`

Entre o `continue` das variações e o `try:`:

```python
            continue
        tipo_titulo = sem_acento(reg[col["tipo_titulo"]])
        if tipo_titulo not in tipos_ok:
            chave = tipo_titulo or "(vazio)"
            outros_tipos[chave] = outros_tipos.get(chave, 0) + 1
            continue
        try:
```

O tipo é comparado sem acento e sem diferenciar maiúsculas (`cri` e `CRI` entram).

### 2g. Guardar o tipo na linha

No fim do `for`, acrescente `tipo_titulo` ao criar a `LinhaCetip`:

```python
        linhas.append(LinhaCetip(arquivo, i, conta, str(reg[col["conta"]]).strip(), titulo,
                                 campos["qtd"], campos["pu"], campos["valor"], data_liq, tipo_titulo))
```

### 2h. Devolver os ignorados

Troque o `return` da função por:

```python
    return Leitura(caminho, arquivo, linhas, invalidas, variacoes, len(df), outros_tipos)
```

---

## Passo 3: `tasks\premio\calculo.py`

### 3a. Campo novo na classe `TituloDia`

Troque a linha `tipo_ativo: str = ""` por:

```python
    tipo_ativo: str = ""          # da posição (ex.: CRI-I), usado na descrição do MTCAIXA
    tipo_titulo: str = ""         # do arquivo de operações (CRI, CRA, DEB, NC)
```

### 3b. Preencher o tipo

Na função `montar_titulos`, logo abaixo de `t.contas[l.arquivo].add(l.conta)`:

```python
        t.tipo_titulo = t.tipo_titulo or l.tipo_titulo
```

---

## Passo 4: `tasks\premio\premio.py` (aviso no console)

No bloco `[1] Leitura`, logo antes de `for tipo, qtd in leitura.variacoes.items():`:

```python
        if leitura.outros_tipos:
            ctx.log(f"{arquivo}: prêmio de outros tipos ignorado: " + ", ".join(
                f"{tipo} {qtd}" for tipo, qtd in sorted(leitura.outros_tipos.items()))
                + f" (entram só {', '.join(P.TIPOS_TITULO)})", "warn")
```

No console, fica assim:

```
! LZ: prêmio de outros tipos ignorado: CDB 1, LF 1 (entram só CRI, CRA, DEB, NC)
```

---

## Passo 5: `app\pages\premio.py` (coluna Tipo da aba Títulos do dia)

Em `_preencher_titulos`, troque:

```python
                item(tit.tipo_ativo or "—", AL_C, t["ink_faint"] if not tit.tipo_ativo else None),
```

por:

```python
                item(tit.tipo_titulo or tit.tipo_ativo or "—", AL_C,
                     None if (tit.tipo_titulo or tit.tipo_ativo) else t["ink_faint"]),
```

Assim a coluna mostra CRI, CRA, DEB ou NC, que vem do arquivo, mesmo quando o título não tem posição.

---

## Passo 6: `tasks\premio\saida.py` (tirar a operação da descrição)

Na função `linha_mtcaixa`, troque:

```python
    descricao = f"{P.DESC_EVENTO} {tipo_ativo} {titulo} {operacao}".strip()
```

por:

```python
    descricao = f"{P.DESC_EVENTO} {tipo_ativo} {titulo}".strip()   # sem o código da operação
```

Se quiser, atualize o comentário da coluna 6, mais abaixo na mesma função:

```python
        descricao,         # 6  PAGAMENTO DE PRÊMIO <tipo_ativo> <título>
```

Não precisa mexer em mais nada:
- O MTCAIXA já sai com **uma linha por carteira + título**, com o valor somado de todos os trades.
- O **MTCAIXA_ESPECIAIS** usa a mesma função, então muda junto.
- Os trades de cada linha continuam no CSV do radar, na coluna `operacoes` (ex.: `OP1102:1.200 | OP1145:800`).

---

## Teste

1. Coloque nos arquivos de operações uma linha de prêmio com "Tipo Título" = `LF` ou `CDB`.
2. Gere o MTCAIXA.
3. No bloco **[1] Leitura** do console, veja o aviso "prêmio de outros tipos ignorado".
4. Na aba **Títulos do dia**, confira se o título ignorado não aparece e se a coluna **Tipo** mostra CRI, CRA,
   DEB ou NC.
5. Abra o `MTCAIXA_LZ.txt`: a coluna 6 deve estar como `PAGAMENTO DE PRÊMIO <tipo> <título>`, sem o código da
   operação.
