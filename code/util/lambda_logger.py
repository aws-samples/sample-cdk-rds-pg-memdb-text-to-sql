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

import sys
import logging

def create_logger(lambda_function_name):
    """Creates a logger with a specific log format for use in Lambda functions.

    This function sets up a logger with the following characteristics:
    - No propagation to root logger
    - Custom formatter including timestamp, log level, Lambda function name, file path, and message
    - Logs directed to stdout for CloudWatch integration

    Args:
        lambda_function_name: The name of the Lambda function

    Returns:
        Configured logger instance
    """
    # Create a logger instance
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    # Prevent the logger from propagating messages to the root logger
    # This ensures our logs don't get duplicated
    logger.propagate = False

    # Remove any existing handlers to avoid duplicate logging
    for handler in logger.handlers:
        logger.removeHandler(handler)

    # Create a stream handler that writes to stdout
    # Lambda automatically captures stdout and sends it to CloudWatch Logs
    handler = logging.StreamHandler(sys.stdout)

    # Create a custom formatter
    # This format includes timestamp, log level, Lambda function name, file path, and the log message
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | " +
        f"{lambda_function_name} | %(pathname)s:%(lineno)d | %(message)s"
    )
    handler.setFormatter(formatter)

    # Add the configured handler to the logger
    logger.addHandler(handler)

    return logger