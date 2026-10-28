"""
Validacao independente dos padroes plantados em cooperativa_horizonte_sul.db.

Este script NAO importa nada de gerar_dados.py e nao reusa a logica de
geracao. Ele so roda queries diretas no banco ja gerado, para que a
validacao nao possa "confirmar a si mesma" usando as mesmas contas do
gerador. Roda depois de `python scripts/gerar_dados.py`.
"""

import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "database" / "cooperativa_horizonte_sul.db"
SQL_PATH = BASE_DIR / "database" / "cooperativa_horizonte_sul.sql"

MESES_CURVA = [
    "2025-10-31", "2025-11-30", "2025-12-31", "2026-01-31", "2026-02-28", "2026-03-31",
    "2026-04-30", "2026-05-31", "2026-06-30", "2026-07-31", "2026-08-31", "2026-09-30",
]


def linha(titulo):
    print()
    print("=" * 78)
    print(titulo)
    print("=" * 78)


def contagens_por_tabela(cur):
    linha("CONTAGEM DE LINHAS POR TABELA")
    for tabela in ("dim_cooperado", "dim_pa", "dim_produto", "fato_contrato", "fato_parcela", "meta_mensal"):
        total = cur.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
        print(f"{tabela}: {total}")


def qualidade_de_dados(cur):
    linha("QUALIDADE DE DADOS (inconsistencias propositais, contagem de evidencia)")

    duplicados = cur.execute(
        "SELECT COUNT(*) FROM (SELECT cooperado_id FROM dim_cooperado "
        "GROUP BY cooperado_id HAVING COUNT(*) > 1)"
    ).fetchone()[0]
    print(f"cooperado_id duplicados em dim_cooperado: {duplicados}")

    orfas = cur.execute(
        "SELECT COUNT(*) FROM fato_parcela p "
        "LEFT JOIN fato_contrato c ON p.contrato_id = c.contrato_id "
        "WHERE c.contrato_id IS NULL"
    ).fetchone()[0]
    print(f"parcelas orfas (sem contrato): {orfas}")

    nivel_risco_nulo = cur.execute(
        "SELECT COUNT(*) FROM fato_contrato WHERE nivel_risco IS NULL"
    ).fetchone()[0]
    print(f"contratos com nivel_risco nulo: {nivel_risco_nulo}")

    variantes_tipo_pessoa = cur.execute(
        "SELECT DISTINCT tipo_pessoa FROM dim_cooperado ORDER BY tipo_pessoa"
    ).fetchall()
    print(f"variantes de escrita em tipo_pessoa: {[v[0] for v in variantes_tipo_pessoa]}")

    variantes_garantia = cur.execute(
        "SELECT DISTINCT garantia FROM fato_contrato ORDER BY garantia"
    ).fetchall()
    print(f"variantes de escrita em garantia: {[v[0] for v in variantes_garantia]}")

    pagamento_antes_contratacao = cur.execute(
        "SELECT COUNT(*) FROM fato_parcela p "
        "JOIN fato_contrato c ON p.contrato_id = c.contrato_id "
        "WHERE p.data_pagamento IS NOT NULL AND p.data_pagamento < c.data_contratacao"
    ).fetchone()[0]
    print(f"parcelas com pagamento antes da contratacao: {pagamento_antes_contratacao}")


def padrao_1_produto_risco(cur):
    linha("PADRAO 1: produto 'Credito Pessoal' concentra inadimplencia 90+")
    cur.execute("""
        SELECT d.nome_produto,
               SUM(CASE WHEN p.data_pagamento IS NULL
                         AND julianday('2026-09-30') - julianday(p.data_vencimento) > 90
                    THEN p.valor_parcela ELSE 0 END) as saldo_90,
               SUM(p.valor_parcela) as saldo_total
        FROM fato_parcela p
        JOIN fato_contrato c ON p.contrato_id = c.contrato_id
        JOIN dim_produto d ON c.produto_id = d.produto_id
        WHERE p.data_pagamento IS NULL
        GROUP BY d.nome_produto
        ORDER BY saldo_90 DESC
    """)
    for nome, saldo_90, saldo_total in cur.fetchall():
        pct = saldo_90 / saldo_total if saldo_total else 0
        print(f"{nome:<28} saldo_90+={saldo_90:>14,.2f}  %_sobre_saldo_aberto={pct:.1%}")


