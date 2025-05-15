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

import json
import logging
from typing import List

import botocore.client

class EmbeddingService:
    """
    A service for generating embeddings using Amazon Bedrock.

    This class provides functionality to generate embeddings for given text inputs
    using the Amazon Titan embedding model through Bedrock.

    Attributes:
        logger (logging.Logger): Logger for logging debug and error messages.
        bedrock_client (botocore.client.BaseClient): Bedrock runtime client for making API calls.
    """

    def __init__(self, bedrock_client: botocore.client.BaseClient, logger: logging.Logger):
        """
        Initialize the EmbeddingService.

        Args:
            bedrock_client (botocore.client.BaseClient): Bedrock runtime client for making API calls.
            logger (logging.Logger): Logger for logging debug and error messages.
        """
        self.logger = logger
        self.bedrock_client = bedrock_client

    def get_embedding(self, text: str) -> List[float]:
        """Generate an embedding for the given text using Amazon Bedrock.

        This method sends a request to the Amazon Titan embedding model
        to generate an embedding for the provided text.

        Args:
            text (str): The text to generate an embedding for.

        Returns:
            List[float]: The generated embedding as a list of floats.

        Raises:
            Exception: If there is an error in generating the embedding.
        """
        try:
            self.logger.debug(f"Generating embedding for {text}")
            response = self.bedrock_client.invoke_model(
                body=json.dumps({"inputText": text}),
                contentType="application/json",
                accept="*/*",
                modelId="amazon.titan-embed-text-v1"
            )
            response_body = json.loads(response["body"].read())
            self.logger.debug(f"Embedding generated: {response_body['embedding']}")
            return response_body["embedding"]
        except Exception as e:
            self.logger.error(f"Error generating embedding: {e}")
            raise
