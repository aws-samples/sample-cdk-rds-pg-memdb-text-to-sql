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
import json
import logging
from array import array
from datetime import timedelta
from typing import List, Dict, Any

from valkey.cluster import ValkeyCluster
from valkey.commands.search.field import VectorField, TextField
from valkey.commands.search.indexDefinition import IndexDefinition, IndexType
from valkey.commands.search.query import Query
from valkey.exceptions import ResponseError, ValkeyError


class CacheService:
    """A service for managing cache operations using Valkey.

    This class provides methods for connecting to a Valkey cluster,
    setting up indexes, searching, adding, and deleting cache entries.
    It uses vector similarity search for efficient data retrieval.

    Attributes:
        valkey_client: Valkey client for interacting with the Valkey cluster.
        logger (logging.Logger): Logger instance for logging operations.
        DATA_INDEX_NAME (str): Name of the Redis search index.
    """

    def __init__(self, logger: logging.Logger):
        """Initialize the CacheService.

        Args:
            logger (logging.Logger): Logger instance for logging operations.
        """
        self.valkey_client = None
        self.logger = logger
        self.DATA_INDEX_NAME = "cache_vector_index"

    def connect_to_cluster(self, memdb_endpoint: str) -> None:
        """Connect to the Redis cluster and set up the index.

        Args:
            memdb_endpoint (str): The endpoint of the MemoryDB cluster.

        Raises:
            Exception: If there is an error connecting to the Redis cluster.
        """
        try:
            self.valkey_client = ValkeyCluster(
                host=memdb_endpoint,
                port=6379,
                ssl=True
            )
            self.valkey_client.ping()
            self.logger.info("Connection to Amazon MemoryDB successful")
            self.setup_index()
        except Exception as e:
            self.logger.error(f"Error connecting to Valkey cluster: {e}")

    def setup_index(self) -> None:
        """Set up the Redis search index.

        If the index already exists, log a message. Otherwise, create a new index
        with the specified schema and definition.

        Raises:
            ResponseError: If there is an error creating the index.
        """
        try:
            self.valkey_client.ft(self.DATA_INDEX_NAME).info()
            self.logger.info("Cache index already exists!")
        except ResponseError as _:
            schema = (
                TextField("sql_statement"),
                TextField("text_response"),
                TextField("query_results"),
                TextField("prompt_text"),
                TextField("schema_text"),
                TextField("column_names"),
                VectorField("vector", "HNSW", {
                    "TYPE": "FLOAT32",
                    "DIM": 1536,
                    "DISTANCE_METRIC": "COSINE",
                }),
            )
            definition = IndexDefinition(prefix=["cache:"], index_type=IndexType.HASH)
            self.valkey_client.ft(self.DATA_INDEX_NAME).create_index(fields=schema, definition=definition)
            self.logger.info(f"Created cache index {self.DATA_INDEX_NAME}")

    def search(self, vector: List[float], top_k: int = 20) -> List[Dict[str, Any]]:
        """Search for similar vectors in the cache.

        Args:
            vector (List[float]): The query vector to search for.
            top_k (int, optional): The number of results to return. Defaults to 3.

        Returns:
            List[Dict[str, Any]]: A list of dictionaries containing the search results,
            including the vector score and other associated data.
        """
        vector_bytes = self._vector_to_bytes(vector)
        index_name = self.DATA_INDEX_NAME
        search_query = "@vector:[VECTOR_RANGE $radius $vec]=>{$YIELD_DISTANCE_AS: score}"
        self.logger.debug(search_query)
        q = (
            Query(search_query)
            .paging(0, top_k)
            .sort_by("score")
            .dialect(2)
            .return_fields("sql_statement", "text_response", "query_results", "prompt_text", "schema_text", "score", "column_names")
        )
        query_params = {"radius": 0.8, "vec": vector_bytes}

        response = self.valkey_client.ft(index_name).search(q, query_params).docs

        flattened_response = []
        for doc in response:
            doc_dict = {
                "id": doc.id,
                "sql_statement": getattr(doc, "sql_statement", None),
                "text_response": getattr(doc, "text_response", None),
                "query_results": getattr(doc, "query_results", None),
                "prompt_text": getattr(doc, "prompt_text", None),
                "schema_text": getattr(doc, "schema_text", None),
                "column_names": getattr(doc, "column_names", None),
                "vector_score": round(1 - float(doc.score), 2)
            }
            flattened_response.append(doc_dict)

        self.logger.debug(flattened_response)
        return flattened_response

    def add(self, key: str, vector: List[float], data: Dict[str, Any], prefix: str) -> bool:
        """Add a key to the cache."""
        key = self._hash_key(prefix, key)
        vector_bytes = self._vector_to_bytes(vector)

        # Convert any non-serializable types to strings
        sql_statement = data["sql_statement"]
        # Handle the psycopg3 format which could be a list containing [query_string, parameters]
        if isinstance(sql_statement, (list, tuple)):
            sql_statement = json.dumps(sql_statement)

        # Same for query results
        query_results = data["query_results"]
        if not isinstance(query_results, str):
            query_results = str(query_results)

        # Ensure column_names is properly serialized
        column_names = data.get("column_names", [])
        if not isinstance(column_names, str):
            column_names = json.dumps(column_names)

        mapping = {
            "vector": vector_bytes,
            "sql_statement": sql_statement,
            "text_response": data["text_response"],
            "query_results": query_results,
            "schema_text": data["schema_text"],
            "prompt_text": data["prompt_text"],
            "column_names": column_names
        }

        if not data["text_response"]:
            self.logger.error("Unable to add to cache, missing SQL statement.")
            return False

        self.logger.debug(f"Adding to cache index: {key} {json.dumps(mapping, default=str)}")

        try:
            self.valkey_client.hset(key, mapping=mapping)
            # Set expiration time to 10 minutes (600 seconds)
            expiration_time = timedelta(minutes=10)
            # Add expiration to the key
            self.valkey_client.expire(key, expiration_time)
            # Verify the expiration time
            ttl = self.valkey_client.ttl(key)
            self.logger.debug(f"Time to live for '{key}': {ttl} seconds")

            # Validate the cache key has been set
            retrieved_value = self.valkey_client.hget(key, "prompt_text")
            self.logger.debug(f"Retrieved value: {retrieved_value}")
            return True
        except ValkeyError as e:
            self.logger.error(f"Error adding to cache: {str(e)}")
            return False

    # For testing purposes
    def purge(self):
        """Purge all cache entries and drop the index.

        This method is intended for testing purposes only.
        It deletes all keys with the 'cache:' prefix and drops the search index.
        """
        for key in self.valkey_client.scan_iter(match=f"cache:*"):
            self.logger.info(f"Deleting {key}")
            self.valkey_client.delete(key)
        self.valkey_client.ft(self.DATA_INDEX_NAME).dropindex()
        self.logger.info(f"Deleted index {self.DATA_INDEX_NAME}")

    @staticmethod
    def _vector_to_bytes(vector: List[float]) -> bytes:
        """Convert a list of floats to bytes.

        Args:
            vector (List[float]): The vector to convert.

        Returns:
            bytes: The vector as bytes.
        """
        return array("f", vector).tobytes()

    @staticmethod
    def _hash_key(prefix: str, key: str) -> str:
        """Create a hashed key from a prefix and a key.

        Args:
            prefix (str): The prefix for the key.
            key (str): The key to hash.

        Returns:
            str: The hashed key.
        """
        return f"{prefix}:{hashlib.sha256(key.encode()).hexdigest()}"
