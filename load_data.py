"""
===============================================================================
LH NAUTICAL - PIPELINE DE ENGENHARIA DE DADOS
Módulo: Carga de Dados Brutos no Banco PostgreSQL (Ingestion)
Questão: 3.1 (Carregamento automatizado de arquivos CSV na Camada Raw/Bronze)

Descrição:
    Este script conecta ao PostgreSQL e executa o carregamento em massa (bulk)
    de todos os 24 arquivos CSV contidos no diretório 'lh_nautical_csv/'.

Premissas & Restrições:
    - Zero tratamento de dados: Mantém nulos, formatos originais e caracteres.
    - Utilizacão do comando nativo 'COPY FROM' para maximizar o throughput.
    - Tratamento de exceções por tabela e log detalhado da operação.
    - Validação automática da contagem de linhas ao final do processo.

Autor: Priscila Castaldo
===============================================================================
"""
###revisar o cedilhas
import logging
import re
from pathlib import Path
from typing import Dict, List
import psycopg2

# =============================================================================
# CONFIGURAÇÃO DE LOGGING
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("ingestion.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# =============================================================================
# CONFIGURAÇÕES E CONSTANTES DE CONEXÃO
# =============================================================================
CSV_DIR = Path("lh_nautical_csv")

# Parametrize os dados da sua instância do PostgreSQL
DB_CONFIG: Dict[str, str] = {
    "host": "localhost",
    "port": "5432",
    "dbname": "lh_nautical",
    "user": "postgres",
    "password": "senac"  
}

# Lista de tabelas exigidas na validaCão final (Questão 3.2)
VALIDATION_TABLES: List[str] = ["customers", "orders", "order_items", "payments"]


# =============================================================================
# FUNÇÕES DE AUXÍLIO E CARGA DE DADOS
# =============================================================================

def sanitize_identifier(raw_name: str) -> str:
    """Garante que o nome da tabela no BD seja idêntico ao gerado no schema.sql."""
    clean_name = raw_name.strip().lower()
    clean_name = re.sub(r"[^a-z0-9_]", "_", clean_name)
    clean_name = re.sub(r"_+", "_", clean_name)
    return clean_name.strip("_")


def load_single_csv(cursor, csv_path: Path) -> int:
    """
    Carrega um arquivo CSV individual na sua respectiva tabela via COPY.

    Args:
        cursor: Cursor ativo da conexão psycopg2.
        csv_path (Path): Caminho para o arquivo CSV.

    Returns:
        int: Quantidade de linhas inseridas na tabela.
    """
    table_name = sanitize_identifier(csv_path.stem)

    # Limpa a tabela antes da carga para evitar duplicidade em re-execuções
    cursor.execute(f"TRUNCATE TABLE {table_name} CASCADE;")

    # Comando COPY nativo do PostgreSQL: leitor em massa de alto desempenho
    copy_sql = f"""
        COPY {table_name}
        FROM STDIN
        WITH (
            FORMAT csv,
            HEADER true,
            DELIMITER ',',
            QUOTE '"',
            ESCAPE '"',
            ENCODING 'UTF8'
        );
    """

    with csv_path.open(mode="r", encoding="utf-8-sig") as f:
        cursor.copy_expert(sql=copy_sql, file=f)

    # Obter total de linhas carregadas na tabela
    cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
    count = cursor.fetchone()[0]
    return count


def execute_data_ingestion() -> None:
    """Gerencia a conexão com o PostgreSQL e orquestra a carga de todos os CSVs."""
    if not CSV_DIR.exists() or not CSV_DIR.is_dir():
        logging.error(f"Diretório de entrada '{CSV_DIR}' não encontrado.")
        return

    csv_files = sorted(list(CSV_DIR.glob("*.csv")))
    if not csv_files:
        logging.warning(f"Nenhum arquivo .csv encontrado na pasta '{CSV_DIR}'.")
        return

    logging.info(f"Iniciando a carga bruta de {len(csv_files)} arquivos no PostgreSQL...")

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        # Ativa o modo autocommit para cada bloco isolado
        conn.autocommit = False
        cursor = conn.cursor()

        total_rows_loaded = 0

        for csv_file in csv_files:
            table_name = sanitize_identifier(csv_file.stem)
            try:
                rows_count = load_single_csv(cursor, csv_file)
                conn.commit()  # Confirma a gravação da tabela
                total_rows_loaded += rows_count
                logging.info(f"✅ Tabela '{table_name}' populada com sucesso: {rows_count:,} linhas.")
            except Exception as err:
                conn.rollback()  # Reverte falhas isoladas sem derrubar a conexão
                logging.error(f"❌ Falha ao carregar a tabela '{table_name}': {err}")

        # =====================================================================
        # VALIDAÇÃO FINAL DA QUESTÃO 3.2
        # =====================================================================
        validate_quest_3_2(cursor)

    except psycopg2.OperationalError as db_err:
        logging.critical(f"Erro de Conexão com o PostgreSQL: {db_err}")
    finally:
        if 'conn' in locals() and conn:
            cursor.close()
            conn.close()
            logging.info("Conexão com o banco de dados encerrada.")


def validate_quest_3_2(cursor) -> int:
    """
    Executa a soma total de linhas das tabelas solicitadas na Questão 3.2:
    customers, orders, order_items e payments.
    """
    logging.info("\n" + "=" * 60)
    logging.info("EXECUTANDO VALIDAÇÃO DA QUESTÃO 3.2...")
    logging.info("=" * 60)

    subqueries = [f"SELECT COUNT(*) AS cnt FROM {tbl}" for tbl in VALIDATION_TABLES]
    validation_sql = f"SELECT SUM(cnt) FROM ({' UNION ALL '.join(subqueries)}) AS total_sum;"

    cursor.execute(validation_sql)
    total_sum = cursor.fetchone()[0]

    for tbl in VALIDATION_TABLES:
        cursor.execute(f"SELECT COUNT(*) FROM {tbl};")
        count = cursor.fetchone()[0]
        logging.info(f"  • {tbl}: {count:,} linhas")

    logging.info("-" * 60)
    logging.info(f"👉 SOMA TOTAL DAS 4 TABELAS (RESPOSTA Q3.2): {total_sum:,} linhas")
    logging.info("=" * 60 + "\n")

    return total_sum


# =============================================================================
# PONTO DE ENTRADA DO SCRIPT
# =============================================================================
if __name__ == "__main__":
    execute_data_ingestion()