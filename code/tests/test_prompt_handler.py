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
from code.prompt_handler import lambda_handler


class TestPromptHandler(unittest.TestCase):

    @patch('code.prompt_handler.text_to_sql')
    @patch('code.prompt_handler.pg')
    @patch('code.prompt_handler.embed')
    @patch('code.prompt_handler.cache')
    @patch('code.prompt_handler.index')
    def test_lambda_handler_follow_up(self, mock_index, mock_cache, mock_embed, mock_pg, mock_text_to_sql):
        # Mock follow-up question detection
        mock_text_to_sql.check_if_follow_up_question.return_value = {
            "is_follow_up": True,
            "answer": "Based on previous data, there are 5 properties."
        }

        # Test event with follow-up question
        event = {
            'query': 'How many properties are there?',
            'conversation_context': [
                {'role': 'Human', 'content': 'What are the top properties in San Francisco?'},
                {'role': 'Assistant',
                 'content': 'I found 5 top properties in San Francisco with prices ranging from \$1.2M to \$3.5M.'}
            ]
        }

        response = lambda_handler(event, {})

        # Assert that the follow-up path was taken
        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(response["body"]["response"], "Based on previous data, there are 5 properties.")
        self.assertEqual(response["body"]["query"], "Follow-up question answered directly")
        self.assertEqual(response["body"]["query_results"], [])

        # Verify that check_if_follow_up_question was called
        mock_text_to_sql.check_if_follow_up_question.assert_called_once()

        # Verify that we didn't attempt database connections for follow-up questions
        mock_pg.connect_to_db.assert_not_called()

    @patch('code.prompt_handler.text_to_sql')
    @patch('code.prompt_handler.pg')
    @patch('code.prompt_handler.embed')
    @patch('code.prompt_handler.cache')
    @patch('code.prompt_handler.index')
    def test_lambda_handler_non_follow_up(self, mock_index, mock_cache, mock_embed, mock_pg, mock_text_to_sql):
        # Mock follow-up question detection
        mock_text_to_sql.check_if_follow_up_question.return_value = {
            "is_follow_up": False,
            "answer": None
        }

        # Set up mocks for the regular query path
        mock_conn = MagicMock()
        mock_pg.connect_to_db.return_value = mock_conn
        mock_pg.set_secret.return_value = None

        mock_embed.get_embedding.return_value = [0.1, 0.2, 0.3]
        mock_cache.connect_to_cluster.return_value = None
        mock_cache.search.return_value = []  # Simulate cache miss

        mock_index.compare_embeddings.return_value = [{"embedding_text": "Table: property"}]
        mock_text_to_sql.get_sql_from_bedrock.return_value = "SELECT * FROM property LIMIT 10"
        mock_text_to_sql.execute_sql.return_value = [[], ("123 Main St", "\$500k")]
        mock_text_to_sql.describe_results_from_query.return_value = {
            "statusCode": 200,
            "body": {
                "response": "Found property at 123 Main St for \$500k",
                "query": "SELECT * FROM property LIMIT 10",
                "query_results": [("123 Main St", "\$500k")],
                "cache_id": None
            },
            "headers": {"Content-Type": "application/json"}
        }

        # Test event with a new question
        event = {
            'query': 'What are affordable properties in Seattle?',
            'conversation_context': [
                {'role': 'Human', 'content': 'What are the top properties in San Francisco?'},
                {'role': 'Assistant',
                 'content': 'I found 5 top properties in San Francisco with prices ranging from \$1.2M to \$3.5M.'}
            ]
        }

        response = lambda_handler(event, {})

        # Assert response is what we expect
        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(response["body"]["response"], "Found property at 123 Main St for \$500k")

        # Verify the regular query path was taken
        mock_text_to_sql.check_if_follow_up_question.assert_called_once()
        mock_pg.connect_to_db.assert_called_once()
        mock_embed.get_embedding.assert_called_once()
        mock_cache.search.assert_called_once()
        mock_index.compare_embeddings.assert_called_once()
        mock_text_to_sql.get_sql_from_bedrock.assert_called_once()
        mock_text_to_sql.execute_sql.assert_called_once()
        mock_text_to_sql.describe_results_from_query.assert_called_once()
