"""
Parâmetros do Lançamento de prêmio. É aqui que se ajusta a regra sem mexer no resto.
"""

from decimal import Decimal

# ---------------------------------------------------------------------------
# Bases e arquivos de operações da CETIP
# ---------------------------------------------------------------------------
BASES = ["LZ", "XZ", "BN7"]

# Arquivo de operações de cada base, pelo começo do nome (sem diferenciar maiúsculas).
# Os arquivos ficam em setup/Arquivos Conciliacao/CETIP. Ex.: Operacoes_19112026_0742.txt
ARQUIVOS_OPERACOES = {
    "LZ": "operacoes",
    "XZ": "operacoes_xz",
}
EXTENSOES_OPERACOES = (".txt",)

# Bases que lançam sempre o valor TEÓRICO (quantidade da posição x PU do prêmio, truncado).
# As outras lançam o valor da CETIP e só conferem com o teórico.
BASES_TEORICO = {"BN7"}

# ---------------------------------------------------------------------------
# Evento
# ---------------------------------------------------------------------------
# "Tipo Operação" que entra (comparado sem acento e sem diferenciar maiúsculas)
TIPOS_EVENTO = ["PAGAMENTO DE PREMIO"]

# Diferença aceita entre o valor da CETIP e o teórico (o teórico trunca uma vez só)
TOLERANCIA_VALOR = Decimal("0.01")

# ---------------------------------------------------------------------------
# Athena
# ---------------------------------------------------------------------------
DSN_ATHENA = "AWS Athena ODBC"
DIAS_POSICAO = 5          # janela da posição: últimos 5 dias úteis (ANBIMA) antes de hoje

# ---------------------------------------------------------------------------
# MTCAIXA (layout em tasks/premio/saida.py, função linha_mtcaixa)
# ---------------------------------------------------------------------------
COD_LANC = "960"
DESC_EVENTO = "PAGAMENTO DE PRÊMIO"
FORMATO_DATA = "%d/%m/%Y"   # data de lançamento e de liquidação
SEP_DECIMAL = ","           # separador decimal do valor no MTCAIXA ("," ou ".")
ENCODING_MTCAIXA = "cp1252"

# Nomes dos arquivos gerados (em setup/Premio/Saida)
NOME_MTCAIXA = "MTCAIXA_{base}.txt"
NOME_ESPECIAIS = "MTCAIXA_ESPECIAIS_{base}.txt"
NOME_RADAR = "RADAR_PREMIO_{carimbo}.csv"
NOME_SEM_OPERACAO = "POSICAO_SEM_OPERACAO_{carimbo}.csv"
