"""
===============================================================================
LH NAUTICAL - PIPELINE DE ENGENHARIA DE DADOS
Módulo: Gerador Automático de Schema DDL (PostgreSQL)
Questão: 2.1 (Geração de DDL a partir de arquivos CSV)

Descrição:
    Este script analisa arquivos CSV no diretório especificado, realiza a
    inferência dos tipos de dados via amostragem de conteúdo e gera um único
    arquivo SQL ('schema.sql') com as instruções de criação de tabelas (DDL)
    compatíveis com PostgreSQL.

Premissas & Restrições:
    - Uso exclusivo da Biblioteca Padrão do Python 3 .
    - Compatibilidade total com a sintaxe do PostgreSQL.
    - Leitura streaming eficiente para não sobrecarregar a memória RAM.

Autor: Priscila Castaldo
===============================================================================
"""

import csv
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

# =============================================================================
# CONFIGURAÇÕES E CONSTANTES GLOBAIS
# =============================================================================

# Diretório base contendo os arquivos CSV de entrada
DEFAULT_CSV_DIR = Path("lh_nautical_csv")

# Arquivo SQL de saída com os DDLs consolidados
DEFAULT_OUTPUT_SQL = Path("schema.sql")

# Limite de linhas amostradas por arquivo para inferência de tipos.
# 5.000 linhas oferecem um excelente equilíbrio entre precisão estatística e velocidade.
SAMPLE_ROW_LIMIT: int = 5000

# Limite máximo para o tipo INTEGER assinado do PostgreSQL (4 bytes)
POSTGRES_MAX_INT: int = 2_147_483_647

# Limite máximo para o tipo BIGINT
POSTGRES_MAX_BIGINT = 9_223_372_036_854_775_807


# =============================================================================
# FUNÇÕES DE HIGIENIZAÇÃO E PADRONIZAÇÃO (SANITY CHECK)
# =============================================================================

def sanitize_identifier(raw_name: str) -> str:
    """
    Normaliza nomes de tabelas e colunas para o padrão snake_case do PostgreSQL.

    Regras aplicadas:
    1. Converte para minúsculas.
    2. Remove acentos e substitui caracteres não alfanuméricos por underline '_'.
    3. Remove underlines duplicados ou nas extremidades.

    Args:
        raw_name (str): Nome original vindo do cabeçalho do CSV ou do arquivo.

    Returns:
        str: Identificador seguro para uso direto em SQL sem aspas duplas.
    """
    if not raw_name:
        return "coluna_sem_nome"
    
    # Substitui espaços no inicio e fim da palavra e coloca em minúsculo
    clean_name = raw_name.strip().lower()
    # Substitui qualquer caractere que não seja letra a-z ou número 0-9 por '_'
    clean_name = re.sub(r"[^a-z0-9_]", "_", clean_name)
    # Reduz múltiplos underlines consecutivos para um único '_'
    clean_name = re.sub(r"_+", "_", clean_name)
    # Remove underlines do início e do fim
    clean_name = clean_name.strip("_")

    return clean_name or "coluna_invalida"


# =============================================================================
# MOTOR DE INFERÊNCIA DE TIPOS DE DADOS (TYPE INFERENCE ENGINE)
# =============================================================================

def _is_boolean(value: str) -> bool:
    """Verifica se uma string representa um valor booleano válido."""
    valid_booleans: Set[str] = {"true", "false", "t", "f", "1", "0"}
    return value.strip().lower() in valid_booleans


def _is_integer(value: str) -> bool:
    """Verifica se uma string é um número inteiro válido."""
    try:
        int(value)
        return True
    except ValueError:
        return False


def _is_float(value: str) -> bool:
    """Verifica se uma string representa um número decimal (ponto/vírgula)."""
    try:
        # Suporta tanto o ponto decimal padrão quanto a vírgula pt-BR
        float(value.replace(",", "."))
        return True
    except ValueError:
        return False


def _is_timestamp(value: str) -> bool:
    """Testa múltiplos formatos ISO e padrão de data/hora."""
    date_formats: List[str] = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    ]
    val_clean = value.strip()
    for fmt in date_formats:
        try:
            datetime.strptime(val_clean, fmt)
            return True
        except ValueError:
            continue
    return False


def infer_postgres_type(sample_values: List[str]) -> str:
    """
    Determina o tipo de dado PostgreSQL mais adequado com base numa lista de amostragem.

    A hierarquia de promoção de tipos segue uma estratégia de menor privilégio:
    BOOLEAN -> INTEGER -> BIGINT -> NUMERIC -> TIMESTAMP/DATE -> TEXT

    Args:
        sample_values (List[str]): Lista com os valores amostrados da coluna.

    Returns:
        str: Tipo nativo do PostgreSQL (ex: 'INTEGER', 'NUMERIC', 'TEXT').
    """
    # Filtra células vazias ou compostas apenas por espaços (Tratamento de metadados apenas)
    non_null_values = [v.strip() for v in sample_values if v is not None and v.strip() != ""]

    # Se a coluna for 100% nula na amostragem, adota TEXT por segurança
    if not non_null_values:
        return "TEXT"

    # 1. Teste de Booleano
    if all(_is_boolean(v) for v in non_null_values):
        return "BOOLEAN"
    
    # 2. Teste de Inteiro (com verificação de estouro para BIGINT)
    if all(_is_integer(v) for v in non_null_values):
        max_val = max(abs(int(v)) for v in non_null_values)
        if max_val > POSTGRES_MAX_BIGINT:
            return "TEXT"  # Para chaves/códigos longos como NFe de 44 dígitos
        elif max_val > POSTGRES_MAX_INT:
            return "BIGINT"
        return "INTEGER"

    # 3. Teste de Decimal / Ponto Flutuante (Valores monetários, métricas)
    if all(_is_float(v) for v in non_null_values):
        return "NUMERIC"

    # 4. Teste de Data e Hora
    if all(_is_timestamp(v) for v in non_null_values):
        has_time_component = any(":" in v for v in non_null_values)
        return "TIMESTAMP" if has_time_component else "DATE"

    # 5. Fallback padrão para strings genéricas
    return "TEXT"


