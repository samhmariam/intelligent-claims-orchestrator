from aws_cdk import (
    CfnParameter,
    Duration,
    Stack,
    aws_apigateway as apigateway,
    aws_cloudwatch as cloudwatch,
    aws_iam as iam,
    aws_lambda as lambda_,
)
from constructs import Construct

class CdkStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        namespace = "ICPA/Production"

        claims_ingested = cloudwatch.Metric(
            namespace=namespace,
            metric_name="ClaimsIngested",
            statistic="Sum",
            period=Duration.minutes(5),
        )
        claims_processing = cloudwatch.Metric(
            namespace=namespace,
            metric_name="ClaimsProcessing",
            statistic="Sum",
            period=Duration.minutes(5),
        )
        claims_approved = cloudwatch.Metric(
            namespace=namespace,
            metric_name="ClaimsApproved",
            statistic="Sum",
            period=Duration.minutes(5),
        )
        claims_denied = cloudwatch.Metric(
            namespace=namespace,
            metric_name="ClaimsDenied",
            statistic="Sum",
            period=Duration.minutes(5),
        )

        fraud_latency_p50 = cloudwatch.Metric(
            namespace=namespace,
            metric_name="FraudAgentLatency",
            statistic="p50",
            period=Duration.minutes(1),
            label="Fraud P50",
        )
        fraud_latency_p95 = cloudwatch.Metric(
            namespace=namespace,
            metric_name="FraudAgentLatency",
            statistic="p95",
            period=Duration.minutes(1),
            label="Fraud P95",
        )
        fraud_latency_p99 = cloudwatch.Metric(
            namespace=namespace,
            metric_name="FraudAgentLatency",
            statistic="p99",
            period=Duration.minutes(1),
            label="Fraud P99",
        )
        adj_latency_p50 = cloudwatch.Metric(
            namespace=namespace,
            metric_name="AdjudicationAgentLatency",
            statistic="p50",
            period=Duration.minutes(1),
            label="Adj P50",
        )
        adj_latency_p95 = cloudwatch.Metric(
            namespace=namespace,
            metric_name="AdjudicationAgentLatency",
            statistic="p95",
            period=Duration.minutes(1),
            label="Adj P95",
        )
        adj_latency_p99 = cloudwatch.Metric(
            namespace=namespace,
            metric_name="AdjudicationAgentLatency",
            statistic="p99",
            period=Duration.minutes(1),
            label="Adj P99",
        )

        error_types = ["TRANSIENT", "THROTTLE", "INVALID_INPUT", "ACCESS_DENIED", "INTERNAL"]
        error_metrics = [
            cloudwatch.Metric(
                namespace=namespace,
                metric_name="ErrorsByType",
                statistic="Sum",
                period=Duration.minutes(5),
                dimensions_map={"error_type": error_type},
                label=error_type,
            )
            for error_type in error_types
        ]

        services = ["Lambda", "Bedrock", "Textract", "S3", "StepFunctions", "DynamoDB"]
        cost_metrics = [
            cloudwatch.Metric(
                namespace=namespace,
                metric_name="CostByService",
                statistic="Sum",
                period=Duration.days(1),
                dimensions_map={"service": service},
                label=service,
            )
            for service in services
        ]

        hitl_queue_depth = cloudwatch.Metric(
            namespace=namespace,
            metric_name="HITLQueueDepth",
            statistic="Maximum",
            period=Duration.minutes(1),
        )

        phi_quarantine_count = cloudwatch.Metric(
            namespace=namespace,
            metric_name="PHIQuarantineCount",
            statistic="Sum",
            period=Duration.hours(1),
        )
        claims_processed = cloudwatch.Metric(
            namespace=namespace,
            metric_name="ClaimsProcessed",
            statistic="Sum",
            period=Duration.hours(1),
        )
        phi_quarantine_rate = cloudwatch.MathExpression(
            expression="(phi / processed) * 100",
            using_metrics={
                "phi": phi_quarantine_count,
                "processed": claims_processed,
            },
            label="PHI Quarantine Rate (%)",
        )

        dashboard = cloudwatch.Dashboard(
            self,
            "IcpAProductionOverview",
            dashboard_name="ICPA-Production-Overview",
        )

        dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Claim Flow Funnel",
                left=[claims_ingested, claims_processing, claims_approved, claims_denied],
                width=8,
                height=6,
                stacked=True,
            ),
            cloudwatch.GraphWidget(
                title="Agent Performance",
                left=[
                    fraud_latency_p50,
                    fraud_latency_p95,
                    fraud_latency_p99,
                    adj_latency_p50,
                    adj_latency_p95,
                    adj_latency_p99,
                ],
                left_annotations=[
                    cloudwatch.HorizontalAnnotation(
                        value=30000,
                        label="P95 target (30s)",
                        color=cloudwatch.Color.RED,
                    ),
                    cloudwatch.HorizontalAnnotation(
                        value=60000,
                        label="P99 max (60s)",
                        color=cloudwatch.Color.ORANGE,
                    ),
                ],
                width=8,
                height=6,
            ),
            cloudwatch.GraphWidget(
                title="Error Rates by Type",
                left=error_metrics,
                view=cloudwatch.GraphWidgetView.BAR,
                width=8,
                height=6,
            ),
        )

        dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Daily Cost by Service",
                left=cost_metrics,
                view=cloudwatch.GraphWidgetView.BAR,
                stacked=True,
                width=8,
                height=6,
            ),
            cloudwatch.GaugeWidget(
                title="HITL Queue Depth",
                metrics=[hitl_queue_depth],
                left_y_axis=cloudwatch.YAxisProps(min=0, max=100),
                width=8,
                height=6,
                annotations=[
                    cloudwatch.HorizontalAnnotation(
                        value=10,
                        label="Elevated",
                        color=cloudwatch.Color.ORANGE,
                    ),
                    cloudwatch.HorizontalAnnotation(
                        value=50,
                        label="Critical",
                        color=cloudwatch.Color.RED,
                    ),
                ],
            ),
            cloudwatch.SingleValueWidget(
                title="PHI Quarantine Rate",
                metrics=[phi_quarantine_rate],
                sparkline=True,
                width=8,
                height=6,
            ),
        )

        vpc_endpoint_id = CfnParameter(
            self,
            "HITLApiVpcEndpointId",
            description="VPC endpoint ID allowed to invoke the private HITL API.",
        )

        hitl_lambda = lambda_.Function.from_function_name(
            self,
            "HitlCallbackLambda",
            "ICPA-HITL-Callback-Lambda",
        )

        api_policy = iam.PolicyDocument(
            statements=[
                iam.PolicyStatement(
                    actions=["execute-api:Invoke"],
                    principals=[iam.AnyPrincipal()],
                    resources=["execute-api:/*/*/*"],
                    conditions={
                        "StringEquals": {"aws:SourceVpce": vpc_endpoint_id.value_as_string}
                    },
                    effect=iam.Effect.ALLOW,
                )
            ]
        )

        api = apigateway.RestApi(
            self,
            "HitlReviewApi",
            rest_api_name="ICPA-HITL-Review",
            description="Private HITL review API for claim approvals.",
            endpoint_configuration=apigateway.EndpointConfiguration(
                types=[apigateway.EndpointType.PRIVATE]
            ),
            policy=api_policy,
            deploy_options=apigateway.StageOptions(stage_name="prod"),
        )

        request_model = apigateway.Model(
            self,
            "HitlReviewRequestModel",
            rest_api=api,
            content_type="application/json",
            schema=apigateway.JsonSchema(
                schema=apigateway.JsonSchemaVersion.DRAFT4,
                title="HitlReviewRequest",
                type=apigateway.JsonSchemaType.OBJECT,
                required=["claim_id", "decision"],
                properties={
                    "claim_id": apigateway.JsonSchema(type=apigateway.JsonSchemaType.STRING),
                    "decision": apigateway.JsonSchema(
                        type=apigateway.JsonSchemaType.STRING,
                        enum=["APPROVE", "DENY", "FLAGGED"],
                    ),
                },
            ),
        )

        request_validator = api.add_request_validator(
            "HitlReviewRequestValidator",
            validate_request_body=True,
        )

        api_key = api.add_api_key(
            "HitlReviewApiKey",
            api_key_name="ICPA-HITL-Review-Key",
        )
        usage_plan = api.add_usage_plan(
            "HitlReviewUsagePlan",
            name="ICPA-HITL-Review-Plan",
            throttle=apigateway.ThrottleSettings(rate_limit=0.83, burst_limit=5),
        )
        usage_plan.add_api_key(api_key)
        usage_plan.add_api_stage(stage=api.deployment_stage)

        review = api.root.add_resource("review")
        approve = review.add_resource("approve")
        approve.add_method(
            "POST",
            apigateway.LambdaIntegration(hitl_lambda),
            authorization_type=apigateway.AuthorizationType.IAM,
            api_key_required=True,
            request_models={"application/json": request_model},
            request_validator=request_validator,
        )

        hitl_lambda.add_permission(
            "HitlApiInvokePermission",
            principal=iam.ServicePrincipal("apigateway.amazonaws.com"),
            action="lambda:InvokeFunction",
            source_arn=api.arn_for_execute_api(
                "POST", "/review/approve", api.deployment_stage.stage_name
            ),
        )
