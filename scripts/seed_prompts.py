from __future__ import annotations

import argparse
import pathlib
from typing import Iterable, Tuple

import boto3


PROMPTS: Tuple[Tuple[str, str, str], ...] = (
    ("fraud_agent", "v1.0.0", "prompts/fraud_agent/v1.0.0.txt"),
    ("adjudication_agent", "v1.0.0", "prompts/adjudication_agent/v1.0.0.txt"),
    ("policy_router", "v1.0.0", "prompts/policy_router/v1.0.0.txt"),
)


def _read_text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def seed_prompts(region: str, update_latest: bool) -> None:
    ssm = boto3.client("ssm", region_name=region)
    repo_root = pathlib.Path(__file__).resolve().parents[1]

    for agent, version, relative_path in PROMPTS:
        prompt_value = _read_text(repo_root / relative_path)
        name = f"/icpa/prompts/{agent}/{version}"
        ssm.put_parameter(
            Name=name,
            Value=prompt_value,
            Type="String",
            Overwrite=True,
            Description=f"{agent} prompt {version}",
        )
        if update_latest:
            ssm.put_parameter(
                Name=f"/icpa/prompts/{agent}/latest",
                Value=version,
                Type="String",
                Overwrite=True,
                Description=f"{agent} latest prompt version",
            )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed ICPA prompts in SSM Parameter Store")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--no-latest", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    seed_prompts(args.region, update_latest=not args.no_latest)


if __name__ == "__main__":
    main()