def padrao_2_pa_concentrado(cur):
    linha("PADRAO 2: PA Centro e PA Industrial concentram atraso")
    cur.execute("""
        SELECT pa.nome_pa,
               SUM(CASE WHEN p.data_pagamento IS NULL
                         AND julianday('2026-09-30') - julianday(p.data_vencimento) > 90
                    THEN p.valor_parcela ELSE 0 END) as saldo_90,
               SUM(p.valor_parcela) as saldo_total
        FROM fato_parcela p
        JOIN fato_contrato c ON p.contrato_id = c.contrato_id
        JOIN dim_pa pa ON c.pa_id = pa.pa_id
        WHERE p.data_pagamento IS NULL
        GROUP BY pa.nome_pa
        ORDER BY saldo_90 DESC
    """)
    for nome, saldo_90, saldo_total in cur.fetchall():
        pct = saldo_90 / saldo_total if saldo_total else 0
        print(f"{nome:<16} saldo_90+={saldo_90:>14,.2f}  %_sobre_saldo_aberto={pct:.1%}")


def padrao_3_curva_antiga_vs_nova(cur):
    linha("PADRAO 3: inadimplencia 90+ ao longo do tempo (CURVA ANTIGA vs CURVA NOVA)")

    print("--- Metodo ANTIGO (por coorte de mes de vencimento, sofre right-censoring) ---")
    print("""
    SQL:
    SELECT strftime('%Y-%m', data_vencimento) as mes,
           SUM(CASE WHEN data_pagamento IS NULL
                     AND julianday('2026-09-30') - julianday(data_vencimento) > 90
                THEN valor_parcela ELSE 0 END) / SUM(valor_parcela)
    FROM fato_parcela
    WHERE data_vencimento BETWEEN '2025-10-01' AND '2026-09-30'
    GROUP BY mes
    """)
    cur.execute("""
        SELECT strftime('%Y-%m', data_vencimento) as mes,
               SUM(CASE WHEN data_pagamento IS NULL
                         AND julianday('2026-09-30') - julianday(data_vencimento) > 90
                    THEN valor_parcela ELSE 0 END) as saldo_90,
               SUM(valor_parcela) as saldo_mes
        FROM fato_parcela
        WHERE data_vencimento BETWEEN '2025-10-01' AND '2026-09-30'
        GROUP BY mes
        ORDER BY mes
    """)
    curva_antiga = {}
    for mes, saldo_90, saldo_mes in cur.fetchall():
        pct = saldo_90 / saldo_mes if saldo_mes else 0
        curva_antiga[mes] = pct

    print()
    print("--- Metodo NOVO (ponto no tempo: numerador e denominador reavaliados a cada fim de mes) ---")
    print("""
    SQL (repetido para cada fim de mes M):
    SELECT
        SUM(CASE WHEN data_vencimento <= date(M, '-90 days')
                  AND (data_pagamento IS NULL OR data_pagamento > M)
             THEN valor_parcela ELSE 0 END) as saldo_90_em_M,
        SUM(CASE WHEN (data_pagamento IS NULL OR data_pagamento > M)
             THEN valor_parcela ELSE 0 END) as saldo_carteira_em_M
    FROM fato_parcela
    -- saldo_carteira_em_M = TODAS as parcelas ainda nao pagas em M, inclusive
    -- as que vencem depois de M (saldo devedor total, nao so o que ja venceu)
    """)
    curva_nova = {}
    for m in MESES_CURVA:
        cur.execute("""
            SELECT
                SUM(CASE WHEN data_vencimento <= date(?, '-90 days')
                          AND (data_pagamento IS NULL OR data_pagamento > ?)
                     THEN valor_parcela ELSE 0 END),
                SUM(CASE WHEN (data_pagamento IS NULL OR data_pagamento > ?)
                     THEN valor_parcela ELSE 0 END)
            FROM fato_parcela
        """, (m, m, m))
        num, den = cur.fetchone()
        num = num or 0
        den = den or 1
        curva_nova[m[:7]] = num / den

    print()
    print(f"{'mes':<10}{'curva_antiga_(coorte)':>24}{'curva_nova_(ponto_no_tempo)':>30}")
    for m in MESES_CURVA:
        mes_curto = m[:7]
        antiga = curva_antiga.get(mes_curto)
        nova = curva_nova.get(mes_curto)
        antiga_str = f"{antiga:.1%}" if antiga is not None else "n/d"
        nova_str = f"{nova:.1%}" if nova is not None else "n/d"
        print(f"{mes_curto:<10}{antiga_str:>24}{nova_str:>30}")

    print()
    print("Leitura: a curva antiga despenca para quase 0% nos ultimos meses porque")
    print("uma parcela so pode ser 90+ depois de 90 dias vencida, e parcelas vencidas")
    print("em jul/ago/set de 2026 ainda nao completaram 90 dias ate a data de corte.")
    print("A curva nova nao sofre isso porque o numerador olha para tras a partir de")
    print("cada mes, nao para a frente a partir do vencimento da parcela.")


