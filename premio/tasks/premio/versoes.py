"""
Versões dos arquivos de operações na pasta CETIP (usado pela tela; não depende do pandas).

Sobem várias versões por dia. A tela lista todas e deixa marcada a 1ª do dia.
A ordem é pela data de modificação do arquivo.
"""

from datetime import date, datetime
from pathlib import Path

from . import parametros as P


def _eh_do_arquivo(nome: str, base: str) -> bool:
    nome = nome.lower()
    if not nome.endswith(P.EXTENSOES_OPERACOES):
        return False
    prefixo = P.ARQUIVOS_OPERACOES[base].lower()
    if not nome.startswith(prefixo):
        return False
    # "operacoes" não pode pegar "operacoes_xz"
    maiores = [p.lower() for b, p in P.ARQUIVOS_OPERACOES.items()
               if b != base and p.lower().startswith(prefixo) and len(p) > len(prefixo)]
    return not any(nome.startswith(m) for m in maiores)


def listar_versoes(pasta, base: str) -> list[tuple[Path, datetime]]:
    """Arquivos de operações da base na pasta, do mais antigo para o mais novo."""
    pasta = Path(pasta)
    if not pasta.is_dir():
        return []
    achados = [(p, datetime.fromtimestamp(p.stat().st_mtime))
               for p in pasta.iterdir() if p.is_file() and _eh_do_arquivo(p.name, base)]
    return sorted(achados, key=lambda x: x[1])


def versao_padrao(versoes: list[tuple[Path, datetime]], hoje: date | None = None) -> int:
    """Índice da 1ª versão de hoje; sem versão de hoje, a mais recente. -1 se não houver arquivo."""
    if not versoes:
        return -1
    hoje = hoje or date.today()
    for i, (_, quando) in enumerate(versoes):
        if quando.date() == hoje:
            return i
    return len(versoes) - 1


def rotulo(versoes: list[tuple[Path, datetime]], i: int, hoje: date | None = None) -> str:
    """Texto do item na lista: hora (ou data e hora), marca e nome do arquivo."""
    hoje = hoje or date.today()
    caminho, quando = versoes[i]
    de_hoje = [j for j, (_, q) in enumerate(versoes) if q.date() == hoje]
    quando_txt = quando.strftime("%H:%M") if quando.date() == hoje else quando.strftime("%d/%m %H:%M")
    marca = ""
    if de_hoje and i == de_hoje[0]:
        marca = "1ª do dia"
    elif i == len(versoes) - 1 and len(versoes) > 1:
        marca = "mais recente"
    return "   ".join(x for x in (quando_txt, marca, caminho.name) if x)
