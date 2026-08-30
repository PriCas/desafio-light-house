"""
===============================================================================
LH NAUTICAL - PIPELINE DE ENGENHARIA DE DADOS
Módulo: Carga de Dados Brutos no Banco PostgreSQL (Ingestion)
Questão: 3.1 (Carregamento automatizado de arquivos CSV na Camada Raw/Bronze)

Descrição:
    Este script conecta ao PostgreSQL via variáveis isoladas (.env) e executa
    o carregamento em massa (bulk COPY) de todos os 24 arquivos CSV.

Priscila Castaldo
Gemini 3.5
===============================================================================
"""

import os
import re
import logging
from pathlib import Path
from typing import List
import psycopg2
from dotenv import load_dotenv

# -----------------------------------------------------------------------------
# 1. CONFIGURAÇÃO DE LOGGING E CARREGAMENTO DE VARIÁVEIS DE AMBIENTE (.ENV)
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("ingestion.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# Carrega e valida credenciais a partir do arquivo .env local
load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

# Validação preventiva contra falta de credenciais
if not all([DB_NAME, DB_USER, DB_PASSWORD]):
    raise ValueError(
        "ERRO CRÍTICO DE CONFIGURAÇÃO: Credenciais de banco de dados não encontradas. "
        "Certifique-se de que o arquivo .env existe e contém DB_NAME, DB_USER e DB_PASSWORD."
    )

CSV_DIR = Path("lh_nautical_csv")
VALIDATION_TABLES: List[str] = ["customers", "orders", "order_items", "payments"]


# -----------------------------------------------------------------------------
# 2. FUNÇÕES AUXILIARES E DE CARGA
# -----------------------------------------------------------------------------

def sanitize_identifier(raw_name: str) -> str:
    """Padroniza o nome da tabela garantindo compatibilidade com o schema.sql."""
    clean_name = raw_name.strip().lower()
    clean_name = re.sub(r"[^a-z0-9_]", "_", clean_name)
    clean_name = re.sub(r"_+", "_", clean_name)
    return clean_name.strip("_")


def conectar_banco():
    """
    Estabelece e retorna a conexão ativa com o PostgreSQL usando UTF-8.
    """
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
        logging.error(f"Falha de Conexão com o PostgreSQL: {error}")
        raise error


def load_single_csv(cursor, csv_path: Path, table_name: str) -> int:
    """
    Executa a carga em massa (COPY) para um arquivo CSV individual.
    """
    # Truncate limpa a tabela prevenindo duplicação em re-execuções (Idempotência)
    cursor.execute(f"TRUNCATE TABLE {table_name} CASCADE;")

    # Comando COPY nativo do PostgreSQL: leitor em massa de alta performance
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

    # Retorna o total de linhas afetadas diretamente pelo cursor sem precisar de SELECT COUNT(*)
    return cursor.rowcount if cursor.rowcount > 0 else 0


def validate_quest_3_2(cursor) -> int:
    """
    Executa a validação agregada requerida na Questão 3.2.
    """
    logging.info("\n" + "=" * 60)
    logging.info("EXECUTANDO VALIDAÇÃO DA QUESTÃO 3.2...")
    logging.info("=" * 60)

    # Obtém e exibe a contagem individual e a soma total em uma única etapa
    total_sum = 0
    for tbl in VALIDATION_TABLES:
        cursor.execute(f"SELECT COUNT(*) FROM {tbl};")
        count = cursor.fetchone()[0]
        total_sum += count
        logging.info(f"  • {tbl}: {count:,} linhas")

    logging.info("-" * 60)
    logging.info(f"👉 SOMA TOTAL DAS 4 TABELAS (RESPOSTA Q3.2): {total_sum:,} linhas")
    logging.info("=" * 60 + "\n")

    return total_sum


# -----------------------------------------------------------------------------
# 3. ORQUESTRADOR DE CARGA
# -----------------------------------------------------------------------------

def execute_data_ingestion() -> None:
    """Orquestra a leitura do diretório, carga idempotente e validação."""
    if not CSV_DIR.exists() or not CSV_DIR.is_dir():
        logging.error(f"Diretório de entrada '{CSV_DIR}' não encontrado.")
        return

    csv_files = sorted(list(CSV_DIR.glob("*.csv")))
    if not csv_files:
        logging.warning(f"Nenhum arquivo .csv encontrado em '{CSV_DIR}'.")
        return

    logging.info(f"Iniciando a carga bruta de {len(csv_files)} arquivos no PostgreSQL...")

    conn = None
    try:
        conn = conectar_banco()
        conn.autocommit = False
        cursor = conn.cursor()

        for csv_file in csv_files:
            table_name = sanitize_identifier(csv_file.stem)
            try:
                rows_count = load_single_csv(cursor, csv_file, table_name)
                conn.commit()  # Confirma a transação por tabela isolada
                logging.info(f"✅ Tabela '{table_name}' populada com sucesso: {rows_count:,} linhas.")
            except Exception as err:
                conn.rollback()  # Isola a falha sem interromper o restante dos CSVs
                logging.error(f"❌ Falha ao carregar a tabela '{table_name}': {err}")

        # Executa a validação solicitada após o término de todas as cargas
        validate_quest_3_2(cursor)

    except Exception as db_err:
        logging.critical(f"Erro no pipeline de ingestão: {db_err}")
    finally:
        if conn:
            cursor.close()
            conn.close()
            logging.info("Conexão com o banco de dados encerrada com segurança.")


# -----------------------------------------------------------------------------
# 4. PONTO DE ENTRADA
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    execute_data_ingestion()