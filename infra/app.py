#!/usr/bin/env python3
import os
import aws_cdk as cdk
from stacks.foundation_stack import FoundationStack
from stacks.api_stack import ApiStack

app = cdk.App()

foundation_stack = FoundationStack(app, "ICPA-FoundationStack",
    # If you don't specify 'env', this stack will be environment-agnostic.
    # Account/Region-dependent features and context lookups will not work,
    # but a single synthesized template can be deployed anywhere.
    # Uncomment the next line to specialize this stack for the AWS Account
    # and Region that are implied by the current CLI configuration.
    # env=cdk.Environment(account=os.getenv('CDK_DEFAULT_ACCOUNT'), region=os.getenv('CDK_DEFAULT_REGION')),
)

# Phase 6: HITL Dashboard API Stack
api_stack = ApiStack(app, "ICPA-ApiStack",
    foundation_stack=foundation_stack,
    # env=cdk.Environment(account=os.getenv('CDK_DEFAULT_ACCOUNT'), region=os.getenv('CDK_DEFAULT_REGION')),
)

app.synth()