def padrao_4_sazonalidade(cur):
    linha("PADRAO 4: concessao de contratos com pico em nov/dez")
    cur.execute("""
        SELECT strftime('%m', data_contratacao) as mes, COUNT(*)
        FROM fato_contrato
        GROUP BY mes
        ORDER BY mes
    """)
    for mes, total in cur.fetchall():
        print(f"mes {mes}: {total} contratos")


def padrao_5_concentracao_top10(cur):
    linha("PADRAO 5: concentracao de saldo nos 10 maiores cooperados")
    cur.execute("""
        SELECT fc.cooperado_id, SUM(fc.valor_parcela) as exposicao
        FROM fato_contrato fc
        GROUP BY fc.cooperado_id
        ORDER BY exposicao DESC
        LIMIT 10
    """)
    top10 = cur.fetchall()
    for cooperado_id, exposicao in top10:
        print(f"cooperado_id={cooperado_id}: {exposicao:,.2f}")
    total = cur.execute("SELECT SUM(valor_parcela) FROM fato_contrato").fetchone()[0]
    soma_top10 = sum(r[1] for r in top10)
    print(f"top10 / total = {soma_top10/total:.1%}")


def padrao_6_pj_menos_inadimplente(cur):
    linha("PADRAO 6 (novo): PJ tem inadimplencia 90+ menor que PF")
    cur.execute("""
        SELECT dc.tipo_pessoa_real,
               SUM(CASE WHEN p.data_pagamento IS NULL
                         AND julianday('2026-09-30') - julianday(p.data_vencimento) > 90
                    THEN p.valor_parcela ELSE 0 END) as saldo_90,
               SUM(p.valor_parcela) as saldo_aberto
        FROM fato_parcela p
        JOIN fato_contrato c ON p.contrato_id = c.contrato_id
        JOIN (SELECT cooperado_id,
                     CASE WHEN documento LIKE '%/%' OR length(replace(replace(replace(replace(trim(documento),'.',''),'-',''),'/',''),' ','')) = 14
                          THEN 'PJ' ELSE 'PF' END as tipo_pessoa_real
              FROM dim_cooperado) dc ON c.cooperado_id = dc.cooperado_id
        WHERE p.data_pagamento IS NULL
        GROUP BY dc.tipo_pessoa_real
    """)
    for tipo, saldo_90, saldo_aberto in cur.fetchall():
        pct = saldo_90 / saldo_aberto if saldo_aberto else 0
        print(f"{tipo}: {pct:.1%}  (saldo_90+={saldo_90:,.2f}  saldo_aberto={saldo_aberto:,.2f})")
    print("Nota: tipo real inferido pelo tamanho do documento (11 digitos = CPF/PF,")
    print("14 digitos = CNPJ/PJ), nao pela coluna tipo_pessoa (que esta suja de proposito).")


def padrao_7_garantia(cur):
    linha("PADRAO 7 (novo): contrato sem garantia atrasa mais que com garantia")
    cur.execute("""
        SELECT
            CASE WHEN lower(trim(c.garantia)) LIKE 'com%' THEN 'Com garantia' ELSE 'Sem garantia' END as garantia_padronizada,
            SUM(CASE WHEN p.data_pagamento IS NULL
                      AND julianday('2026-09-30') - julianday(p.data_vencimento) > 90
                 THEN p.valor_parcela ELSE 0 END) as saldo_90,
            SUM(p.valor_parcela) as saldo_aberto
        FROM fato_parcela p
        JOIN fato_contrato c ON p.contrato_id = c.contrato_id
        WHERE p.data_pagamento IS NULL
        GROUP BY garantia_padronizada
    """)
    for garantia, saldo_90, saldo_aberto in cur.fetchall():
        pct = saldo_90 / saldo_aberto if saldo_aberto else 0
        print(f"{garantia}: {pct:.1%}  (saldo_90+={saldo_90:,.2f}  saldo_aberto={saldo_aberto:,.2f})")


