"""
===============================================================================
LH NAUTICAL - 

Questão: 6 Modelo baseline simples


Priscila Castaldo
===============================================================================
"""


import pandas as pd
import numpy as np
import psycopg2
import logging

# Configuração de Logs
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Configuração de Conexão com o PostgreSQL
DB_CONFIG = {
    "host": "localhost",
    "port": "5432",
    "dbname": "lh_nautical",
    "user": "postgres",
    "password": "senac",  
    "client_encoding": "utf8"
}

PRODUTO_ALVO = "Bússola de Bordo 702"

def carregar_serie_temporal():
    """1. Extrai a série temporal unificada diretamente do PostgreSQL."""
    query = f"""
        SELECT 
            DATE_TRUNC('month', o.placed_at)::date AS mes,
            SUM(oi.quantity) AS quantidade_vendida
        FROM orders o
        JOIN order_items oi ON o.id = oi.order_id
        JOIN product_variants pv ON oi.product_variant_id = pv.id
        JOIN products p ON pv.product_id = p.id
        WHERE p.name ILIKE '%{PRODUTO_ALVO}%'
        AND o.status NOT IN ('cancelled', 'draft')
        GROUP BY DATE_TRUNC('month', o.placed_at)::date
        ORDER BY mes ASC;
    """
    
    conn = psycopg2.connect(**DB_CONFIG)
    df = pd.read_sql(query, conn)
    conn.close()
    
    # Garantir que a coluna 'mes' seja do tipo datetime
    df['mes'] = pd.to_datetime(df['mes'])
    return df

def executar_previsao_baseline():
    logging.info(f"Extração de dados para: '{PRODUTO_ALVO}'...")
    df = carregar_serie_temporal()
    
    if df.empty:
        logging.error("Nenhum dado encontrado para o produto especificado!")
        return

    # Garantir frequência mensal contínua (preenchendo meses sem vendas com 0)
    full_range = pd.date_range(start=df['mes'].min(), end='2026-03-01', freq='MS')
    df = df.set_index('mes').reindex(full_range, fill_value=0).reset_index()
    df.rename(columns={'index': 'mes'}, inplace=True)

    # 2. Construção do Modelo Baseline: Média Móvel dos últimos 3 meses (MA_3)
    # Importante: usa shift(1) para não vazar dados do próprio mês
    df['previsao_ma3'] = df['quantidade_vendida'].shift(1).rolling(window=3).mean()

    # Divisão de Treino e Teste
    df_treino = df[df['mes'] <= '2025-12-31']
    df_teste = df[(df['mes'] >= '2026-01-01') & (df['mes'] <= '2026-03-01')].copy()

    # 3. Previsão para o 1º Trimestre de 2026
    print("\n" + "=" * 65)
    print(f"PREVISÃO BASELINE (MÉDIA MÓVEL 3 MESES) - {PRODUTO_ALVO}")
    print("=" * 50)
    
    for idx, row in df_teste.iterrows():
        mes_str = row['mes'].strftime('%m/%Y')
        real = int(row['quantidade_vendida'])
        pred = round(row['previsao_ma3'], 2)
        print(f"  • Mês {mes_str} | Venda Real: {real:3d} unid. | Previsão (MA3): {pred:6.2f} unid.")

    # 4. Avaliação do Modelo (Métrica MAE - Mean Absolute Error)
    df_teste['erro_absoluto'] = np.abs(df_teste['quantidade_vendida'] - df_teste['previsao_ma3'])
    mae = df_teste['erro_absoluto'].mean()

    print("-" * 50)
    print(f"MÉTRICA MAE (Mean Absolute Error) NO TESTE (Q1 2026): {mae:.2f}")
    print("=" * 50 + "\n")

    soma_prevista_q1 = df_teste['previsao_ma3'].sum()
    print(f"RESPOSTA QUESTAO 6.1 (Soma Arredondada Q1 2026): {round(soma_prevista_q1)}")

    import pandas as pd
import numpy as np
import psycopg2
import logging

# Configuração de Logs
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Configuração de Conexão com o PostgreSQL
DB_CONFIG = {
    "host": "localhost",
    "port": "5432",
    "dbname": "lh_nautical",
    "user": "postgres",
    "password": "senac",  
    "client_encoding": "utf8"
}

PRODUTO_ALVO = "Bússola de Bordo 702"

