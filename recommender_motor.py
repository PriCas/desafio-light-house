"""
===============================================================================
LH NAUTICAL - 

Questão: 7 Sistema de recomendação


Autor: Priscila Castaldo
===============================================================================
"""
import logging
import numpy as np
import pandas as pd
import psycopg2
from sklearn.metrics.pairwise import cosine_similarity

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)

# Configuração do PostgreSQL
DB_CONFIG = {
    "host": "localhost",
    "port": "5432",
    "dbname": "lh_nautical",
    "user": "postgres",
    "password": "senac",
    "client_encoding": "utf8",
}

PRODUTO_ALVO = "Motor de Popa 1949"


def carregar_interacoes():
    """Carrega o histórico de compras únicas (Cliente x Produto)."""
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
    conn = psycopg2.connect(**DB_CONFIG)
    df = pd.read_sql(query, conn)
    conn.close()
    return df


def executar_sistema_recomendacao():
    logging.info("Carregando interações de clientes e produtos...")
    df_interacoes = carregar_interacoes()

    if df_interacoes.empty:
        logging.error("Nenhuma interação encontrada!")
        return

    # 1. Construção da Matriz Usuário x Produto (Linhas: Cliente, Colunas: Produto)
    # Valor 1 se comprou ao menos uma vez, 0 caso contrário
    logging.info(
        "Construindo a Matriz Binária de Interação (Usuário x Produto)..."
    )
    matriz_usuario_produto = pd.crosstab(
        index=df_interacoes["customer_id"],
        columns=df_interacoes["product_name"],
    ).map(lambda x: 1 if x > 0 else 0)

    # Verificar se o produto alvo existe no catálogo
    if PRODUTO_ALVO not in matriz_usuario_produto.columns:
        logging.error(
            f"O produto '{PRODUTO_ALVO}' não foi encontrado no catálogo!"
        )
        return

    # 2. Cálculo da Similaridade de Cosseno entre os Vetores dos Produtos
    # Transpomos a matriz para ter Produtos nas linhas e Clientes nas colunas
    matriz_produto_usuario = matriz_usuario_produto.T

    logging.info("Calculando Similaridade de Cosseno entre Produtos...")
    matriz_similaridade = cosine_similarity(matriz_produto_usuario)

    # Transformar em DataFrame para facilitar busca
    df_similaridade = pd.DataFrame(
        matriz_similaridade,
        index=matriz_produto_usuario.index,
        columns=matriz_produto_usuario.index,
    )

    # 3. Ranking dos 5 produtos mais similares ao 'Motor de Popa 1949'
    # Puxa a coluna do produto alvo, remove ele mesmo do ranking e pega os Top 5
    top_5_recomendacoes = (
        df_similaridade[PRODUTO_ALVO]
        .drop(index=PRODUTO_ALVO)
        .sort_values(ascending=False)
        .head(5)
    )

    # Mapeamento auxiliar para resgatar ID e Descrição de cada produto
    info_produtos = (
        df_interacoes[["product_name", "product_id", "description"]]
        .drop_duplicates(subset=["product_name"])
        .set_index("product_name")
    )

    # Exibição do Resultado Executivo
    print("\n" + "=" * 70)
    print(
        f"SISTEMA DE RECOMENDAÇÃO: VITRINE 'QUEM COMPROU ISSO, TAMBÉM LEVOU...'"
    )
    print(f"ITEM DE REFERÊNCIA: {PRODUTO_ALVO}")
    print("=" * 70)

    for i, (prod_nome, sim_score) in enumerate(
        top_5_recomendacoes.items(), 1
    ):
        p_id = info_produtos.loc[prod_nome, "product_id"]
        p_desc = info_produtos.loc[prod_nome, "description"]
        print(
            f"  {i}º Lugar | ID: {p_id:4d} | Similaridade: {sim_score:.4f} | Produto: {prod_nome} | Descrição: {p_desc}"
        )

    print("=" * 70 + "\n")

    # =========================================================================
    # 4. PREPARAÇÃO E EXPORTAÇÃO DO CSV PARA O LOOKER STUDIO
    # =========================================================================
    df_export = pd.DataFrame(
        {
            "posicao": range(1, len(top_5_recomendacoes) + 1),
            "produto_referencia": PRODUTO_ALVO,
            "product_id": [
                info_produtos.loc[p, "product_id"]
                for p in top_5_recomendacoes.index
            ],
            "produto_recomendado": top_5_recomendacoes.index,
            "description": [
                info_produtos.loc[p, "description"]
                for p in top_5_recomendacoes.index
            ],
            "score_similaridade": top_5_recomendacoes.values.round(4),
        }
    )
    
    # Salva o arquivo CSV
    df_export.to_csv("recomendacao.csv", index=False, encoding="utf-8")
    logging.info(
        f"🎉 Arquivo 'recomendacao.csv' exportado com sucesso com {len(df_export)} recomendações!"
    )


if __name__ == "__main__":
    executar_sistema_recomendacao()