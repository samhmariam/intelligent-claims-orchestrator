from aws_cdk import (
    Stack,
    aws_apigateway as apigw,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_logs as logs,
)
import aws_cdk as cdk
from constructs import Construct


class ApiStack(Stack):
    """
    API Stack for Human-in-the-Loop (HITL) Dashboard
    
    Provides REST API endpoints for:
    - GET /claims/{external_id} - Retrieve claim data with presigned URLs
    - POST /claims/{external_id}/override - Process manual overrides
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        foundation_stack,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Import Powertools Layer from Foundation Stack
        powertools_layer = lambda_.LayerVersion.from_layer_version_arn(
            self, "PowertoolsLayerImport",
            layer_version_arn=foundation_stack.powertools_layer.layer_version_arn
        )

        # ==============================================================================
        # API Lambda Functions
        # ==============================================================================

        # 1. Get Claim Handler
        self.get_claim_lambda = lambda_.Function(
            self, "GetClaimLambda",
            runtime=lambda_.Runtime.PYTHON_3_13,
            handler="icpa.api.handlers.get_claim_handler",
            code=lambda_.Code.from_asset("../src"),
            timeout=cdk.Duration.seconds(30),
            memory_size=256,
            environment={
                "POWERTOOLS_SERVICE_NAME": "hitl-api",
                "CLAIMS_TABLE_NAME": foundation_stack.claims_table.table_name,
                "CLEAN_BUCKET_NAME": foundation_stack.clean_bucket.bucket_name,
            },
            tracing=lambda_.Tracing.ACTIVE,
            layers=[powertools_layer]
        )

        # Grant permissions for Get Claim Lambda
        foundation_stack.claims_table.grant_read_data(self.get_claim_lambda)
        foundation_stack.clean_bucket.grant_read(self.get_claim_lambda)
        
        # Grant ExternalIdIndex query permission
        self.get_claim_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["dynamodb:Query"],
            resources=[f"{foundation_stack.claims_table.table_arn}/index/ExternalIdIndex"]
        ))

        # 2. Manual Override Handler
        self.override_lambda = lambda_.Function(
            self, "ManualOverrideLambda",
            runtime=lambda_.Runtime.PYTHON_3_13,
            handler="icpa.api.handlers.manual_override_handler",
            code=lambda_.Code.from_asset("../src"),
            timeout=cdk.Duration.seconds(30),
            memory_size=256,
            environment={
                "POWERTOOLS_SERVICE_NAME": "hitl-override",
                "CLAIMS_TABLE_NAME": foundation_stack.claims_table.table_name,
                "CLEAN_BUCKET_NAME": foundation_stack.clean_bucket.bucket_name,
                "EVENT_BUS_NAME": "ICPA_EventBus",
            },
            tracing=lambda_.Tracing.ACTIVE,
            layers=[powertools_layer]
        )

        # Grant permissions for Override Lambda
        foundation_stack.claims_table.grant_read_write_data(self.override_lambda)
        
        # Grant ExternalIdIndex query permission
        self.override_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["dynamodb:Query"],
            resources=[f"{foundation_stack.claims_table.table_arn}/index/ExternalIdIndex"]
        ))
        
        # Grant EventBridge PutEvents permission
        self.override_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["events:PutEvents"],
            resources=[f"arn:aws:events:{self.region}:{self.account}:event-bus/ICPA_EventBus"]
        ))

        # ==============================================================================
        # API Gateway REST API
        # ==============================================================================

        # CloudWatch Log Group for API Gateway
        api_log_group = logs.LogGroup(
            self, "ApiGatewayLogs",
            log_group_name="/aws/apigateway/icpa-hitl-api",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=cdk.RemovalPolicy.DESTROY
        )

        # REST API
        self.api = apigw.RestApi(
            self, "HitlApi",
            rest_api_name="ICPA HITL Dashboard API",
            description="API for Human-in-the-Loop claim review and manual overrides",
            deploy_options=apigw.StageOptions(
                stage_name="prod",
                logging_level=apigw.MethodLoggingLevel.INFO,
                data_trace_enabled=True,
                access_log_destination=apigw.LogGroupLogDestination(api_log_group),
                access_log_format=apigw.AccessLogFormat.json_with_standard_fields(
                    caller=True,
                    http_method=True,
                    ip=True,
                    protocol=True,
                    request_time=True,
                    resource_path=True,
                    response_length=True,
                    status=True,
                    user=True,
                )
            ),
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["Content-Type", "Authorization"],
            )
        )

        # ==============================================================================
        # API Resources and Methods
        # ==============================================================================

        # /claims resource
        claims_resource = self.api.root.add_resource("claims")
        
        # /claims/{external_id} resource
        claim_resource = claims_resource.add_resource("{external_id}")

        # GET /claims/{external_id}
        claim_resource.add_method(
            "GET",
            apigw.LambdaIntegration(
                self.get_claim_lambda,
                proxy=True,
                integration_responses=[{
                    "statusCode": "200",
                    "responseParameters": {
                        "method.response.header.Access-Control-Allow-Origin": "'*'"
                    }
                }]
            ),
            method_responses=[{
                "statusCode": "200",
                "responseParameters": {
                    "method.response.header.Access-Control-Allow-Origin": True
                }
            }]
        )

        # POST /claims/{external_id}/override
        override_resource = claim_resource.add_resource("override")
        override_resource.add_method(
            "POST",
            apigw.LambdaIntegration(
                self.override_lambda,
                proxy=True,
                integration_responses=[{
                    "statusCode": "200",
                    "responseParameters": {
                        "method.response.header.Access-Control-Allow-Origin": "'*'"
                    }
                }]
            ),
            method_responses=[{
                "statusCode": "200",
                "responseParameters": {
                    "method.response.header.Access-Control-Allow-Origin": True
                }
            }]
        )

        # ==============================================================================
        # Outputs
        # ==============================================================================

        cdk.CfnOutput(
            self, "ApiEndpoint",
            value=self.api.url,
            description="HITL Dashboard API Endpoint",
            export_name="HitlApiEndpoint"
        )

        cdk.CfnOutput(
            self, "GetClaimUrl",
            value=f"{self.api.url}claims/{{external_id}}",
            description="GET Claim Endpoint (replace {{external_id}} with actual ID)"
        )

        cdk.CfnOutput(
            self, "OverrideUrl",
            value=f"{self.api.url}claims/{{external_id}}/override",
            description="POST Override Endpoint (replace {{external_id}} with actual ID)"
        )