def carregar_serie_temporal():
    """1. Extrai a série temporal unificada diretamente do PostgreSQL."""
    query = f"""
        SELECT 
            DATE_TRUNC('month', o.placed_at)::date AS mes,
            SUM(oi.quantity) AS quantidade_vendida
        FROM orders o
        JOIN order_items oi ON o.id = oi.order_id
        JOIN product_variants pv ON oi.product_variant_id = pv.id
        JOIN products p ON pv.product_id = p.id
        WHERE p.name ILIKE '%{PRODUTO_ALVO}%'
        AND o.status NOT IN ('cancelled', 'draft')
        GROUP BY DATE_TRUNC('month', o.placed_at)::date
        ORDER BY mes ASC;
    """
    
    conn = psycopg2.connect(**DB_CONFIG)
    df = pd.read_sql(query, conn)
    conn.close()
    
    # Garantir que a coluna 'mes' seja do tipo datetime
    df['mes'] = pd.to_datetime(df['mes'])
    return df

def executar_previsao_baseline():
    logging.info(f"Iniciando extração de dados para: '{PRODUTO_ALVO}'...")
    df = carregar_serie_temporal()
    
    if df.empty:
        logging.error("Nenhum dado encontrado para o produto especificado!")
        return

    # Garantir frequência mensal contínua (preenchendo meses sem vendas com 0)
    full_range = pd.date_range(start=df['mes'].min(), end='2026-03-01', freq='MS')
    df = df.set_index('mes').reindex(full_range, fill_value=0).reset_index()
    df.rename(columns={'index': 'mes'}, inplace=True)

    # 2. Construção do Modelo Baseline: Média Móvel dos últimos 3 meses (MA_3)
    # Importante: usa shift(1) para não vazar dados do próprio mês
    df['previsao_ma3'] = df['quantidade_vendida'].shift(1).rolling(window=3).mean()

    # Divisão de Treino e Teste
    df_treino = df[df['mes'] <= '2025-12-31']
    df_teste = df[(df['mes'] >= '2026-01-01') & (df['mes'] <= '2026-03-01')].copy()

    # 3. Previsão para o 1º Trimestre de 2026
    print("\n" + "=" * 65)
    print(f"PREVISÃO BASELINE (MÉDIA MÓVEL 3 MESES) - {PRODUTO_ALVO}")
    print("=" * 65)
    
    for idx, row in df_teste.iterrows():
        mes_str = row['mes'].strftime('%m/%Y')
        real = int(row['quantidade_vendida'])
        pred = round(row['previsao_ma3'], 2)
        print(f"  • Mês {mes_str} | Venda Real: {real:3d} unid. | Previsão (MA3): {pred:6.2f} unid.")

    # 4. Avaliação do Modelo (Métrica MAE - Mean Absolute Error)
    df_teste['erro_absoluto'] = np.abs(df_teste['quantidade_vendida'] - df_teste['previsao_ma3'])
    mae = df_teste['erro_absoluto'].mean()

    print("-" * 65)
    print(f"MÉTRICA MAE (Mean Absolute Error) NO TESTE (Q1 2026): {mae:.2f}")
    print("=" * 65 + "\n")

    soma_prevista_q1 = df_teste['previsao_ma3'].sum()
    print(f"RESPOSTA QUESTAO 6.1 (Soma Arredondada Q1 2026): {round(soma_prevista_q1)}")

    # =========================================================================
    # 5. EXPORTAÇÃO APENAS DO PERÍODO DE TESTE (Q1/2026) PARA O LOOKER STUDIO
    # =========================================================================
    # Filtra apenas o subset do teste (01/2026 a 03/2026)
    df_export = df_teste.copy()

    # Formata a data no padrão YYYY-MM-DD
    df_export["data"] = df_export["mes"].dt.strftime("%Y-%m-%d")

    # Arredonda os valores numéricos
    df_export["previsao_ma3"] = df_export["previsao_ma3"].round(2)
    df_export["erro_absoluto"] = df_export["erro_absoluto"].round(2)

    # Seleciona e renomeia apenas as colunas desejadas para a entrega
    colunas_finais = {
        "data": "data",
        "quantidade_vendida": "vendas_reais",
        "previsao_ma3": "previsao_ma3",
        "erro_absoluto": "erro_absoluto",
    }

    df_export = df_export[list(colunas_finais.keys())].rename(
        columns=colunas_finais
    )

    # Salva o arquivo CSV apenas com o período Q1/2026
    
    df_export.to_csv("previsao_demanda_csv", index=False, encoding="utf-8")
    logging.info(
        f"🎉 Arquivo '{"previsao_demanda_csv"}' exportado apenas com o Q1/2026 ({len(df_export)} linhas)!"
    )

if __name__ == "__main__":
    executar_previsao_baseline()