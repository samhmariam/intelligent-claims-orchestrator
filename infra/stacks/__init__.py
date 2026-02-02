"""
ICPA Infrastructure Stacks
===========================
CDK stacks for the Intelligent Claims Processing Accelerator.

Stacks:
- FoundationStack: Core infrastructure (S3, DynamoDB, Lambda)
- ApiStack: Phase 6 Human-in-the-Loop dashboard API
- AnalyticsStack: Phase 7 Analytics & Reporting data lake
"""

from .foundation_stack import FoundationStack
from .api_stack import ApiStack
from .analytics_stack import AnalyticsStack

__all__ = [
    "FoundationStack",
    "ApiStack",
    "AnalyticsStack",
]
