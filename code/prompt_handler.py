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
import json
from typing import Any, Dict

import boto3

from services.cache import CacheService
from services.embed import EmbeddingService
from services.indexer import DataIndexerService
from services.postgres import PostgreSQLService
from services.text_to_sql import TextToSQL
from util.lambda_logger import create_logger
from util.postgres_validation import is_valid_postgres_identifier

# Get the Lambda function name from the environment
lambda_function_name = os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "UnknownFunction")

# Setup logging
logger = create_logger(lambda_function_name)

session = boto3.session.Session()
bedrock_client = session.client("bedrock-runtime")
sm_client = session.client("secretsmanager")

RDS_HOST = os.getenv("RDS_HOST")
RDS_DATABASE_NAME = os.getenv("DB_NAME", "postgres")
RDS_SCHEMA = os.getenv("DB_SCHEMA", "public")
SECRET_NAME = os.getenv("SECRET_NAME")

MEMDB_ENDPOINT = os.getenv("MEMDB_CACHE_ENDPOINT")

# Adjust as needed
VECTOR_SCORE_THRESHOLD = 0.85

embed = EmbeddingService(bedrock_client=bedrock_client, logger=logger)
index = DataIndexerService(embedding_service=embed, log=logger)
cache = CacheService(logger=logger)
pg = PostgreSQLService(secret_client=sm_client, db_host=RDS_HOST, db_name=RDS_DATABASE_NAME, log=logger)
text_to_sql = TextToSQL(secret_client=sm_client, bedrock_client=bedrock_client, log=logger)


def lambda_handler(event: Dict[str, Any], context: Any):
    """AWS Lambda handler for processing prompt requests.

    This function handles processes a prompt by looking up the MemoryDB cache for similar items.
    If a cache miss occurs, it generates a textual context from similar tables to the prompt,
    generates a SQL statement from textual context, and executes the SQL statement.
    The results are then described in natural language and returned as the response.

    Args:
        event (Dict[str, Any]): The event dict containing the parameters passed to the function.
        context (Any): The context in which the function is called.

    Returns:
        Dict: The result of delete_item for DELETE requests.
        None: For other types of requests.

    Raises:
        Exception: If it fails to connect to the database.
    """
    logger.debug(f"{event}")
    logger.info("Start")

    prompt = event['query']
    conversation_context = event.get('conversation_context', [])

    # First, check if this is a follow-up question and can be answered directly
    if conversation_context:
        # Combine the conversation context with the current prompt
        full_prompt = "\n".join([f"{msg['role']}: {msg['content']}" for msg in conversation_context])
        full_prompt += f"\nHuman: {prompt}"

        # Create a prompt to check if this is a follow-up question that can be answered directly
        follow_up_check = text_to_sql.check_if_follow_up_question(full_prompt)

        # If it's a follow-up that can be answered directly without SQL
        if follow_up_check["is_follow_up"]:
            logger.info("Handling as follow-up question without SQL")
            return {"statusCode": 200,
                    "body": {"response": follow_up_check["answer"], "query": "Follow-up question answered directly",
                             "query_results": [], "cache_id": None}, "headers": {"Content-Type": "application/json"}}

    if not (is_valid_postgres_identifier(RDS_DATABASE_NAME) or is_valid_postgres_identifier(RDS_SCHEMA)):
        raise Exception(f"'{RDS_SCHEMA}' or '{RDS_DATABASE_NAME}' is not a valid PostgreSQL name.")
    pg.set_secret(SECRET_NAME)
    t2sql_conn = pg.connect_to_db()
    if not t2sql_conn:
        raise Exception("Failed to connect to database for text-to-SQL user")
    try:
        # Combine the conversation context with the current prompt
        full_prompt = "\n".join([f"{msg['role']}: {msg['content']}" for msg in conversation_context])
        full_prompt += f"\nHuman: {prompt}"

        embeddings_for_prompt = embed.get_embedding(prompt)
        cache.connect_to_cluster(MEMDB_ENDPOINT)
        cache_lookup = cache.search(vector=embeddings_for_prompt)
        cache_entry = None

        if cache_lookup:
            for entry in cache_lookup:
                logger.debug(entry)
                stored_prompt = entry.get("prompt_text")
                if stored_prompt == prompt:
                    logger.debug(f"EXACT MATCH FOUND with vector score: {entry['vector_score']}")
                    # Force use this entry regardless of score
                    cache_entry = entry

        cache_hit = False

        # First priority: exact text match
        if cache_entry is not None:
            logger.info("Exact match cache hit")
            cache_hit = True
        # Second priority: vector similarity above threshold
        elif cache_lookup and float(cache_lookup[0]["vector_score"]) >= VECTOR_SCORE_THRESHOLD:
            logger.info("Vector-based cache hit")
            cache_entry = cache_lookup[0]
            cache_hit = True

        # Now handle either cache hit or miss
        if not cache_hit:
            logger.info("Cache miss")

            # Find relevant tables in index
            schema_results = index.compare_embeddings(t2sql_conn, prompt)

            # Generate textual context for similar tables
            schema_context = []
            for result in schema_results:
                logger.debug(result)
                schema_context.append(result["embedding_text"])
            scehma_context_text = "\n\n".join(schema_context)

            # Include schema context in prompt to get better results
            sql = text_to_sql.get_sql_from_bedrock(prompt, scehma_context_text)
            logger.debug(f"sql::{sql}")
            if not sql:
                return {"statusCode": 500,
                        "body": {"response": "Unable to generate SQL for the provided prompt, please try again."},
                        "headers": {"Content-Type": "application/json"}}
            # Execute the SQL statement
            sql_response, column_names = text_to_sql.execute_sql(t2sql_conn, sql)
            logger.debug(f"sql_response::{sql_response}")
            logger.debug(f"column_names::{column_names}")

            # Describe the SQL results in natural language
            # Pass the tuple to describe_results_from_query
            response = text_to_sql.describe_results_from_query(sql, (sql_response, column_names), scehma_context_text)

            # Add entry to cache for future invocations
            cache_data = {"sql_statement": sql, "text_response": response["body"]["response"],
                          "query_results": str(sql_response), "column_names": column_names,
                          "schema_text": scehma_context_text, "prompt_text": prompt}
            cache.add(key=prompt, vector=embeddings_for_prompt, data=cache_data, prefix="cache")

            # Return the response
            return response
        else:
            logger.info("Cache hit")
            # Take the highest similarity result and use it to get the SQL response
            cache_entry = cache_entry if cache_entry else cache_lookup[0]
            logger.info(f"Cache similarity: {cache_entry['vector_score']}")
            sql_statement = cache_entry.get("sql_statement")
            if sql_statement and sql_statement.startswith("["):
                # This might be a JSON string representing [query, params]
                try:
                    sql_statement = json.loads(sql_statement)
                except json.JSONDecodeError:
                    pass
            return {"statusCode": 200, "body": {"response": cache_entry["text_response"], "query": sql_statement,
                                                "query_results": cache_entry["query_results"],
                                                "column_names": cache_entry.get("column_names", []),
                                                "cache_id": cache_entry["id"]},
                    "headers": {"Content-Type": "application/json"}}
    finally:
        logger.info("Closing connection")
        logger.info("End")
        t2sql_conn.close()
