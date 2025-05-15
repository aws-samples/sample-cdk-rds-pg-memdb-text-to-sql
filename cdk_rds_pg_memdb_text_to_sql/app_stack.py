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
    aws_ec2 as ec2,
    aws_rds as rds,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_apigateway as apigw,
    aws_memorydb as memorydb,
    aws_secretsmanager as sm,
    aws_logs as logs,
    Stack, CfnOutput, Duration, CfnParameter, BundlingOptions, RemovalPolicy
)
from cdk_nag import NagSuppressions
from constructs import Construct


class AppStack(Stack):
    vpc: ec2.IVpc
    subnet: ec2.ISubnet
    security_group: ec2.ISecurityGroup
    rds_instance: rds.IDatabaseInstance
    readonly_secret: sm.ISecret

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        # CfnInput for S3 Bucket name
        s3_bucket_name = CfnParameter(
            self, "S3BucketName",
            type="String",
            default="your-bucket-name",
            description="Name of the S3 bucket to be used for the application"
        )
        # Create a VPC
        self.vpc = ec2.Vpc(self, "VPC", max_azs=2, gateway_endpoints={
            "S3": ec2.GatewayVpcEndpointOptions(
                service=ec2.GatewayVpcEndpointAwsService.S3
            )
        })
        self.vpc.add_flow_log("FlowLog")
        self.subnet = self.vpc.private_subnets[0]

        # Create a PostgreSQL DB Instance
        rds_instance = rds.DatabaseInstance(self, "AppDatabaseInstance",
                                            engine=rds.DatabaseInstanceEngine.postgres(
                                                version=rds.PostgresEngineVersion.VER_16),
                                            instance_type=ec2.InstanceType.of(ec2.InstanceClass.BURSTABLE3,
                                                                              ec2.InstanceSize.SMALL),
                                            vpc=self.vpc,
                                            storage_encrypted=True,
                                            vpc_subnets=ec2.SubnetSelection(
                                                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
                                            ),
                                            )
        rds_instance.add_rotation_single_user()
        rds_instance.apply_removal_policy(RemovalPolicy.DESTROY)
        self.rds_instance = rds_instance

        NagSuppressions.add_resource_suppressions(self.rds_instance, [
            {"id": "AwsSolutions-RDS3", "reason": "Multi-AZ is not required for this example"}
        ])
        NagSuppressions.add_resource_suppressions(self.rds_instance, [
            {"id": "AwsSolutions-RDS10", "reason": "Deletion protection is not required for this example"}
        ])
        NagSuppressions.add_resource_suppressions(self.rds_instance, [
            {"id": "AwsSolutions-RDS11", "reason": "Default port is sufficient for this example"}
        ])

        # Create an IAM role for the Lambda function
        lambda_role = iam.Role(
            self, "AppLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaVPCAccessExecutionRole")
            ]
        )
        NagSuppressions.add_resource_suppressions(lambda_role, [
            {"id": "AwsSolutions-IAM4", "reason": "This is a managed policy for Lambda VPC execution.",
             "appliesTo": ["Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"]}
        ])
        # Create Secrets Manager secret for read-only user
        self.readonly_secret = sm.Secret(
            self,
            "ReadOnlyUserSecret",
            generate_secret_string=sm.SecretStringGenerator(
                secret_string_template='{"username": "readonly_user"}',
                generate_string_key="password",
            ),
        )
        NagSuppressions.add_resource_suppressions(self.readonly_secret, [
            {"id": "AwsSolutions-SMG4",
             "reason": "This read-only user is manually provisioned in the database."}
        ])

        lambda_role.attach_inline_policy(
            iam.Policy(
                self, "LambdaSecretsManagerPolicy",
                statements=[
                    iam.PolicyStatement(
                        effect=iam.Effect.ALLOW,
                        actions=["secretsmanager:GetSecretValue"],
                        resources=[self.readonly_secret.secret_arn]
                    )
                ]
            )
        )
        # Add Bedrock InvokeModel permissions for Anthropic Claude to Lambda role
        lambda_role.attach_inline_policy(
            iam.Policy(
                self, "LambdaBedrockPolicy",
                statements=[
                    iam.PolicyStatement(
                        actions=["bedrock:InvokeModel"],
                        resources=[
                            f"arn:aws:bedrock:{self.region}::foundation-model/amazon.titan-embed-text-v1",
                            f"arn:aws:bedrock:{self.region}::foundation-model/anthropic.claude-3-5-sonnet-20240620-v1:0"]
                    )]
            )
        )

        self.rds_instance.secret.grant_read(lambda_role)

        database_sg = ec2.SecurityGroup(
            self, "DatabaseSecurityGroup",
            vpc=self.vpc
        )
        # RDS PostgreSQL Database
        database_sg.add_ingress_rule(
            database_sg,
            ec2.Port.tcp(5432),
            "Allow PostgreSQL traffic within the security group"
        )
        # MemoryDB
        database_sg.add_ingress_rule(
            database_sg,
            ec2.Port.tcp(6379),
            "Allow MemoryDB for Valkey traffic within the security group"
        )

        # Subnet group for MemoryDB
        subnet_group = memorydb.CfnSubnetGroup(
            self, "MemoryDBSubnetGroup",
            subnet_ids=self.vpc.select_subnets(subnet_type=ec2.SubnetType.PRIVATE_WITH_NAT).subnet_ids,
            subnet_group_name="memorydb-subnet-group"
        )
        # MemoryDB cluster
        # Vector search for MemoryDB is currently limited to a single shard
        memorydb_cluster = memorydb.CfnCluster(
            self, "TextToSQLMemoryDBCluster",
            cluster_name="text-to-sql-memorydb-cluster",
            node_type="db.t4g.small",
            num_shards=1,
            num_replicas_per_shard=0,
            tls_enabled=True,
            subnet_group_name=subnet_group.subnet_group_name,
            security_group_ids=[database_sg.security_group_id],
            engine_version="7.2",
            engine="valkey",
            acl_name="open-access",
            data_tiering="false",
            parameter_group_name="default.memorydb-valkey7.search",
        )
        memorydb_cluster.add_dependency(subnet_group)

        asset_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "code"
        )
        function = lambda_.Function(
            self, "TextToSQLFunction",
            function_name="AppStack-TextToSQLFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="prompt_handler.lambda_handler",
            code=lambda_.Code.from_asset(
                asset_path,
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_12.bundling_image,
                    platform="linux/amd64",
                    command=[
                        "bash",
                        "-c",
                        "pip install --platform manylinux2014_x86_64 --target /asset-output --implementation cp " +
                        "--python-version 3.12 --only-binary=:all: --upgrade -r requirements.txt && cp -au . " +
                        "/asset-output",
                    ]
                )
            ),
            role=lambda_role,
            timeout=Duration.seconds(60),
            vpc=self.vpc,
            security_groups=[database_sg],
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            memory_size=3072,
            environment={
                "SECRET_NAME": self.readonly_secret.secret_name,
                "RDS_HOST": self.rds_instance.instance_endpoint.hostname,
                "MEMDB_CACHE_ENDPOINT": memorydb_cluster.attr_cluster_endpoint_address
            },
            log_retention=logs.RetentionDays.ONE_WEEK
        )
        NagSuppressions.add_stack_suppressions(
            self,
            [
                # Suppress IAM4 for LogRetention Lambda roles
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
        self.security_group = database_sg
        self.rds_instance.connections.allow_default_port_from(database_sg)

        # Create a bastion host EC2 instance
        bastion_host = ec2.BastionHostLinux(
            self, "BastionHostTextToSQL",
            vpc=self.vpc,
            subnet_selection=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PUBLIC
            ),
            instance_name="BastionHostTextToSQL",
            instance_type=ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.NANO),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            require_imdsv2=True,
            block_devices=[
                ec2.BlockDevice(device_name="/dev/xvda", volume=ec2.BlockDeviceVolume.ebs(10, encrypted=True))]
        )
        NagSuppressions.add_resource_suppressions(bastion_host, [
            {"id": "AwsSolutions-IAM5",
             "reason": "This is a bastion host instance with defaults for SSM and EC2 messages."}
        ], True)
        NagSuppressions.add_resource_suppressions(bastion_host, [
            {"id": "AwsSolutions-EC28", "reason": "This is a bastion host instance, ASG not required."}
        ], True)
        NagSuppressions.add_resource_suppressions(bastion_host, [
            {"id": "AwsSolutions-EC29",
             "reason": "This is a bastion host instance, termination protection not required."}
        ], True)

        # Add S3 permissions to the inline policy attached to the bastion host instance role
        bastion_s3_policy = iam.Policy(
            self, "BastionS3Policy",
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
                    resources=[
                        f"arn:aws:s3:::{s3_bucket_name.value_as_string}/*",
                        f"arn:aws:s3:::{s3_bucket_name.value_as_string}"
                    ]
                )
            ]
        )
        bastion_host.role.attach_inline_policy(bastion_s3_policy)
        NagSuppressions.add_resource_suppressions(bastion_s3_policy, [
            {"id": "AwsSolutions-IAM5",
             "reason": "Provides users flexibility for file transfers on bastion host for specified bucket.",
             "appliesTo": ["Resource::arn:aws:s3:::<S3BucketName>/*"]}
        ])

        bastion_host.role.attach_inline_policy(
            iam.Policy(
                self, "BastionSecretsManagerPolicy",
                statements=[
                    iam.PolicyStatement(
                        effect=iam.Effect.ALLOW,
                        actions=["secretsmanager:GetSecretValue"],
                        resources=[self.rds_instance.secret.secret_arn]
                    )
                ]
            )
        )

        # Grant the bastion host access to the Database
        self.rds_instance.connections.allow_default_port_from(bastion_host)

        api = apigw.LambdaRestApi(
            self,
            "Text2SqlApi",
            handler=function,
            proxy=False,
            integration_options=apigw.LambdaIntegrationOptions(proxy=False),
            api_key_source_type=apigw.ApiKeySourceType.HEADER,
            default_method_options=apigw.MethodOptions(
                api_key_required=True
            ),
            endpoint_types=[apigw.EndpointType.REGIONAL]
        )
        # Create a request validator
        request_validator = api.add_request_validator("RequestValidator",
                                                      validate_request_body=True,
                                                      validate_request_parameters=True
                                                      )
        query_model = api.add_model("JsonQueryModel", schema=apigw.JsonSchema(
            type=apigw.JsonSchemaType.OBJECT,
            properties={
                "query": apigw.JsonSchema(
                    type=apigw.JsonSchemaType.STRING
                ), "conversation_context": apigw.JsonSchema(
                    type=apigw.JsonSchemaType.ARRAY,
                    items=apigw.JsonSchema(
                        type=apigw.JsonSchemaType.OBJECT,
                        properties={
                            "role": apigw.JsonSchema(type=apigw.JsonSchemaType.STRING),
                            "content": apigw.JsonSchema(type=apigw.JsonSchemaType.STRING)
                        }
                    )
                )
            },
            required=["query"]
        ))
        # Define the '/text-to-sql' resource with a POST method
        text_to_sql_resource = api.root.add_resource("text-to-sql")
        integration_responses = apigw.LambdaIntegration(function, proxy=False,
                                                        integration_responses=[
                                                            apigw.IntegrationResponse(status_code="200"),
                                                            apigw.IntegrationResponse(status_code="500")
                                                        ])
        text_to_sql_resource.add_method("POST",
                                        request_models={
                                            "application/json": query_model
                                        },
                                        integration=integration_responses,
                                        method_responses=[
                                            apigw.MethodResponse(status_code="200"),
                                            apigw.MethodResponse(status_code="500")
                                        ],
                                        request_validator=request_validator)
        # Add an API token
        api_key = api.add_api_key("Text2SqlApiKey")

        # Create a usage plan and associate the API key for the Gateway
        usage_plan = api.add_usage_plan("Text2SqlUsagePlan",
                                        throttle=apigw.ThrottleSettings(
                                            burst_limit=100,
                                            rate_limit=50
                                        ))
        usage_plan.add_api_stage(stage=api.deployment_stage)
        usage_plan.add_api_key(api_key)

        NagSuppressions.add_resource_suppressions(api, [
            {"id": "AwsSolutions-APIG1", "reason": "Logging is not required for this example."}
        ], True)

        NagSuppressions.add_resource_suppressions(api, [
            {"id": "AwsSolutions-APIG6", "reason": "Logging is not required for this example."}
        ], True)
        NagSuppressions.add_resource_suppressions(api, [
            {"id": "AwsSolutions-APIG4", "reason": "API Key is sufficient for this example."}
        ], True)
        NagSuppressions.add_resource_suppressions(api, [
            {"id": "AwsSolutions-COG4", "reason": "Cognito authorization is not required for this example."}
        ], True)

        # Output
        CfnOutput(self, "ApiEndpoint", value=api.url,
                  description="API Gateway endpoint URL for the text-to-sql function")
        # Add a CloudFormation output with the CLI command to retrieve the API key value
        CfnOutput(self, "GetApiKeyCommand",
                  value=f"aws apigateway get-api-key --api-key {api_key.key_id} --include-value --query 'value' --output text",
                  description="AWS CLI command to retrieve the API key value")
        CfnOutput(self, "BastionHostInstanceId", value=bastion_host.instance_id,
                  description="Bastion host instance ID for the environment")
        # Add CDK Nag suppressions for Python 3.12
        NagSuppressions.add_resource_suppressions(function, [
            {"id": "AwsSolutions-L1", "reason": "Python 3.12 is the stable version tested for this solution"}
        ])