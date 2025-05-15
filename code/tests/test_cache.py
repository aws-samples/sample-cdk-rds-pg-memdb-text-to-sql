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

import unittest
import random
from unittest.mock import patch, MagicMock

from code.services.cache import CacheService


class TestCacheService(unittest.TestCase):

    def setUp(self):
        self.logger = MagicMock()
        self.cache_service = CacheService(self.logger)

    @patch('code.services.cache.ValkeyCluster')
    def test_connect_to_cluster(self, mock_valkey_cluster):
        self.cache_service.connect_to_cluster(memdb_endpoint="localhost")
        mock_valkey_cluster.assert_called_once()
        self.assertIsNotNone(self.cache_service.valkey_client)

    @patch('code.services.cache.ValkeyCluster')
    def test_add(self, mock_valkey_cluster):
        self.cache_service.valkey_client = MagicMock()
        vector = [0.1, 0.2, 0.3]

        data = {
            "sql_statement": "SELECT * FROM table",
            "text_response": "Sample response",
            "query_results": "Sample results",
            "schema_text": "Sample schema",
            "prompt_text": "Sample prompt",
            "column_names": []
        }
        expected_mapping = {
            "vector": self.cache_service._vector_to_bytes(vector),
            "sql_statement": data["sql_statement"],
            "text_response": data["text_response"],
            "query_results": data["query_results"],
            "schema_text": data["schema_text"],
            "prompt_text": data["prompt_text"],
            "column_names": "[]"
        }

        self.cache_service.add("What are the top properties?", vector, data, "cache")

        self.cache_service.valkey_client.hset.assert_called_once_with(
            "cache:4099728cd5473e0179641789eb02072bd198a9b5c90311962775d828f63b6c09",
            mapping=expected_mapping
        )

    def test_vector_to_bytes(self):
        vector = [0.1, 0.2, 0.3]
        bytes1 = self.cache_service._vector_to_bytes(vector)
        self.assertIsInstance(bytes1, bytes)
        self.assertEqual(len(bytes1), len(vector) * 4)  # 4 bytes per float

    def test_vector_to_bytes_large(self):
        # Test case 2: Large vector
        vector = [random.random() for _ in range(1000)]
        bytes2 = self.cache_service._vector_to_bytes(vector)
        self.assertIsInstance(bytes2, bytes)
        self.assertEqual(len(bytes2), len(vector) * 4)

    def test_hash_key(self):
        result1 = self.cache_service._hash_key("prefix", "key")
        self.assertIsInstance(result1, str)
        self.assertTrue(result1.startswith("prefix:"))


if __name__ == '__main__':
    unittest.main()
