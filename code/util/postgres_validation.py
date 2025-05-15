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

import re

# List of PostgreSQL reserved words
# https://www.postgresql.org/docs/current/sql-keywords-appendix.html
# reserved, requires AS, reserved (can be function or type)
POSTGRES_RESERVED_WORDS = {
    "all", "analyse", "analyze", "and", "any", "array", "as", "asc", "asymmetric", "authorization", "binary", "both",
     "case", "cast", "check", "collate", "collation", "column", "concurrently", "constraint", "create", "cross",
     "current_catalog", "current_date", "current_role", "current_schema", "current_time", "current_timestamp",
     "current_user", "default", "deferrable", "desc", "distinct", "do", "else", "end", "except", "false", "fetch",
     "for", "foreign", "freeze", "from", "full", "grant", "group", "having", "ilike", "in", "initially", "inner",
     "intersect", "into", "is", "isnull", "join", "lateral", "leading", "left", "like", "limit", "localtime",
     "localtimestamp", "natural", "not", "notnull", "null", "offset", "on", "only", "or", "order", "outer", "overlaps",
     "placing", "primary", "references", "returning", "right", "select", "session_user", "similar", "some", "symmetric",
     "system_user", "table", "tablesample", "then", "to", "trailing", "true", "union", "unique", "user", "using",
     "variadic", "verbose", "when", "where", "window", "with"
}


def is_valid_postgres_identifier(name: str) -> bool:
    # Check basic pattern
    pattern = r"^(?!pg_)[a-zA-Z_][a-zA-Z0-9_$]*$"
    if not re.match(pattern, name):
        return False

    # Check length
    if len(name.encode("utf-8")) > 63:
        return False

    # Check if name is a reserved word (case-insensitive)
    if name.lower() in POSTGRES_RESERVED_WORDS:
        return False

    return True