def padrao_8_score_risco(cur):
    linha("PADRAO 8 (novo): nivel_risco D/E concentram atraso")
    cur.execute("""
        SELECT c.nivel_risco,
               SUM(CASE WHEN p.data_pagamento IS NULL
                         AND julianday('2026-09-30') - julianday(p.data_vencimento) > 90
                    THEN p.valor_parcela ELSE 0 END) as saldo_90,
               SUM(p.valor_parcela) as saldo_aberto
        FROM fato_parcela p
        JOIN fato_contrato c ON p.contrato_id = c.contrato_id
        WHERE p.data_pagamento IS NULL AND c.nivel_risco IS NOT NULL
        GROUP BY c.nivel_risco
        ORDER BY c.nivel_risco
    """)
    for nivel, saldo_90, saldo_aberto in cur.fetchall():
        pct = saldo_90 / saldo_aberto if saldo_aberto else 0
        print(f"nivel {nivel}: {pct:.1%}  (saldo_90+={saldo_90:,.2f}  saldo_aberto={saldo_aberto:,.2f})")


def padrao_9_metas_por_pa(cur):
    linha("PADRAO 9 (novo): um PA bate a meta com folga, outro fica sistematicamente abaixo")

    print("--- Saldo (estoque): meta do ultimo mes (set/2026) vs saldo real no corte ---")
    cur.execute("""
        SELECT pa.nome_pa,
               m.meta_saldo,
               (SELECT SUM(fp.valor_parcela)
                FROM fato_parcela fp
                JOIN fato_contrato fc ON fp.contrato_id = fc.contrato_id
                WHERE fc.pa_id = pa.pa_id AND fp.data_pagamento IS NULL) as saldo_realizado
        FROM meta_mensal m
        JOIN dim_pa pa ON m.pa_id = pa.pa_id
        WHERE m.mes = '2026-09-01'
        ORDER BY pa.nome_pa
    """)
    for nome, meta_saldo, saldo_realizado in cur.fetchall():
        saldo_realizado = saldo_realizado or 0
        atingimento = saldo_realizado / meta_saldo if meta_saldo else 0
        print(f"{nome:<16} meta_saldo_set2026={meta_saldo:>14,.2f}  saldo_realizado_corte={saldo_realizado:>14,.2f}  atingimento={atingimento:.1%}")

    print()
    print("--- Volume concedido (fluxo): soma de 36 meses de meta vs soma de 36 meses realizado ---")
    cur.execute("""
        SELECT pa.nome_pa,
               SUM(m.meta_volume_concedido) as meta_volume_total,
               (SELECT SUM(fc.valor_parcela * fc.prazo_meses)
                FROM fato_contrato fc
                WHERE fc.pa_id = pa.pa_id) as volume_realizado
        FROM meta_mensal m
        JOIN dim_pa pa ON m.pa_id = pa.pa_id
        GROUP BY pa.nome_pa
        ORDER BY pa.nome_pa
    """)
    for nome, meta_volume_total, volume_realizado in cur.fetchall():
        volume_realizado = volume_realizado or 0
        atingimento = volume_realizado / meta_volume_total if meta_volume_total else 0
        print(f"{nome:<16} meta_volume_total={meta_volume_total:>14,.2f}  volume_realizado={volume_realizado:>14,.2f}  atingimento={atingimento:.1%}")


def tamanho_dos_arquivos():
    linha("TAMANHO DOS ARQUIVOS (controle de peso no repositorio)")
    tamanho_db = os.path.getsize(DB_PATH) / (1024 * 1024)
    tamanho_sql = os.path.getsize(SQL_PATH) / (1024 * 1024)
    print(f"{DB_PATH.name}: {tamanho_db:.2f} MB")
    print(f"{SQL_PATH.name}: {tamanho_sql:.2f} MB")


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    contagens_por_tabela(cur)
    qualidade_de_dados(cur)
    padrao_1_produto_risco(cur)
    padrao_2_pa_concentrado(cur)
    padrao_3_curva_antiga_vs_nova(cur)
    padrao_4_sazonalidade(cur)
    padrao_5_concentracao_top10(cur)
    padrao_6_pj_menos_inadimplente(cur)
    padrao_7_garantia(cur)
    padrao_8_score_risco(cur)
    padrao_9_metas_por_pa(cur)
    tamanho_dos_arquivos()

    conn.close()


if __name__ == "__main__":
    main()
