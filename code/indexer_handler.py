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

import os
from typing import Dict, Any

import boto3

from services.postgres import PostgreSQLService
from services.indexer import DataIndexerService
from services.embed import EmbeddingService

from util.lambda_logger import create_logger
from util.postgres_validation import is_valid_postgres_identifier
# Get the Lambda function name from the environment
lambda_function_name = os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "UnknownFunction")

# Setup logging
logger = create_logger(lambda_function_name)

session = boto3.session.Session()
sm = session.client(service_name="secretsmanager")
bedrock_runtime = boto3.client("bedrock-runtime")

RDS_HOST = os.getenv("RDS_HOST")
RDS_DATABASE_NAME = os.getenv("DB_NAME", "postgres")
RDS_SCHEMA = os.getenv("DB_SCHEMA", "public")
INDEXER_SECRET_ID = os.environ.get("INDEXER_SECRET_ID")

embed = EmbeddingService(bedrock_client=bedrock_runtime, logger=logger)
pg = PostgreSQLService(secret_client=sm, db_host=RDS_HOST, db_name=RDS_DATABASE_NAME, log=logger)
indexer = DataIndexerService(embedding_service=embed, log=logger)


def lambda_handler(event: Dict[str, Any], context: Any):
    """AWS Lambda handler for indexing metadata.

    This function connects to a database, fetches metadata, creates an embedding string,
    generates embeddings, and stores them in the database.

    Args:
        event (Dict[str, Any]): The event dict containing the parameters passed to the function.
        context (Any): The context in which the function is called.

    Raises:
        Exception: If it fails to connect to the database.

    Returns:
        None
    """
    if not (is_valid_postgres_identifier(RDS_DATABASE_NAME) or is_valid_postgres_identifier(RDS_SCHEMA)):
        raise Exception(f"'{RDS_SCHEMA}' or '{RDS_DATABASE_NAME}' is not a valid PostgreSQL name.")
    pg.set_secret(INDEXER_SECRET_ID)
    idx_conn = pg.connect_to_db()
    if not idx_conn:
        raise Exception("Failed to connect to database for index user")
    try:
        cursor_result = indexer.fetch_metadata(idx_conn)
        metadata = indexer.create_embedding_string(cursor_result)
        metadata_w_embeddings = indexer.generate_embeddings(metadata)
        indexer.store_embeddings(idx_conn, metadata_w_embeddings)
    finally:
        logger.info("Closing connection")
        logger.info("End")
        idx_conn.close()
