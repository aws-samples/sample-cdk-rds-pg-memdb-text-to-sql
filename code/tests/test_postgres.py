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
from unittest.mock import patch, MagicMock
from code.services.postgres import PostgreSQLService
from code.util.postgres_validation import is_valid_postgres_identifier, POSTGRES_RESERVED_WORDS


class TestPostgreSQLService(unittest.TestCase):

    def setUp(self):
        self.secret_client = MagicMock()
        self.logger = MagicMock()
        self.postgres_service = PostgreSQLService(self.secret_client, "localhost", "testdb", self.logger)

    @patch("code.services.postgres.json.loads")
    def test_set_secret(self, mock_json_loads):
        mock_secret = {"username": "user", "password": "pass"}
        mock_json_loads.return_value = mock_secret
        self.secret_client.get_secret_value.return_value = {"SecretString": "dummy"}

        self.postgres_service.set_secret(secret_id="test_secret")

        self.secret_client.get_secret_value.assert_called_once()
        self.assertEqual(self.postgres_service.db_secret, mock_secret)

    @patch("code.services.postgres.psycopg.connect")
    def test_connect_to_db(self, mock_connect):
        mock_connection = MagicMock()
        mock_connect.return_value = mock_connection
        self.postgres_service.db_secret = {"username": "user", "password": "pass"}

        result = self.postgres_service.connect_to_db()

        mock_connect.assert_called_once_with(
            host="localhost",
            dbname="testdb",
            user="user",
            password="pass"
        )
        self.assertEqual(result, mock_connection)

    @patch("code.services.postgres.psycopg.connect")
    def test_connect_to_db_error(self, mock_connect):
        mock_connect.side_effect = Exception("Connection failed")
        self.postgres_service.db_secret = {"host": "localhost", "port": 5432, "dbname": "testdb", "username": "user",
                                           "password": "pass"}

        with self.assertRaises(Exception):
            self.postgres_service.connect_to_db()

        self.logger.error.assert_called_once()


class TestPostgresValidation(unittest.TestCase):

    def test_is_valid_postgres_identifier(self):
        # Test valid identifiers
        self.assertTrue(is_valid_postgres_identifier("public"))
        self.assertTrue(is_valid_postgres_identifier("postgres"))
        self.assertTrue(is_valid_postgres_identifier("valid_name"))
        self.assertTrue(is_valid_postgres_identifier("Valid_Name_123"))
        self.assertTrue(is_valid_postgres_identifier("_valid_name"))

        # Test invalid identifiers
        self.assertFalse(is_valid_postgres_identifier(""))  # Empty string
        self.assertFalse(is_valid_postgres_identifier("123invalid"))  # Starts with number
        self.assertFalse(is_valid_postgres_identifier("invalid-name"))  # Contains hyphen
        self.assertFalse(is_valid_postgres_identifier("pg_invalid"))  # Starts with pg_
        self.assertFalse(is_valid_postgres_identifier("a" * 64))  # Too long (> 63 bytes)

    def test_is_valid_postgres_identifier_reserved_words(self):
        # Test a few reserved words (case-insensitive)
        for word in ["select", "FROM", "Where", "pg_schema"]:
            self.assertFalse(is_valid_postgres_identifier(word))

        # Test that reserved words are rejected regardless of case
        for word in POSTGRES_RESERVED_WORDS:
            self.assertFalse(is_valid_postgres_identifier(word.lower()))
            self.assertFalse(is_valid_postgres_identifier(word.upper()))


if __name__ == "__main__":
    unittest.main()