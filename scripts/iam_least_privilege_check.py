from __future__ import annotations

import argparse
from typing import Iterable, List

import boto3


def _get_function_role_arns(function_names: Iterable[str], region: str) -> List[str]:
    lambda_client = boto3.client("lambda", region_name=region)
    role_arns: List[str] = []
    for name in function_names:
        response = lambda_client.get_function(FunctionName=name)
        role_arns.append(response["Configuration"]["Role"])
    return role_arns


def _list_attached_policies(role_arn: str, region: str) -> List[str]:
    iam_client = boto3.client("iam", region_name=region)
    role_name = role_arn.split("/")[-1]
    response = iam_client.list_attached_role_policies(RoleName=role_name)
    return [policy["PolicyArn"] for policy in response.get("AttachedPolicies", [])]


def validate_least_privilege(function_names: Iterable[str], region: str) -> None:
    role_arns = _get_function_role_arns(function_names, region)
    for role_arn in role_arns:
        policies = _list_attached_policies(role_arn, region)
        if any("AdministratorAccess" in policy for policy in policies):
            raise SystemExit(f"High risk: AdministratorAccess attached to {role_arn}")
        print(f"Role {role_arn} attached policies: {policies}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check Lambda IAM roles for least privilege")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--functions", nargs="+", required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    validate_least_privilege(args.functions, args.region)


if __name__ == "__main__":
    main()
