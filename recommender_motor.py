"""
===============================================================================
LH NAUTICAL - PIPELINE DE ENGENHARIA E CIÊNCIA DE DADOS
Questão: 7 Sistema de Recomendação (Similaridade de Cosseno)

Descrição:
    Gera recomendações de produtos baseadas no histórico de compras dos clientes,
    utilizando a técnica de Filtragem Colaborativa Baseada em Itens.

Autora: Priscila Castaldo
Gemini 3.5
===============================================================================
"""

import os
import logging
import numpy as np
import pandas as pd
import psycopg2
from dotenv import load_dotenv
from sklearn.metrics.pairwise import cosine_similarity

# -----------------------------------------------------------------------------
# 1. CONFIGURAÇÃO DE LOGS E VARIÁVEIS DE AMBIENTE (SEGURANÇA)
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# Carrega as variáveis do arquivo .env (Removemos o DB_CONFIG hardcoded)
load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

if not all([DB_NAME, DB_USER, DB_PASSWORD]):
    raise ValueError("ERRO CRÍTICO: Credenciais do banco não encontradas no .env.")

PRODUTO_ALVO = "Motor de Popa 1949"

# -----------------------------------------------------------------------------
# 2. PADRONIZAÇÃO DA CONEXÃO
# -----------------------------------------------------------------------------
def conectar_banco():
    """Estabelece a conexão com o PostgreSQL forçando a codificação UTF-8."""
    try:
        return psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            client_encoding='UTF8'
        )
    except Exception as error:
        logging.error(f"Falha de conexão com o banco: {error}")
        raise error

# -----------------------------------------------------------------------------
# 3. EXTRAÇÃO DE DADOS (DATA ENGINEERING)
# -----------------------------------------------------------------------------
def carregar_interacoes():
    """Carrega o histórico de compras (Cliente x Produto) ignorando cancelamentos."""
    query = """
        SELECT DISTINCT
            o.customer_id,
            p.id AS product_id,
            p.name AS product_name,
            COALESCE(p.description, 'Sem descrição') AS description
        FROM orders o
        JOIN order_items oi ON o.id = oi.order_id
        JOIN product_variants pv ON oi.product_variant_id = pv.id
        JOIN products p ON pv.product_id = p.id
        WHERE o.status NOT IN ('cancelled', 'draft');
    """
    
    # Utiliza a função padronizada de conexão
    conn = conectar_banco()
    df = pd.read_sql(query, conn)
    conn.close()
    
    return df

# -----------------------------------------------------------------------------
# 4. SISTEMA DE RECOMENDAÇÃO (MACHINE LEARNING)
# -----------------------------------------------------------------------------
def executar_sistema_recomendacao():
    logging.info("Carregando interações de clientes e produtos...")
    df_interacoes = carregar_interacoes()

    if df_interacoes.empty:
        logging.error("Nenhuma interação encontrada! Verifique o banco de dados.")
        return

    # Passo A: Construção da Matriz Binária (One-Hot) de Interação
    logging.info("Construindo a Matriz Binária de Interação (Usuário x Produto)...")
    matriz_usuario_produto = pd.crosstab(
        index=df_interacoes["customer_id"],
        columns=df_interacoes["product_name"]
    ).map(lambda x: 1 if x > 0 else 0)

    # Validação de integridade: O produto alvo existe nas vendas?
    if PRODUTO_ALVO not in matriz_usuario_produto.columns:
        logging.error(f"O produto '{PRODUTO_ALVO}' não possui histórico de vendas!")
        return

    # Passo B: Transposição e Cálculo da Similaridade de Cosseno
    # Transpomos (T) para que a similaridade seja calculada entre os PRODUTOS (linhas)
    matriz_produto_usuario = matriz_usuario_produto.T
    
    logging.info("Calculando Similaridade de Cosseno entre Produtos...")
    matriz_similaridade = cosine_similarity(matriz_produto_usuario)

    df_similaridade = pd.DataFrame(
        matriz_similaridade,
        index=matriz_produto_usuario.index,
        columns=matriz_produto_usuario.index,
    )

    # Passo C: Extração e Ranking do Top 5
    top_5_recomendacoes = (
        df_similaridade[PRODUTO_ALVO]
        .drop(index=PRODUTO_ALVO) # Remove o próprio produto da lista de recomendação
        .sort_values(ascending=False)
        .head(5)
    )

    # Mapeamento auxiliar para resgatar IDs e Descrições para a apresentação
    info_produtos = (
        df_interacoes[["product_name", "product_id", "description"]]
        .drop_duplicates(subset=["product_name"])
        .set_index("product_name")
    )

    # Passo D: Exibição Executiva no Terminal
    print("\n" + "=" * 70)
    print(f"VITRINE: 'QUEM COMPROU ISSO, TAMBÉM LEVOU...'")
    print(f"ITEM DE REFERÊNCIA: {PRODUTO_ALVO}")
    print("=" * 70)

    for i, (prod_nome, sim_score) in enumerate(top_5_recomendacoes.items(), 1):
        p_id = info_produtos.loc[prod_nome, "product_id"]
        p_desc = info_produtos.loc[prod_nome, "description"]
        print(f"  {i}º Lugar | ID: {p_id:4d} | Similaridade: {sim_score:.4f} | Produto: {prod_nome}")

    print("=" * 70 + "\n")

    # -------------------------------------------------------------------------
    # 5. EXPORTAÇÃO PARA O DASHBOARD (POWER BI / LOOKER)
    # -------------------------------------------------------------------------
    df_export = pd.DataFrame({
        "posicao": range(1, len(top_5_recomendacoes) + 1),
        "produto_referencia": PRODUTO_ALVO,
        "product_id": [info_produtos.loc[p, "product_id"] for p in top_5_recomendacoes.index],
        "produto_recomendado": top_5_recomendacoes.index,
        "description": [info_produtos.loc[p, "description"] for p in top_5_recomendacoes.index],
        "score_similaridade": top_5_recomendacoes.values.round(4),
    })
    
    nome_arquivo = "recomendacao.csv"
    df_export.to_csv(nome_arquivo, index=False, encoding="utf-8")
    logging.info(f"🎉 Arquivo '{nome_arquivo}' exportado com sucesso ({len(df_export)} recomendações)!")

if __name__ == "__main__":
    executar_sistema_recomendacao()