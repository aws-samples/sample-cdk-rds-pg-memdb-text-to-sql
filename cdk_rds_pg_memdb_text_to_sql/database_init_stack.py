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
    aws_secretsmanager as sm,
    aws_iam as iam,
    custom_resources as cr,
    aws_rds as rds,
    aws_ec2 as ec2,
    aws_lambda as lambda_,
    aws_logs as logs,
    Stack,
    CfnOutput,
    CustomResource,
    Duration,
    BundlingOptions
)
from cdk_nag import NagSuppressions
from constructs import Construct


class DatabaseInitStack(Stack):

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
            os.path.dirname(os.path.abspath(__file__)), "..", "custom_resource"
        )

        # Create an IAM role for the DB Init Lambda function
        cr_lambda_role = iam.Role(
            self, "CrLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaVPCAccessExecutionRole")
            ]
        )
        cr_lambda_role.add_to_policy(iam.PolicyStatement(
            actions=["secretsmanager:GetSecretValue",
                     "secretsmanager:DescribeSecret", ],
            resources=[db_instance.secret.secret_arn, readonly_secret.secret_arn]
        ))
        NagSuppressions.add_resource_suppressions(cr_lambda_role, [
            {"id": "AwsSolutions-IAM4", "reason": "This is a managed policy for Lambda VPC execution.",
             "appliesTo": ["Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"]}
        ])

        init_function = lambda_.Function(
            self,
            "DBInitFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",
            role=cr_lambda_role,
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
            security_groups=[security_group],
            timeout=Duration.seconds(60),
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "DB_SECRET_NAME": db_instance.secret.secret_name,
                "READ_ONLY_SECRET_NAME": readonly_secret.secret_name,
                "DB_NAME": "postgres",
            },
        )
        NagSuppressions.add_stack_suppressions(
            self,
            [
                # Suppress IAM4 for LogRetention and Provider framework Lambda roles
                {
                    "id": "AwsSolutions-IAM4",
                    "reason": "Lambda log retention uses AWS managed policy for basic execution which is acceptable for this use case",
                    "appliesTo": [
                        "Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
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
        cr_provider_role = iam.Role(
            self, "CrProviderRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
            ]
        )
        cr_provider_role.add_to_policy(iam.PolicyStatement(
            actions=["lambda:InvokeFunction"],
            resources=[init_function.function_arn]
        ))
        immutable_cr_role = cr_provider_role.without_policy_updates()
        # Custom resource to trigger database initialization
        provider = cr.Provider(self, "db-provider", on_event_handler=init_function,
                               role=immutable_cr_role
                               )
        NagSuppressions.add_resource_suppressions(provider, [
            {"id": "AwsSolutions-L1",
             "reason": "Event handler is the latest Python version, 3.12"}
        ], True)
        CustomResource(self, "db-cr", service_token=provider.service_token)

        # Output the secret ARNs
        CfnOutput(self, "DBSecretArn", value=db_instance.secret.secret_name)
        CfnOutput(self, "ReadOnlySecretArn", value=readonly_secret.secret_name)
        # Add CDK Nag suppressions for Python 3.12
        NagSuppressions.add_resource_suppressions(init_function, [
            {"id": "AwsSolutions-L1", "reason": "Python 3.12 is the stable version tested for this solution"}
        ])