# =============================================================================
# GERADOR DE DDL E PROCESSAMENTO DE ARQUIVOS
# =============================================================================

def process_single_csv(csv_path: Path) -> Optional[str]:
    """
    Lê um arquivo CSV individual e constrói a instrução 'CREATE TABLE' em SQL.

    Args:
        csv_path (Path): Caminho completo para o arquivo CSV.

    Returns:
        Optional[str]: Bloco SQL de DDL da tabela ou None caso o arquivo esteja vazio.
    """
    table_name = sanitize_identifier(csv_path.stem)

    # Utiliza 'utf-8-sig' para tratar automaticamente o caractere invisível BOM (\ufeff)
    with csv_path.open(mode="r", encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)

        try:
            raw_headers = next(reader)
        except StopIteration:
            print(f"⚠️  [Aviso] Arquivo vazio ignorado: {csv_path.name}")
            return None

        # Higieniza os nomes das colunas
        columns = [sanitize_identifier(h) for h in raw_headers]
        columns_data: Dict[str, List[str]] = {col: [] for col in columns}

        # Coleta a amostragem de dados linha por linha (Memory Friendly)
        for row_idx, row in enumerate(reader):
            if row_idx >= SAMPLE_ROW_LIMIT:
                break
            for col_idx, cell_value in enumerate(row):
                if col_idx < len(columns):
                    columns_data[columns[col_idx]].append(cell_value)

        # Montagem das cláusulas DDL
        sql_lines: List[str] = [
            f"-- ========================================================",
            f"-- Tabela: {table_name} (Fonte: {csv_path.name})",
            f"-- ========================================================",
            f"DROP TABLE IF EXISTS {table_name} CASCADE;",
            f"CREATE TABLE {table_name} ("
        ]

        column_definitions: List[str] = []
        for col_name in columns:
            col_type = infer_postgres_type(columns_data[col_name])

            # Aplicação pragmática de Chave Primária por convenção de nomenclatura
            if col_name in ("id", f"{table_name}_id", f"{table_name[:-1]}_id"):
                definition = f"    {col_name} {col_type} PRIMARY KEY"
            else:
                definition = f"    {col_name} {col_type}"

            column_definitions.append(definition)

        sql_lines.append(",\n".join(column_definitions))
        sql_lines.append(");\n")

        print(f"✅ Tabela '{table_name}' mapeada com sucesso ({len(columns)} colunas).")
        return "\n".join(sql_lines)


def generate_schema(input_dir: Path = DEFAULT_CSV_DIR, output_file: Path = DEFAULT_OUTPUT_SQL) -> None:
    """
    Itera sobre o diretório de CSVs, gera os DDLs e consolida no arquivo 'schema.sql'.

    Args:
        input_dir (Path): Diretório contendo os arquivos .csv.
        output_file (Path): Caminho do arquivo .sql a ser gerado.
    """
    if not input_dir.exists() or not input_dir.is_dir():
        raise FileNotFoundError(f"❌ Diretório de entrada não encontrado: '{input_dir}'")

    # Localiza e ordena todos os arquivos CSV para garantir reprodutibilidade
    csv_files = sorted(list(input_dir.glob("*.csv")))

    if not csv_files:
        print(f"⚠️  Nenhum arquivo CSV encontrado em '{input_dir}'.")
        return

    print(f"🚀 Iniciando mapeamento de {len(csv_files)} arquivos CSV para PostgreSQL...\n")

    ddl_blocks: List[str] = [
        "-- ========================================================",
        "-- DESAFIO LIGHTHOUSE - SCHEMA DDL (POSTGRESQL)",
        f"-- Data de Geração: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "-- Gerado via Script Python Puro (Biblioteca Padrão)",
        "-- ========================================================\n"
    ]

    for csv_file in csv_files:
        ddl_script = process_single_csv(csv_file)
        if ddl_script:
            ddl_blocks.append(ddl_script)

    # Gravando o arquivo de saída consolidado
    with output_file.open(mode="w", encoding="utf-8") as out:
        out.write("\n\n".join(ddl_blocks))

    print(f"\n🎉 Sucesso! Arquivo '{output_file}' gerado com {len(csv_files)} tabelas.")


# =============================================================================
# PONTO DE ENTRADA DO SCRIPT (MAIN ENTRYPOINT)
# =============================================================================

if __name__ == "__main__":
    generate_schema()