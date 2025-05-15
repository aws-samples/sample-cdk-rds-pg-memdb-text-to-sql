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

import psycopg

class PostgreSQLService:
    """A service for managing PostgreSQL database connections.

    This class provides functionality to connect to a PostgreSQL database,
    retrieve database secrets from AWS Secrets Manager, and manage database connections.

    Attributes:
        logger (logging.Logger): Logger for logging messages.
        secret_client: AWS Secrets Manager client for retrieving database secrets.
        db_host (str): Database host address.
        db_name (str): Database name.
        db_secret (Dict[str, str]): Database connection secrets (initialized as None).
    """

    def __init__(self,
                 secret_client,
                 db_host, db_name,
                 log
                 ):
        """Initialize the PostgreSQLService.

        Args:
            secret_client: AWS Secrets Manager client.
            db_host (str): Database host address.
            db_name (str): Database name.
            log (logging.Logger): Logger object for logging messages.
        """
        self.logger = log
        self.secret_client = secret_client
        self.db_host = db_host
        self.db_name = db_name
        self.db_secret = None

    def set_secret(self, secret_id: str) -> None:
        """Retrieve the database secret from AWS Secrets Manager.

        Args:
            secret_id (str): The ID of the secret in AWS Secrets Manager.

        Raises:
            Exception: If there is an error retrieving the secret.
        """
        try:
            get_secret_value_response = self.secret_client.get_secret_value(SecretId=secret_id)
            self.db_secret = json.loads(get_secret_value_response["SecretString"])
        except Exception as e:
            self.logger.error(f"Error retrieving secret: {e}")
            raise e

    def connect_to_db(self) -> psycopg.Connection:
        """Establish a connection to the PostgreSQL database.

        Returns:
            psycopg.Connection: A psycopg database connection object.

        Raises:
            Exception: If the database secret is not available or if the connection fails.
        """
        try:
            if not self.db_secret:
                raise Exception("Database secret not available")
            
            conn = psycopg.connect(
                host=self.db_host,
                dbname=self.db_name,
                user=self.db_secret["username"],
                password=self.db_secret["password"]
            )
            
            # Configure connection to handle decimals as floats
            conn.execute("SET extra_float_digits = 3")
            
            return conn
        except Exception as e:
            self.logger.error(f"Error connecting to database or retrieving secret: {e}")
            raise e