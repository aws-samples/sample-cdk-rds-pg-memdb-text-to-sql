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

import os

from aws_cdk import (
    aws_iam as iam,
    aws_rds as rds,
    aws_ec2 as ec2,
    aws_lambda as lambda_,
    aws_secretsmanager as sm,
    aws_logs as logs,
    Stack,
    Duration,
    BundlingOptions
)
from cdk_nag import NagSuppressions
from constructs import Construct


class DataIndexerStack(Stack):

    def __init__(
            self,
            scope: Construct,
            construct_id: str,
            db_instance: rds.IDatabaseInstance,
            vpc: ec2.IVpc,
            security_group: ec2.ISecurityGroup,
            readonly_secret: sm.ISecret,
            **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        asset_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "code"
        )
        indexer_role = iam.Role(self, "LambdaDataIndexer", assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"))
        # Use the Lambda VPC managed policy
        indexer_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaVPCAccessExecutionRole"))
        indexer_role.add_to_policy(iam.PolicyStatement(
            actions=["secretsmanager:GetSecretValue",
                     "secretsmanager:DescribeSecret"],
            resources=[db_instance.secret.secret_arn, readonly_secret.secret_arn]
        ))
        # Add Bedrock permissions for amazon.titan-embed-text-v1
        indexer_role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel"],
            resources=[
                f"arn:aws:bedrock:{self.region}::foundation-model/amazon.titan-embed-text-v1",
                f"arn:aws:bedrock:{self.region}::foundation-model/anthropic.claude-3-5-sonnet-20240620-v1:0"]
        ))
        func = lambda_.Function(
            self,
            "DataIndexerFunction",
            function_name="DataIndexerStack-DataIndexerFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="indexer_handler.lambda_handler",
            role=indexer_role,
            code=lambda_.Code.from_asset(
                asset_path,
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install --platform manylinux2014_x86_64 --target /asset-output --implementation cp " +
                        "--python-version 3.12 --only-binary=:all: --upgrade -r requirements.txt && cp -au . " +
                        "/asset-output",
                    ]
                ),
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            memory_size=2048,
            security_groups=[security_group],
            timeout=Duration.seconds(60),
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "INDEXER_SECRET_ID": db_instance.secret.secret_name,
                "RDS_HOST": db_instance.instance_endpoint.hostname,
                "DB_NAME": "postgres"
            },
        )
        NagSuppressions.add_stack_suppressions(
            self,
            [
                # Suppress IAM4 for LogRetention Lambda and VPC execution roles
                {
                    "id": "AwsSolutions-IAM4",
                    "reason": "Lambda log retention uses AWS managed policy for basic execution which is acceptable for this example.",
                    "appliesTo": [
                        "Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
                        "Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
                    ]
                },
                # Suppress IAM5 for LogRetention Lambda roles
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Lambda log retention requires these permissions to function correctly",
                    "appliesTo": [
                        "Resource::*"
                    ]
                }
        ])
        # Add CDK Nag suppressions for Python 3.12
        NagSuppressions.add_resource_suppressions(func, [
            {"id": "AwsSolutions-L1", "reason": "Python 3.12 is the stable version tested for this solution."}
        ])
