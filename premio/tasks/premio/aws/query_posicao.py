"""
Query da posição no Athena (Lançamento de prêmio).

>>> TROQUE A QUERY ABAIXO PELA SUA. <<<
Esta é só um rascunho, com base na especificação. Mantenha os campos entre chaves,
que a Central preenche antes de rodar:

    {bases}         bases entre aspas, ex.: 'LZ', 'XZ', 'BN7'
    {titulos}       títulos do dia entre aspas, ex.: 'CRI019000AB', '19F0210606'
    {data_de}       1º dia da janela (D-5 útil ANBIMA), ex.: 2026-11-12
    {data_ate}      último dia da janela (D-1 útil ANBIMA), ex.: 2026-11-18

Se a sua query calcula a janela sozinha, é só não usar {data_de} e {data_ate}.

Colunas que a Central usa (o nome tem que ser este; maiúsculas não importam):
    codigo_sistema, sigla_carteira, CD_CETIP, data_posicao, codigo_operacao,
    tipo_ativo, clearing, qtd_total
As outras colunas (dias_parado, CD_ADM, codigo_lastro...) podem vir: são ignoradas.
"""

QUERY_POSICAO = """
WITH posicao AS (
    SELECT
        p.sigla_sistema_origem                           AS codigo_sistema,
        p.sigla_carteira,
        p.cd_cetip                                       AS CD_CETIP,
        p.data_posicao,
        p.codigo_operacao,
        p.tipo_ativo,
        p.indicador_publico_privado,
        p.codigo_clearing                                AS clearing,
        p.quantidade_total                               AS qtd_total,
        MAX(p.data_posicao) OVER (PARTITION BY p.sigla_sistema_origem, p.sigla_carteira) AS ultima_data
    FROM db_corp_custodiademercadodecapitais_hubdadosinvesmentservices_sor_01.tbih3_posicao_fundo_renda_fixa p
    WHERE p.sigla_sistema_origem IN ({bases})
      AND p.indicador_publico_privado = 'I'
      AND p.codigo_clearing IN ({titulos})
      AND p.data_posicao >= TIMESTAMP '{data_de} 00:00:00'
      AND p.data_posicao <  TIMESTAMP '{data_ate} 23:59:59'
)
SELECT
    codigo_sistema,
    sigla_carteira,
    CD_CETIP,
    data_posicao,
    date_diff('day', data_posicao, (SELECT MAX(ultima_data) FROM posicao)) AS dias_parado,
    codigo_operacao,
    tipo_ativo,
    indicador_publico_privado,
    clearing,
    qtd_total
FROM posicao
WHERE data_posicao = ultima_data
ORDER BY codigo_sistema, sigla_carteira, clearing, codigo_operacao
"""
