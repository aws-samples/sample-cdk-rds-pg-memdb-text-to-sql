#!/usr/bin/env python3

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

import aws_cdk as cdk

from cdk_rds_pg_memdb_text_to_sql.app_stack import AppStack
from cdk_rds_pg_memdb_text_to_sql.database_init_stack import DatabaseInitStack
from cdk_rds_pg_memdb_text_to_sql.data_indexer_stack import DataIndexerStack
from cdk_nag import AwsSolutionsChecks

app = cdk.App()
env = cdk.Environment(region="us-west-2")

app_stack = AppStack(app, "AppStack", env=env)
db_init_stack = DatabaseInitStack(app, "DatabaseInitStack", db_instance=app_stack.rds_instance, vpc=app_stack.vpc,
                                  security_group=app_stack.security_group, readonly_secret=app_stack.readonly_secret, env=env)
data_indexer_stack = DataIndexerStack(app, "DataIndexerStack", db_instance=app_stack.rds_instance, vpc=app_stack.vpc,
                                      security_group=app_stack.security_group, readonly_secret=app_stack.readonly_secret,env=env)
cdk.Aspects.of(app).add(AwsSolutionsChecks(verbose=True))
app.synth()
