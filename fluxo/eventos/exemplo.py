"""
Exemplo com dados fictícios no mesmo formato do resultado da query.

Intervalo analisado: 07/11/2026 (sáb) a 10/11/2026 (ter)
  -> dia útil 09/11: eventos de 07, 08 e 09/11 (analisados juntos)
  -> dia útil 10/11: eventos de 10/11

Gera os Excel ANTES e DEPOIS na pasta "saida_exemplo" (raiz do projeto).
Para os dados reais, use eventos/rodar.py.

Como rodar (a partir da pasta raiz do projeto):
    python -m eventos.exemplo
ou pelo botão "Run" do VS Code com este arquivo aberto.
"""

import sys
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
if str(RAIZ_PROJETO) not in sys.path:          # permite rodar o arquivo direto
    sys.path.insert(0, str(RAIZ_PROJETO))

import pandas as pd                                 # noqa: E402

from eventos import tratamento_fluxo as tf          # noqa: E402
from eventos.exportacao import gerar_excels         # noqa: E402

pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 20)
pd.set_option("display.max_colwidth", 70)
pd.set_option("display.float_format", lambda v: f"{v:.10f}".rstrip("0").rstrip("."))

DATA_INICIAL = "2026-11-07"
DATA_FINAL = "2026-11-10"

COLUNAS = [
    "codigo_lastro", "data_evento", "sigla_evento", "percentual_juros_evento",
    "sigla_sistema_origem", "tipo_ativo", "data_vencimento", "codigo_clearing", "origem_selecao",
]
BASE, IRMAO = "EVENTO_NO_INTERVALO", "IRMAO_SEM_EVENTO"


def montar_exemplo() -> pd.DataFrame:
    def ev(lastro, data, sigla, perc, clearing, origem=BASE, tipo="CRI", venc="2030-12-31"):
        return (lastro, data, sigla, perc, "LZ", tipo, venc, clearing, origem)

    def vazio(lastro, clearing, tipo="CRI", venc="2030-12-31"):
        return (lastro, None, None, None, "LZ", tipo, venc, clearing, IRMAO)

    linhas = [
        # ATIVO_A: L001 tem evento; L002 (vazio) e L003 (só linhas antigas) são irmãos
        ev("L001", "2026-05-07", "J", 0.48, "ATIVO_A"),           # fora do intervalo
        ev("L001", "2026-11-07", "J", 0.48, "ATIVO_A"),           # sáb -> dia útil 09/11 (Caso 1)
        ev("L001", "2026-11-10", "J", 0.48, "ATIVO_A"),           # ter -> dia útil 10/11 (Caso 1)
        ev("L001", "2030-12-31", "I", 100, "ATIVO_A"),            # vencimento
        vazio("L002", "ATIVO_A"),                                  # irmão sem nenhum evento
        ev("L003", "2025-03-10", "J", 0.50, "ATIVO_A", IRMAO),    # irmão com linhas antigas
        ev("L003", "2025-03-10", "I", 100, "ATIVO_A", IRMAO),

        # ATIVO_B: J no sábado + I na segunda -> mesmo dia útil -> já tem I (Caso 3)
        ev("L004", "2026-11-07", "J", 0.30, "ATIVO_B"),
        ev("L004", "2026-11-09", "I", 50, "ATIVO_B"),

        # ATIVO_C: J + L no domingo + B na segunda -> Caso 4
        ev("L005", "2026-11-08", "J", 0.70, "ATIVO_C"),
        ev("L005", "2026-11-08", "L", 100, "ATIVO_C"),
        ev("L005", "2026-11-09", "B", 0, "ATIVO_C"),

        # ATIVO_D: J no sábado + J na segunda -> repetido no mesmo dia útil -> pendência
        ev("L006", "2026-11-07", "J", 0.20, "ATIVO_D"),
        ev("L006", "2026-11-09", "J", 0.25, "ATIVO_D"),

        # ATIVO_E: L007 tem evento em 09/11, L008 em 10/11 -> cada um falta num dia útil
        ev("L007", "2026-11-09", "J", 0.40, "ATIVO_E"),
        ev("L007", "2026-11-09", "M", 0, "ATIVO_E"),              # Caso 2
        ev("L008", "2026-11-10", "J", 0.40, "ATIVO_E"),           # Caso 1

        # ATIVO_F: J + B (sem L) -> exclui B, J = mínimo, inclui I
        ev("L009", "2026-11-10", "J", 0.90, "ATIVO_F"),
        ev("L009", "2026-11-10", "B", 0, "ATIVO_F"),

        # ATIVO_G: código desconhecido -> pendência
        ev("L010", "2026-11-09", "J", 1.0, "ATIVO_G"),
        ev("L010", "2026-11-09", "X", 5, "ATIVO_G"),

        # ATIVO_H: irmão com evento só M (sem J) -> par J+I usa a data do M
        ev("L011", "2026-11-08", "M", 0, "ATIVO_H"),
        vazio("L012", "ATIVO_H"),

        # Lastro sem cadastro (codigo_clearing vazio) -> pendência
        ev("L013", "2026-11-09", "J", 0.60, None, tipo=None, venc=None),
    ]
    return pd.DataFrame(linhas, columns=COLUNAS)


if __name__ == "__main__":
    antes, depois, res = gerar_excels(montar_exemplo(), DATA_INICIAL, DATA_FINAL,
                                      RAIZ_PROJETO / "saida_exemplo")
    print(f"Excel ANTES:  {antes}")
    print(f"Excel DEPOIS: {depois}\n")

    print("=== FLUXO TRATADO (final) ===")
    print(res.fluxo_tratado.to_string(index=False))
    print("\n=== LOG DE ALTERAÇÕES ===")
    print(res.log_alteracoes.to_string(index=False))
    print("\n=== DIAGNÓSTICO ===")
    print(res.diagnostico.to_string(index=False))
    print("\n=== PENDÊNCIAS ===")
    print(res.pendencias.to_string(index=False))
    print("\n=== RESUMO ===")
    for k, v in res.resumo.items():
        print(f"{k}: {v}")
