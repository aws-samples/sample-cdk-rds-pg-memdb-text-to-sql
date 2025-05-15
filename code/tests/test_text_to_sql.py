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
from code.services.text_to_sql import TextToSQL

class TestTextToSQL(unittest.TestCase):

    def setUp(self):
        self.secret_client = MagicMock()
        self.bedrock_client = MagicMock()
        self.logger = MagicMock()
        self.text_to_sql = TextToSQL(self.secret_client, self.bedrock_client, self.logger)

    @patch.object(TextToSQL, '_TextToSQL__call_bedrock')
    def test_get_sql_from_bedrock(self, mock_call_bedrock):
        mock_call_bedrock.return_value = "<sql>SELECT * FROM users WHERE id = $1;</sql>"
        result = self.text_to_sql.get_sql_from_bedrock("Get user with ID 1", "users(id, name)")
        self.assertEqual(result, ("SELECT * FROM users WHERE id = $1;", []))

    def test_execute_sql(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [("John", 30), ("Jane", 25)]

        result, column_names = self.text_to_sql.execute_sql(mock_conn, "SELECT name, age FROM users")
        self.assertEqual(result, [("John", 30), ("Jane", 25)])
        mock_cursor.execute.assert_called_once_with("SELECT name, age FROM users", [])

    @patch.object(TextToSQL, '_TextToSQL__call_bedrock')
    def test_describe_results_from_query(self, mock_call_bedrock):
        mock_call_bedrock.return_value = "The query returned two users: John (30 years old) and Jane (25 years old)."
        result = self.text_to_sql.describe_results_from_query(
            "SELECT name, age FROM users",
            ([("John", 30), ("Jane", 25)], ["name", "age"]),
            "users(name, age)"
        )
        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(result["body"]["response"], "The query returned two users: John (30 years old) and Jane (25 years old).")
        self.assertEqual(result["body"]["query"], "SELECT name, age FROM users")
        self.assertEqual(result["body"]["query_results"], [("John", 30), ("Jane", 25)])
        self.assertEqual(result["body"]["column_names"], ["name", "age"])
        self.assertIsNone(result["body"]["cache_id"])
        self.assertEqual(result["headers"], {"Content-Type": "application/json"})

    @patch.object(TextToSQL, '_TextToSQL__call_bedrock')
    def test_check_if_follow_up_question(self, mock_call_bedrock):
        # Test case where it is a follow-up question
        mock_call_bedrock.return_value = """
        {
          "is_follow_up": true,
          "answer": "Based on the previous conversation, there are 5 properties in San Francisco."
        }
        """

        conversation = """
        Human: What are the top properties in San Francisco, CA?
        Assistant: I found 5 top properties in San Francisco with prices ranging from \$1.2M to \$3.5M.
        Human: How many properties did you find?
        """

        result = self.text_to_sql.check_if_follow_up_question(conversation)
        self.assertTrue(result["is_follow_up"])
        self.assertEqual(result["answer"],
                         "Based on the previous conversation, there are 5 properties in San Francisco.")

        # Test case where it's not a follow-up question
        mock_call_bedrock.return_value = """
        {
          "is_follow_up": false,
          "answer": null
        }
        """

        conversation = """
        Human: What are the top properties in San Francisco, CA?
        Assistant: I found 5 top properties in San Francisco with prices ranging from \$1.2M to \$3.5M.
        Human: What are the cheapest properties in Seattle?
        """

        result = self.text_to_sql.check_if_follow_up_question(conversation)
        self.assertFalse(result["is_follow_up"])
        self.assertIsNone(result["answer"])

        # Test case with malformed JSON response
        mock_call_bedrock.return_value = "This is not a valid JSON response"

        result = self.text_to_sql.check_if_follow_up_question(conversation)
        self.assertFalse(result["is_follow_up"])
        self.assertIsNone(result["answer"])
        self.logger.error.assert_called()  # Check if error was logged

if __name__ == '__main__':
    unittest.main()