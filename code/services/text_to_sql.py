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
import ast
import re
from typing import Dict, Any, Union, List, Tuple

from psycopg.connection import Connection


class TextToSQL:
    """A class for converting natural language queries to SQL, executing them, and describing results.

    This class uses Amazon Bedrock to generate SQL from natural language text,
    executes the generated SQL queries, and then describes the results in natural language.

    Attributes:
        bedrock_client: Client for Bedrock runtime service.
        logger (logging.Logger): Logger object for logging messages.
        secret_client: Client for accessing AWS Secrets Manager.
    """

    def __init__(self,
                 secret_client,
                 bedrock_client,
                 log):
        """Initialize the TextToSQL class.

        Args:
            secret_client: Client for accessing secrets.
            bedrock_client: Client for Bedrock runtime service.
            log (logging.Logger): Logger object for logging messages.
        """
        self.bedrock_client = bedrock_client
        self.logger = log
        self.secret_client = secret_client

    @staticmethod
    def __generate_sql_prompt(query, schema):
        """Generate a prompt to create a SQL statement.

        Args:
            query: The natural language query to convert to SQL
            schema: The database schema

        Returns:
            A dictionary containing the prompt for the model
        """
        # LLM prompt, not SQL, hence nosec here
        sql_prompt_text = f"""
        Write a SQL statement for the following task, as a highly skilled, security-conscious database administrator would.

        ## Instructions:
        - Reject any question that asks for insert, update, and delete actions. Do NOT generate SQL statements for these.
        - Never query for all columns from a specific table; only request relevant columns based on the question.

        ## Security Requirements:
        - Use %s placeholders for parameters (compatible with psycopg3)
        - Never concatenate user input directly into the query string
        - Place all user inputs as parameters, including:
          * Search terms/filters
          * Column names for ORDER BY
          * LIMIT/OFFSET values
          * IN clause values
        - VERIFY that all tables and columns exist in the provided schema before referencing them
        - Use appropriate data types for parameters
        - Use schema-qualified table names (e.g., public.users instead of just users) ONLY if they appear that way in the schema

        ## Error Prevention Guidelines:
        - Always use NULLIF() when dividing to prevent division by zero errors
          * Example: price / NULLIF(quantity, 0) instead of price / quantity
        - For percentage or ratio calculations, use CASE statements to handle zeros:
          * Example: CASE WHEN total > 0 THEN part / total ELSE 0 END
        - When calculating averages or ratios, check if the denominator is zero or if the collection is empty
        - Use COALESCE() to provide default values for NULL results
        - Include a LIMIT clause to prevent excessive data retrieval
        - Handle case sensitivity appropriately:
          * For text comparisons, consider using UPPER() or LOWER() to normalize case
          * Example: LOWER(column_name) = LOWER(%s) instead of column_name = %s

        ## Aggregation and GROUP BY Best Practices:
        - Critical rule: Every column in the SELECT that is not inside an aggregate function MUST be in the GROUP BY clause exactly as it appears in the SELECT
        - When using CASE statements with GROUP BY, there are two valid approaches:
          * Approach 1: Include the exact CASE statement in both SELECT and GROUP BY clauses
          * Approach 2: Assign an alias to the CASE expression in a subquery/CTE, then GROUP BY the alias in the outer query
        - Never reference a raw column in a GROUP BY query's SELECT clause that isn't either:
          * Included directly in the GROUP BY clause, or
          * Wrapped in an aggregate function
        - For CASE statements that reference columns in a grouped query:
          * The entire CASE expression must be in the GROUP BY clause, or
          * The raw columns used within the CASE must all be in the GROUP BY clause
        - For comparison queries (e.g., comparing categories, regions, time periods):
          * Create categorical columns with CASE statements BEFORE aggregating using a subquery or CTE
          * Examples:
            ```sql
            -- Approach 1: Same CASE in both SELECT and GROUP BY
            SELECT 
                CASE 
                    WHEN condition1 THEN 'Category A' 
                    WHEN condition2 THEN 'Category B'
                    ELSE 'Other'
                END AS category,
                AVG(value) as average
            FROM table
            GROUP BY CASE 
                      WHEN condition1 THEN 'Category A' 
                      WHEN condition2 THEN 'Category B'
                      ELSE 'Other'
                    END

            -- Approach 2: Use a subquery/CTE for cleaner syntax
            WITH categorized AS (
              SELECT 
                  CASE 
                      WHEN condition1 THEN 'Category A' 
                      WHEN condition2 THEN 'Category B'
                      ELSE 'Other'
                  END AS category,
                  value
              FROM table
            )
            SELECT 
                category, 
                AVG(value) as average
            FROM categorized
            GROUP BY category
            ```

        ## PostgreSQL Function and Type Compatibility:
        - Use PostgreSQL-compatible numeric functions:
          * Instead of ROUND(), use: CAST(value AS NUMERIC(precision, scale))
          * Example: CAST(AVG(price) AS NUMERIC(10,2)) instead of ROUND(AVG(price), 2)
        - For division and mathematical operations, ensure proper type casting:
          * CAST expressions to NUMERIC before division: CAST(numerator AS NUMERIC) / CAST(denominator AS NUMERIC)
        - When calculating correlation or statistics:
          * Use CORR(x, y) for Pearson correlation coefficient
          * Use COVAR_POP(x, y) for population covariance
          * Use COVAR_SAMP(x, y) for sample covariance
        - For date calculations and age:
          * Use AGE(end_date, start_date) for interval between dates
          * Use DATE_PART('year', AGE(end_date, start_date)) for age in years
        - For text operations:
          * Use || for string concatenation: first_name || ' ' || last_name
          * Use ILIKE for case-insensitive pattern matching: column ILIKE '%pattern%'
        - For array handling:
          * Use array functions like ARRAY_AGG(), UNNEST(), ARRAY_TO_STRING(array, delimiter)
          * Array indexing is 1-based: my_array[1] for first element
        - For JSON operations:
          * Use -> for JSON object field access returning JSON: data->'field'
          * Use ->> for JSON object field access returning text: data->>'field'
          * Use jsonb_agg() to aggregate values as JSON array
        - For common table expressions (CTEs):
          * Use WITH queries for complex operations
          * Add RECURSIVE for hierarchical data: WITH RECURSIVE cte_name AS (...)
        - For window functions:
          * Specify frame clause explicitly: ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
          * Use DISTINCT ON (column) for getting the first row per group
        - Type conversion:
          * Use ::type shorthand for casting: amount::numeric instead of CAST(amount AS NUMERIC)
          * Use explicit type casts for date/time operations: date_column::date

        ## Performance Considerations:
        - Avoid CROSS JOINs for large tables
        - Prefer EXISTS over IN for subqueries when checking existence
        - Use appropriate JOIN types (INNER, LEFT, RIGHT) based on requirements
        - Consider using indexed columns in WHERE clauses and JOIN conditions
        - For pagination, use OFFSET with caution on large datasets
        - Be mindful of query performance, especially with large datasets

        ## Response Format:
        First: Carefully analyze the provided schema to identify all available tables and columns.
        Do not reference any tables or columns that don't exist in this schema.
        Second: Consider actual data formats and case sensitivity in the database values.

        Please respond with:
        1. <sql>Your SQL query here</sql>
        2. <params>[param1, param2, ...]</params>
        3. <validation>Brief validation that confirms the placeholders match parameters and all tables/columns exist</validation>

        Here is the task:
        <task>
        You are a security-focused SQL expert. A database in PostgreSQL was created with the following tables and columns:
        {schema}

        Write a parameterized SQL query using %s placeholders (for psycopg3) that returns the best results based on the following user input:
        {query}

        Double check your work to ensure:
        1. EVERY table and column you reference EXISTS in the schema above
        2. The number of %s placeholders EXACTLY MATCHES the number of parameters you provide
        3. No SQL injection vulnerabilities
        4. No division by zero errors
        5. Case sensitivity in string comparisons is properly handled (use UPPER or LOWER functions when appropriate)
        </task>
        """  # nosec

        return {"type": "text", "text": sql_prompt_text}

    @staticmethod
    def __generate_text_prompt(query, schema, results):
        """Generate a prompt to describe SQL query results in natural language.

        Args:
            query: The original SQL query
            schema: The database schema
            results: The results of the SQL query

        Returns:
            A dictionary containing the prompt for the AI
        """
        return {"type": "text", "text": f"""
               Human: You are a very skilled database administrator.
               The below rows were returned for the SQL query that follows:
               {str(results)}
               {str(query)}
               The schema for the database is as follows: {schema}
               Describe the results ONLY in natural language.
               DO NOT describe the query, database schema, or any technical aspects of the underlying SQL database.
               Assistant:
               """}

    def __call_bedrock(self, prompt: Dict[str, Any]) -> str:
        """Call the Bedrock service with a given prompt.

        Args:
            prompt (Dict[str, Any]): The prompt to send to Bedrock.

        Returns:
            str: The text content of the response.
        """
        body = {"messages": [{"role": "user", "content": [prompt]}], "max_tokens": 2048, "top_k": 250, "top_p": 1,
                "stop_sequences": ["\\n\\nHuman:"], "anthropic_version": "bedrock-2023-05-31"}
        response = self.bedrock_client.invoke_model(
            body=json.dumps(body),
            modelId="anthropic.claude-3-5-sonnet-20240620-v1:0",
            accept="application/json",
            contentType="application/json",
        )
        body = response["body"].read().decode("utf-8")
        text_content = json.loads(body)["content"][0]["text"]
        return text_content

    def check_if_follow_up_question(self, full_prompt: str) -> Dict[str, Any]:
        """Check if this is a follow-up question that can be answered directly.

        Args:
            full_prompt (str): The full conversation history with the current question.

        Returns:
            Dict[str, Any]: Dictionary with is_follow_up flag and answer if applicable.
        """
        prompt = {"type": "text", "text": f"""
            Human: You are reviewing a conversation to determine if the latest question is a follow-up that can be answered directly from the conversation context without needing to query a database. Analyze carefully:

            {full_prompt}

            Your task:
            1. Determine if the latest question is a follow-up that can be answered directly using information already provided in the conversation.
            2. If it IS a follow-up that can be answered directly, provide the answer based on the conversation context.
            3. If it is NOT a follow-up OR requires new database information, clearly state that a database query is needed.

            Respond in JSON format:
            ```
            {{
              "is_follow_up": true/false,
              "answer": "Your answer if it's a follow-up that can be answered directly, otherwise null"
            }}
            ```
            Assistant:
        """}

        response = self.__call_bedrock(prompt)

        # Extract JSON from response
        try:
            # Find JSON between triple backticks if present
            json_match = re.search(r'```(?:json)?\s*({\s*"is_follow_up".*?})\s*```', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Try to extract JSON without backticks
                json_match = re.search(r'({[\s\S]*?"is_follow_up"[\s\S]*?})', response)
                json_str = json_match.group(1) if json_match else response

            result = json.loads(json_str)
            return result
        except Exception as e:
            self.logger.error(f"Error parsing follow-up check response: {e}")
            return {"is_follow_up": False, "answer": None}

    def get_sql_from_bedrock(self, query: str, schema: str) -> Union[Tuple[str, List], Dict[str, Any]]:
        """Generate SQL from a natural language query using Bedrock.

        Args:
            query (str): The natural language query.
            schema (str): The database schema.

        Returns:
            Union[Tuple[str, List], Dict[str, Any]]: The generated SQL statement and parameters or an error response dictionary.

        Raises:
            Exception: If there is an error generating SQL from the query.
        """
        # Generate the prompt for Bedrock
        sql_prompt = self.__generate_sql_prompt(query, schema)
        self.logger.debug(sql_prompt)

        # Call Bedrock to generate SQL
        text_content = self.__call_bedrock(sql_prompt)

        # Extract SQL from the AI's response
        sql_regex = re.compile(r"<sql>(.*?)</sql>", re.DOTALL)
        sql_statements = sql_regex.findall(text_content)

        # Extract parameters
        params_regex = re.compile(r"<params>(.*?)</params>", re.DOTALL)
        params_match = params_regex.findall(text_content)

        self.logger.debug(sql_statements)
        self.logger.debug(params_match)

        # Check if SQL was successfully generated
        if not sql_statements:
            return {"statusCode": 500,
                    "body": {"response": "Unable to generate SQL for the provided prompt, please try again."},
                    "headers": {"Content-Type": "application/json"}}

        # Parse parameters if available, otherwise return empty list
        params = []
        if params_match:
            try:
                # Safely evaluate the parameter list (should be a Python list literal)
                params = ast.literal_eval(params_match[0])
            except Exception as e:
                self.logger.error(f"Error parsing parameters: {e}")
                self.logger.error(f"Raw parameters string: {params_match[0]}")
                # Continue with empty params rather than failing

        # Return the SQL and parameters
        return sql_statements[0], params

    def execute_sql(self, conn: Connection, sql_data) -> Tuple[List[Tuple], List[str]]:
        """Execute SQL statements on a given database connection.

        Args:
            conn (connection): The database connection.
            sql_data: Either a SQL string or a tuple of (SQL, parameters)

        Returns:
            Tuple[List[Tuple], List[str]]: The results of the SQL execution and column names.

        Raises:
            Exception: If there is an error executing the SQL statements.
        """
        sql = sql_data
        params = []

        # Check if we have parameters
        if isinstance(sql_data, tuple) and len(sql_data) == 2:
            sql, params = sql_data

        self.logger.info(f"Executing SQL: {sql}")
        self.logger.info(f"With parameters: {params}")

        cursor = conn.cursor()
        cursor.execute(sql, params)

        # Fetch results if available
        results = []
        column_names = []

        if cursor.description:  # Check if the query returned any rows
            results = cursor.fetchall()
            column_names = [desc[0] for desc in cursor.description]

        self.logger.info(f"Results: {results}")
        self.logger.info(f"Column names: {column_names}")
        return results, column_names

    def describe_results_from_query(self, sql_statements: str, results_tuple: Tuple[List[Tuple], List[str]],
                                    schema: str) -> Dict[str, Any]:
        """Generate a natural language description of SQL query results.

        Args:
            sql_statements (str): The SQL statements that were executed.
            results_tuple (Tuple[List[Tuple], List[str]]): The results of the SQL query and column names.
            schema (str): The database schema.

        Returns:
            Dict[str, Any]: A dictionary containing the response, query, results, column names, and headers.

        Raises:
            Exception: If there is an error generating the description of the query results.
        """
        results, column_names = results_tuple
        text_prompt = self.__generate_text_prompt(sql_statements, schema, results)
        text_content = self.__call_bedrock(text_prompt)
        return {"statusCode": 200,
                "body": {"response": text_content,
                         "query": sql_statements,
                         "query_results": results,
                         "column_names": column_names,
                         "cache_id": None},
                "headers": {"Content-Type": "application/json"}}
