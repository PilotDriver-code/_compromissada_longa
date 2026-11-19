# Lançamento de prêmio: como colocar no projeto

## 1. Copie os arquivos

Copie as pastas deste zip para a raiz do projeto (`C:\PyProjects\CENTRAL_RF`). São só arquivos novos, nenhum
arquivo seu é substituído:

```
app\pages\premio.py                tela
tasks\premio\
    __init__.py
    parametros.py                  regras e formatos (bases, tolerância, layout, nomes de arquivo)
    versoes.py                     lista as versões dos arquivos de operações (para a tela)
    leitura.py                     lê Operacoes / operacoes_xz
    calculo.py                     títulos do dia, radar, BN7 teórico, posição sem operação
    saida.py                       MTCAIXA, MTCAIXA_ESPECIAIS e CSVs   <- layout do MTCAIXA aqui
    premio.py                      rotina do botão "Gerar MTCAIXA" (blocos [1] a [4] do console)
    aws\
        __init__.py
        query_posicao.py           <- COLE A SUA QUERY AQUI
        posicao.py                 conexão ODBC (sempre fecha), janela de 5 dias úteis
```

## 2. Coloque a tela no menu

Em `app\pages\__init__.py`, acrescente o import:

```python
from .premio import PremioPage
```

e coloque `PremioPage` na lista, onde quiser que ela apareça no menu:

```python
PAGES = [CravarPUPage, EventosSACPage, PremioPage, ReplicarFluxoPage, AWSPage, ConfiguracoesPage]
```

O ícone (medalha) já vem dentro do `premio.py`, então não precisa mexer no `icons.py`.

## 3. Pasta de saída (recomendado)

Em `config.py`, dentro de `SUBPASTAS`, acrescente:

```python
    "premio_saida":   ("Premio/Saida",     "MTCAIXA, MTCAIXA_ESPECIAIS e radar do Lançamento de prêmio"),
```

Assim a pasta `setup\Premio\Saida` é criada na abertura e aparece na aba Configurações.
Mesmo sem essa linha a tela funciona, porque cria a pasta na primeira execução.

## 4. Cole a sua query

Abra `tasks\premio\aws\query_posicao.py` e troque o rascunho pela sua query. Deixe estes campos, que a Central
preenche antes de rodar:

| Campo        | Vira                                       |
|--------------|--------------------------------------------|
| `{bases}`    | `'LZ', 'XZ', 'BN7'`                        |
| `{titulos}`  | `'CRI019000AB', '19F0210606', ...`         |
| `{data_de}`  | 1º dia da janela (D-5 útil ANBIMA)         |
| `{data_ate}` | último dia da janela (D-1 útil ANBIMA)     |

Se a sua query já calcula os 5 dias sozinha, é só não usar `{data_de}` e `{data_ate}`.

A query pode trazer todas as colunas do seu exemplo. A Central usa só estas (os nomes precisam ser estes,
maiúsculas não importam):

`codigo_sistema, sigla_carteira, CD_CETIP, codigo_operacao, tipo_ativo, clearing, qtd_total`

A quantidade usada é sempre a `qtd_total`. O `CD_CETIP` pode vir como `23854006` ou `23854006.0`.

> A consulta busca as 3 bases de uma vez, mesmo com só uma marcada na tela. A base de cada linha da CETIP sai
> da posição (pela conta + título), então uma conta de BN7 que aparece no arquivo Operacoes não vira
> "sem posição" no LZ.

## 5. Confira o formato do MTCAIXA

O layout segue a especificação: 18 colunas separadas por TAB, cp1252, CRLF, ordenado por carteira e título.

```
seq | dt_liq | carteira | MT | 960 | PAGAMENTO DE PRÊMIO {tipo_ativo} {título} {operação} | valor | | | | N | dt_liq | N | N | REAL | valor | | 5
```

O que costuma precisar de ajuste fica em `tasks\premio\parametros.py`:

```python
FORMATO_DATA = "%d/%m/%Y"   # data de lançamento e de liquidação
SEP_DECIMAL = ","           # 1234,56  (troque para "." se o sistema pedir 1234.56)
```

Para mudar colunas, a ordem ou a descrição, edite a função `linha_mtcaixa()` em `tasks\premio\saida.py`.
O MTCAIXA_ESPECIAIS usa a mesma função.

## 6. Regras implementadas

- **Arquivos:** `Operacoes*.txt` (LZ) e `operacoes_xz*.txt` (XZ), na pasta `setup\Arquivos Conciliacao\CETIP`.
  A lista mostra todas as versões, e a 1ª do dia vem marcada. Sem versão de hoje, vem marcada a mais recente.
  O botão de pasta escolhe um arquivo de outro lugar.
- **Evento:** só "PAGAMENTO DE PREMIO", comparado sem acento e sem diferenciar maiúsculas. Variações como
  "... DETENTOR" ficam de fora e aparecem como aviso. Linhas com quantidade, PU, valor ou data inválidos não
  entram e são listadas no console.
- **Títulos do dia:** juntam os dois arquivos. Se o PU ou a data de um título não baterem, ele **não lança em
  nenhuma base**.
- **Teórico:** `TRUNC(soma das quantidades de todos os trades × PU do prêmio, 2)`, com um truncamento só.
  Tolerância de 0,01 (`TOLERANCIA_VALOR`).
- **LZ / XZ:** uma linha por conta + título da CETIP. Linhas repetidas da mesma conta + título são somadas.
  O valor lançado é o da CETIP.
  - Lançam com alerta: Diverge qtd e Diverge valor.
  - Não lançam: Ambígua (a conta + título está em mais de uma carteira), Sem posição e PU diferente.
- **BN7:** uma linha por carteira + título da posição. Lança sempre o teórico e não é comparado com a CETIP.
- **Operação no MTCAIXA:** quando a carteira + título tem vários trades, entra a operação de maior quantidade.
- **Bloquear se houver divergência:** trava só o MTCAIXA da base que tiver alerta.
- **Posição sem operação:** posição de LZ/XZ em título do dia cuja conta não está na CETIP. Não entra no
  MTCAIXA. Na aba aparecem a quantidade de trades, a soma das quantidades e o teórico. O CSV traz uma linha
  por trade. O MTCAIXA_ESPECIAIS sai um por base, com todas as linhas.
- **Arquivos anteriores:** o MTCAIXA e o MTCAIXA_ESPECIAIS das bases marcadas são apagados no início de cada
  execução, para não sobrar arquivo velho na pasta.

## 7. Teste

1. Coloque um `Operacoes...txt` e um `operacoes_xz...txt` em `setup\Arquivos Conciliacao\CETIP`.
2. Abra a tela **Prêmio**, confira as versões marcadas e clique em **Gerar MTCAIXA**.
3. O console mostra os blocos [1] Leitura, [2] Posição (Athena), [3] Radar e [4] Resultado.
   No fim, a tela abre o Radar.
4. Confira `setup\Premio\Saida`: MTCAIXA_LZ.txt, MTCAIXA_XZ.txt, MTCAIXA_BN7.txt e RADAR_PREMIO_....csv.
5. Na aba **Sem operação**, teste **Exportar CSV** e **Gerar MTCAIXA_ESPECIAIS**.

Se o Athena der erro de coluna ("a query da posição não trouxe a(s) coluna(s): ..."), ajuste os nomes no
SELECT da sua query (pode usar `AS`).
