"""
===============================================================================
LH NAUTICAL - DESAFIO LIGHTHOUSE
Questão 6: Modelo Baseline Preditivo de Demanda (Bússola de Bordo 702)
Priscila Castaldo
===============================================================================
"""

import os
import logging
import pandas as pd
import numpy as np
import psycopg2
from dotenv import load_dotenv

# -----------------------------------------------------------------------------
# 1. CONFIGURAÇÃO DE LOGS E AMBIENTE (REPOSITÓRIO SEGURO)
# -----------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Carrega as variáveis de ambiente contidas no arquivo local .env (Isolamento de Credenciais)
load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

# Validação Preventiva de Segurança antes da execução do pipeline
if not all([DB_NAME, DB_USER, DB_PASSWORD]):
    raise ValueError(
        "ERRO CRÍTICO DE CONFIGURAÇÃO: Variáveis de ambiente do PostgreSQL não foram encontradas. "
        "Verifique se o seu arquivo .env existe e possui as chaves DB_NAME, DB_USER e DB_PASSWORD."
    )

PRODUTO_ALVO = "Bússola de Bordo 702"
# -----------------------------------------------------------------------------
# 2. CONEXÃO AO BANCO DE DADOS SUPORTE A UNICODE / UTF-8)
# -----------------------------------------------------------------------------
def conectar_banco():
    """
    Estabelece e retorna um objeto de conexão ativo com o PostgreSQL,
    garantindo que senhas com caracteres especiais/acentos sejam codificadas em UTF-8.
    """
    try:
        # Garantindo que os parâmetros sejam strings tratadas
        connection = psycopg2.connect(
            host=str(DB_HOST),
            port=str(DB_PORT),
            database=str(DB_NAME),
            user=str(DB_USER),
            password=str(DB_PASSWORD),
            client_encoding='UTF8'  # <--- FORÇA O CLIENTE POSTGRES A TRABALHAR EM UTF-8
        )
        return connection
    except Exception as error:
        logging.error(f"Falha na conexão com o PostgreSQL: {error}")
        raise error



# -----------------------------------------------------------------------------
# 3. EXTRAÇÃO E ENGENHARIA DA SÉRIE TEMPORAL
# -----------------------------------------------------------------------------
def carregar_serie_temporal():
    """
    Consulta o PostgreSQL e extrai a série de vendas unificada da Bússola de Bordo 702.
    Descarte preventivo de registros não efetivados ('cancelled', 'draft').
    """
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
    
    # Invocação direta da função de conexão reescrita
    conn = conectar_banco()
    df = pd.read_sql(query, conn)
    conn.close()
    
    # Garantia de tipo datetime para manipulação contínua da série
    df['mes'] = pd.to_datetime(df['mes'])
    return df

# -----------------------------------------------------------------------------
# 4. EXECUÇÃO DO FORECASTING E AVALIAÇÃO DO MODELO
# -----------------------------------------------------------------------------
def executar_previsao_baseline():
    logging.info(f"Iniciando pipeline de extração e forecasting para: '{PRODUTO_ALVO}'...")
    df = carregar_serie_temporal()
    
    if df.empty:
        logging.error("Nenhum registro de vendas localizado para o produto alvo!")
        return

    # Garante a continuidade mensal preenchendo eventuais meses sem venda com valor 0
    full_range = pd.date_range(start=df['mes'].min(), end='2026-03-01', freq='MS')
    df = df.set_index('mes').reindex(full_range, fill_value=0).reset_index()
    df.rename(columns={'index': 'mes'}, inplace=True)

    # Modelo Baseline: Média Móvel de 3 meses (MA_3)
    # USO OBRIGATÓRIO DE .shift(1): Evita Data Leakage (vazamento do próprio mês t)
    df['previsao_ma3'] = df['quantidade_vendida'].shift(1).rolling(window=3).mean()

    # Separação Estrita entre Períodos de Treino e Teste (Premissas Obrigatórias)
    df_teste = df[(df['mes'] >= '2026-01-01') & (df['mes'] <= '2026-03-01')].copy()

    # Apresentação Limpa do Resultado no Terminal
    print("\n" + "=" * 65)
    print(f"PREVISÃO BASELINE (MÉDIA MÓVEL 3 MESES) - {PRODUTO_ALVO}")
    print("=" * 65)
    
    for idx, row in df_teste.iterrows():
        mes_str = row['mes'].strftime('%m/%Y')
        real = int(row['quantidade_vendida'])
        pred = round(row['previsao_ma3'], 2) if pd.notnull(row['previsao_ma3']) else 0.0
        print(f"  • Mês {mes_str} | Venda Real: {real:3d} unid. | Previsão (MA3): {pred:6.2f} unid.")

    # Cálculo da Métrica de Avaliação: Erro Médio Absoluto (MAE)
    df_teste['erro_absoluto'] = np.abs(df_teste['quantidade_vendida'] - df_teste['previsao_ma3'])
    mae = df_teste['erro_absoluto'].mean()

    print("-" * 65)
    print(f"MÉTRICA MAE (Mean Absolute Error) NO TESTE (Q1 2026): {mae:.2f}")
    print("=" * 65 + "\n")

    soma_prevista_q1 = df_teste['previsao_ma3'].sum()
    print(f"RESPOSTA QUESTAO 6.1 (Soma Arredondada Q1 2026): {round(soma_prevista_q1)}")

    # Exportação do Dataset de Entrega para o Dashboard (Looker Studio / Power BI)
    df_export = df_teste.copy()
    df_export["data"] = df_export["mes"].dt.strftime("%Y-%m-%d")
    df_export["previsao_ma3"] = df_export["previsao_ma3"].round(2)
    df_export["erro_absoluto"] = df_export["erro_absoluto"].round(2)

    colunas_finais = {
        "data": "data",
        "quantidade_vendida": "vendas_reais",
        "previsao_ma3": "previsao_ma3",
        "erro_absoluto": "erro_absoluto",
    }

    df_export = df_export[list(colunas_finais.keys())].rename(columns=colunas_finais)

    nome_arquivo = "previsao_demanda.csv"
    df_export.to_csv(nome_arquivo, index=False, encoding="utf-8")
    logging.info(f"🎉 Arquivo '{nome_arquivo}' exportado com sucesso para o Q1/2026 ({len(df_export)} linhas)!")

# -----------------------------------------------------------------------------
# 5. PONTO DE ENTRADA DO SCRIPT
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    executar_previsao_baseline()