# /*
#  * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#  * SPDX-License-Identifier: MIT-0
#  *
#  * Permission is hereby granted, free of charge, to any person obtaining a copy of this
#  * software and associated documentation files (the "Software"), to deal in the Software
#  * without restriction, including without limitation the rights to use, copy, modify,
#  * merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
#  * permit persons to whom the Software is furnished to do so.
#  *
#  * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
#  * INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
#  * PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
#  * HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
#  * OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
#  * SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#  */

import hashlib
import os
from typing import Dict, List, Any


class DataIndexerService:
    """A service for indexing and managing database metadata and embeddings.

    This class provides functionality to fetch metadata from a database,
    generate embeddings for the metadata, store the embeddings, and compare
    user prompts with stored embeddings.

    Attributes:
        embedding_service (EmbeddingService): An instance of EmbeddingService for generating embeddings.
        logger (logging.Logger): Logger for logging information and errors.
        db_name (str): The name of the database to connect to.
        db_secret (Dict[str, str]): Secret for database connection (initialized as None).
    """

    def __init__(self,
                 embedding_service,
                 log):
        """
        Initialize the DataIndexerService.

        Args:
            embedding_service: An instance of EmbeddingService for generating embeddings.
            log: Logger for logging information and errors.
        """
        self.embedding_service = embedding_service
        self.logger = log
        self.db_name = os.environ.get("DB_NAME", "postgres")
        self.db_secret = None

    def fetch_metadata(self, conn) -> List[Dict]:
        """Fetch metadata from the database.

        This method retrieves metadata about tables, columns, and indexes from the connected database.

        Args:
            conn: Database connection object.

        Returns:
            List[Dict]: A list of dictionaries containing metadata for each table.

        Raises:
            Exception: If there is an error fetching metadata from the database.
        """
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    t.table_schema,
                    t.table_name,
                    c.column_name,
                    c.data_type,
                    c.character_maximum_length,
                    c.numeric_precision,
                    c.numeric_scale,
                    c.is_nullable,
                    c.column_default,
                    tc.constraint_type,
                    tc.constraint_name,
                    ccu.table_schema AS referenced_table_schema,
                    ccu.table_name AS referenced_table_name,
                    ccu.column_name AS referenced_column_name
                FROM 
                    information_schema.tables t
                JOIN 
                    information_schema.columns c ON t.table_schema = c.table_schema 
                    AND t.table_name = c.table_name
                LEFT JOIN 
                    information_schema.table_constraints tc ON t.table_schema = tc.table_schema 
                    AND t.table_name = tc.table_name 
                    AND tc.constraint_type IN ('FOREIGN KEY', 'UNIQUE')
                LEFT JOIN 
                    information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name 
                    AND tc.table_schema = kcu.table_schema
                LEFT JOIN 
                    information_schema.referential_constraints rc ON tc.constraint_name = rc.constraint_name 
                    AND tc.table_schema = rc.constraint_schema
                LEFT JOIN 
                    information_schema.constraint_column_usage ccu ON rc.unique_constraint_name = ccu.constraint_name 
                    AND rc.unique_constraint_schema = ccu.table_schema
                WHERE 
                    t.table_schema NOT IN ('pg_catalog', 'information_schema')
                    AND t.table_name != 'embeddings'
                ORDER BY 
                    t.table_schema, 
                    t.table_name, 
                    c.ordinal_position
            """)
            return cur.fetchall()

    def create_embedding_string(self, query_result) -> List[Dict]:
        """Create embedding strings from query results.

        This method processes the query results and creates a list of dictionaries
        containing metadata and embedding text for each table.

        Args:
            query_result: The result of the metadata query.

        Returns:
            List[Dict]: A list of dictionaries containing metadata and embedding text for each table.
        """
        # Group the results by table
        tables = {}
        for row in query_result:
            table_key = (row[0], row[1])  # table_schema, table_name
            if table_key not in tables:
                tables[table_key] = []
            tables[table_key].append(row)

        metadata = []

        for (schema, table_name), columns in tables.items():
            # Start with table information
            table_string = f"Table: {table_name} (Schema: {schema})\nColumns:\n"

            # Add column information
            for col in columns:
                col_name = col[2]
                data_type = col[3]
                max_length = col[4]
                precision = col[5]
                scale = col[6]
                is_nullable = "NULL" if col[7] == 'YES' else "NOT NULL"
                column_default = col[8]
                constraint_type = col[9]
                # description = get_column_description(col_name)
                constraints = []

                # Check for unique constraint
                if constraint_type == 'UNIQUE':
                    constraints.append("UNIQUE")

                # Check for foreign key constraint
                if constraint_type == 'FOREIGN KEY':
                    ref_schema = col[11]
                    ref_table = col[12]
                    ref_column = col[13]
                    constraints.append(f"FOREIGN KEY references {ref_schema}.{ref_table}({ref_column})")

                # Add constraints to the column description
                constraint_str = f" [{', '.join(constraints)}]" if constraints else ""

                # Add precision and scale for numeric types
                if data_type in ["numeric", "decimal", "real", "double precision"]:
                    if precision is not None:
                        data_type += f"({precision}"
                        if scale is not None:
                            data_type += f",{scale}"
                        data_type += ")"

                # Add maximum length for character types
                elif data_type in ['character', 'character varying', 'varchar', 'char']:
                    if max_length is not None:
                        data_type += f"({max_length})"

                table_string += f"- {col_name} ({data_type}, {is_nullable}){constraint_str}\n"

            # Add table summary
            # table_summary = get_table_summary(schema, table_name)
            # table_string += f"\n{table_summary}\n"
            table_definition = {
                "database": self.db_name,
                "schema": schema,
                "table": table_name,
                "embedding_text": table_string,
                "embedding_hash": hashlib.sha256(table_string.encode()).hexdigest()
            }
            metadata.append(table_definition)

        return metadata

    def generate_embeddings(self, metadata) -> List[Dict]:
        """Generate embeddings for the given metadata.

        This method iterates through the metadata and generates an embedding
        for each item's "embedding_text" using the embedding service.

        Args:
            metadata (List[Dict]): A list of metadata dictionaries.

        Returns:
            List[Dict]: The input metadata with added "embedding" key-value pairs.
        """
        for db_metadata in metadata:
            db_embedding = self.embedding_service.get_embedding(db_metadata["embedding_text"])
            db_metadata["embedding"] = db_embedding
        return metadata

    def store_embeddings(self, conn, metadata_w_embedding) -> None:
        """Store embeddings in the database.

        This method stores the generated embeddings along with their metadata in the database.

        Args:
            conn: Database connection object.
            metadata_w_embedding (List[Dict]): A list of dictionaries containing metadata and embeddings.

        Raises:
            Exception: If there's an error during the storage process.
        """
        with conn.cursor() as cur:
            for metadata in metadata_w_embedding:
                embedding = metadata["embedding"]
                embedding_text = metadata["embedding_text"]
                embedding_hash = metadata["embedding_hash"]
                database_name = metadata["database"]
                schema_name = metadata["schema"]
                table_name = metadata["table"]
                # Check if the embedding already exists
                cur.execute("""
                    SELECT id FROM embeddings 
                    WHERE database_name = %s AND schema_name = %s AND table_name = %s AND embedding_hash = %s
                """, (database_name, schema_name, table_name, embedding_hash))

                if cur.fetchone() is not None:
                    self.logger.info(f"Embedding for {database_name}.{schema_name}.{table_name} already exists.")
                    continue

                # If the embedding doesn't exist, insert it
                cur.execute("""
                    INSERT INTO embeddings (embedding, database_name, schema_name, table_name, embedding_text, embedding_hash)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (embedding, database_name, schema_name, table_name, embedding_text, embedding_hash))

                conn.commit()
                self.logger.info(f"Embedding for {database_name}.{schema_name}.{table_name} stored successfully.")

    def compare_embeddings(self, conn, user_prompt: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Compare the embedding of a user prompt with stored embeddings in the database.

        This method generates an embedding for the user prompt and compares it with
        the stored embeddings in the database to find the top-k most similar items.

        Args:
            conn: Database connection object.
            user_prompt (str): The user's input prompt to compare against.
            top_k (int): The number of top similar items to return (default is 5).

        Returns:
            List[Dict[str, Any]]: A list of dictionaries containing the top-k most similar items.

        Raises:
            Exception: If there's an error during the comparison process.
        """
        try:
            # Generate embedding for the user prompt
            user_embedding = self.embedding_service.get_embedding(user_prompt)
            with conn.cursor() as cur:
                # Execute SQL query to compare embeddings
                cur.execute("""
                    SELECT database_name, schema_name, table_name, embedding_text, 
                           1 - (embedding <=> %s::vector) AS similarity
                    FROM embeddings
                    ORDER BY similarity DESC
                    LIMIT %s
                """, (user_embedding, top_k))

                # Fetch and return results
                results = [
                    {"database": row[0], "schema": row[1], "table": row[2],
                     "embedding_text": row[3], "similarity": row[4]}
                    for row in cur.fetchall() if float(row[4]) > 0.10
                ]
                return results
        except Exception as e:
            self.logger.error(f"Error in compare_embeddings: {str(e)}")
            raise
