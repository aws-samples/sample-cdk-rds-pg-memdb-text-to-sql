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
import os

import boto3
import psycopg
from psycopg import sql

secrets_client = boto3.client("secretsmanager")


def handler(event, context):
    print(event)
    request_type = event["RequestType"]
    if request_type == "Create":
        return on_create(event)
    if request_type == "Update":
        return on_update(event)
    if request_type == "Delete":
        return on_delete(event)
    raise Exception(f"Invalid request type: {request_type}")


def on_create(event):
    request_id = event["RequestId"]
    props = event["ResourceProperties"]
    print(f"create new resource with props {props}")

    # Get database credentials
    db_secret = secrets_client.get_secret_value(SecretId=os.environ["DB_SECRET_NAME"])
    db_secret_dict = json.loads(db_secret["SecretString"])

    read_only_secret = secrets_client.get_secret_value(SecretId=os.environ["READ_ONLY_SECRET_NAME"])
    read_only_secret_dict = json.loads(read_only_secret["SecretString"])

    # Connect to the database
    conn = psycopg.connect(host=db_secret_dict["host"], port=db_secret_dict["port"], dbname="postgres",
        user=db_secret_dict["username"], password=db_secret_dict["password"], )
    try:
        with conn.cursor() as cur:
            # Create a table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS us_housing_properties (
                    property_url TEXT,
                    property_id INTEGER PRIMARY KEY,
                    address TEXT,
                    street_name TEXT,
                    apartment TEXT,
                    city TEXT,
                    state TEXT,
                    latitude REAL,
                    longitude REAL,
                    postcode TEXT,
                    price REAL,
                    bedroom_number INTEGER,
                    bathroom_number INTEGER,
                    price_per_unit REAL,
                    living_space REAL,
                    land_space REAL,
                    land_space_unit TEXT,
                    broker_id INTEGER,
                    property_type TEXT,
                    property_status TEXT,
                    year_build INTEGER,
                    total_num_units INTEGER,
                    listing_age INTEGER,
                    RunDate TEXT,
                    agency_name TEXT,
                    agent_name TEXT,
                    agent_phone TEXT,
                    is_owned_by_zillow INTEGER
                )
              """)
            # Enable pg_vector
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute("""
                CREATE TABLE  IF NOT EXISTS embeddings (
                    id SERIAL PRIMARY KEY,
                    embedding VECTOR(1536),
                    database_name VARCHAR(255) NOT NULL,
                    schema_name VARCHAR(255) NOT NULL,
                    table_name VARCHAR(255) NOT NULL,
                    embedding_text TEXT NOT NULL,
                    embedding_hash VARCHAR(64) NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (database_name, schema_name, table_name, embedding_hash)
                )
            """)

            # Check if role exists
            cur.execute("""
            SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'readonly_user'
            """)
            role_exists = cur.fetchone() is not None

            if not role_exists:
                # Create role with parameterized password
                # semgrep seems to be flagging as a false positive
                create_role_query = sql.SQL("CREATE ROLE readonly_user WITH LOGIN PASSWORD {}").format(
                    sql.Literal(read_only_secret_dict["password"]))
                cur.execute(create_role_query) # nosemgrep
                # Grant permissions
                cur.execute("""
                GRANT CONNECT ON DATABASE postgres TO readonly_user;
                GRANT USAGE ON SCHEMA public TO readonly_user;
                GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_user;
                ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly_user;
                """)

        conn.commit()
        return {"PhysicalResourceId": request_id}
    except Exception as e:
        raise e
    finally:
        conn.close()


def on_update(event):
    physical_id = event["PhysicalResourceId"]
    props = event["ResourceProperties"]
    print(f"update resource {physical_id} with props {props}")
    return {"PhysicalResourceId": physical_id}


def on_delete(event):
    physical_id = event["PhysicalResourceId"]
    print(f"delete resource {physical_id}")
    return {"PhysicalResourceId": physical_id}
