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
from unittest.mock import MagicMock

from code.services.indexer import DataIndexerService

FIXTURE = fixture = [(
    "public", "us_housing_properties", "property_url", "text", None, None, None, "YES", None, None, None, None,
    None, None), (
    "public", "us_housing_properties", "property_id", "integer", None, 32, 0, "NO", None, None, None, None,
    None, None), (
    "public", "us_housing_properties", "address", "text", None, None, None, "YES", None, None, None, None, None,
    None), (
    "public", "us_housing_properties", "street_name", "text", None, None, None, "YES", None, None, None, None,
    None, None), (
    "public", "us_housing_properties", "apartment", "text", None, None, None, "YES", None, None, None, None,
    None, None), (
    "public", "us_housing_properties", "city", "text", None, None, None, "YES", None, None, None, None, None,
    None), (
    "public", "us_housing_properties", "state", "text", None, None, None, "YES", None, None, None, None, None,
    None), (
    "public", "us_housing_properties", "latitude", "real", None, 24, None, "YES", None, None, None, None, None,
    None), (
    "public", "us_housing_properties", "longitude", "real", None, 24, None, "YES", None, None, None, None, None,
    None), (
    "public", "us_housing_properties", "postcode", "text", None, None, None, "YES", None, None, None, None,
    None, None), (
    "public", "us_housing_properties", "price", "real", None, 24, None, "YES", None, None, None, None, None,
    None), (
    "public", "us_housing_properties", "bedroom_number", "integer", None, 32, 0, "YES", None, None, None, None,
    None, None), (
    "public", "us_housing_properties", "bathroom_number", "integer", None, 32, 0, "YES", None, None, None, None,
    None, None), (
    "public", "us_housing_properties", "price_per_unit", "real", None, 24, None, "YES", None, None, None, None,
    None, None), (
    "public", "us_housing_properties", "living_space", "real", None, 24, None, "YES", None, None, None, None,
    None, None), (
    "public", "us_housing_properties", "land_space", "real", None, 24, None, "YES", None, None, None, None,
    None, None), (
    "public", "us_housing_properties", "land_space_unit", "text", None, None, None, "YES", None, None, None,
    None, None, None), (
    "public", "us_housing_properties", "broker_id", "integer", None, 32, 0, "YES", None, None, None, None, None,
    None), (
    "public", "us_housing_properties", "property_type", "text", None, None, None, "YES", None, None, None, None,
    None, None), (
    "public", "us_housing_properties", "property_status", "text", None, None, None, "YES", None, None, None,
    None, None, None), (
    "public", "us_housing_properties", "year_build", "integer", None, 32, 0, "YES", None, None, None, None,
    None, None), (
    "public", "us_housing_properties", "total_num_units", "integer", None, 32, 0, "YES", None, None, None, None,
    None, None), (
    "public", "us_housing_properties", "listing_age", "integer", None, 32, 0, "YES", None, None, None, None,
    None, None), (
    "public", "us_housing_properties", "rundate", "text", None, None, None, "YES", None, None, None, None, None,
    None), (
    "public", "us_housing_properties", "agency_name", "text", None, None, None, "YES", None, None, None, None,
    None, None), (
    "public", "us_housing_properties", "agent_name", "text", None, None, None, "YES", None, None, None, None,
    None, None), (
    "public", "us_housing_properties", "agent_phone", "text", None, None, None, "YES", None, None, None, None,
    None, None), (
    "public", "us_housing_properties", "is_owned_by_zillow", "integer", None, 32, 0, "YES", None, None, None,
    None, None, None)]


class TestIndexerService(unittest.TestCase):
    def setUp(self):
        self.embedding_service = MagicMock()
        self.logger = MagicMock()
        self.mock_conn = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_conn.cursor.return_value.__enter__.return_value = self.mock_cursor
        self.indexer_service = DataIndexerService(self.embedding_service, self.logger)

        # Mock sample data for testing
        self.sample_data = [
            {'property_id': 1, 'address': '123 Main St', 'price': 500000},
            {'property_id': 2, 'address': '456 Oak Ave', 'price': 750000},
            {'property_id': 3, 'address': '789 Pine Rd', 'price': 600000}
        ]
        self.mock_cursor.description = [
            ('property_id', None, None, None, None, None, None),
            ('address', None, None, None, None, None, None),
            ('price', None, None, None, None, None, None)
        ]
        self.mock_cursor.fetchall.return_value = [
            (1, '123 Main St', 500000),
            (2, '456 Oak Ave', 750000),
            (3, '789 Pine Rd', 600000)
        ]

    def test_create_embedding_string(self):
        self.indexer_service.db_name = "postgres"
        result = self.indexer_service.create_embedding_string(FIXTURE)
        expected_output = [{"database": "postgres",
                            "embedding_hash": "144ca8245b29c39cd6c532fe09d60a5dfe8c8d83bd25b1511e8775bfb1be4763",
                            "embedding_text": "Table: us_housing_properties (Schema: public)\n"
                                              "Columns:\n"
                                              "- property_url (text, NULL)\n"
                                              "- property_id (integer, NOT NULL)\n"
                                              "- address (text, NULL)\n"
                                              "- street_name (text, NULL)\n"
                                              "- apartment (text, NULL)\n"
                                              "- city (text, NULL)\n"
                                              "- state (text, NULL)\n"
                                              "- latitude (real(24), NULL)\n"
                                              "- longitude (real(24), NULL)\n"
                                              "- postcode (text, NULL)\n"
                                              "- price (real(24), NULL)\n"
                                              "- bedroom_number (integer, NULL)\n"
                                              "- bathroom_number (integer, NULL)\n"
                                              "- price_per_unit (real(24), NULL)\n"
                                              "- living_space (real(24), NULL)\n"
                                              "- land_space (real(24), NULL)\n"
                                              "- land_space_unit (text, NULL)\n"
                                              "- broker_id (integer, NULL)\n"
                                              "- property_type (text, NULL)\n"
                                              "- property_status (text, NULL)\n"
                                              "- year_build (integer, NULL)\n"
                                              "- total_num_units (integer, NULL)\n"
                                              "- listing_age (integer, NULL)\n"
                                              "- rundate (text, NULL)\n"
                                              "- agency_name (text, NULL)\n"
                                              "- agent_name (text, NULL)\n"
                                              "- agent_phone (text, NULL)\n"
                                              "- is_owned_by_zillow (integer, NULL)\n",
                            "schema": "public",
                            "table": "us_housing_properties"}]

        self.assertEqual(expected_output, result)


if __name__ == "__main__":
    unittest.main()
