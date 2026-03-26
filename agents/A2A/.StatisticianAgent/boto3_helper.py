import boto3
from typing import Optional


def find_s3_bucket_name_by_suffix(name_suffix: str) -> Optional[str]:
    """Find S3 bucket name by name suffix."""
    client = boto3.client('s3')
    response = client.list_buckets()
    for bucket in response['Buckets']:
        if bucket['Name'].endswith(name_suffix):
            return bucket['Name']
    return None


def get_role_arn(role_name_part: str) -> Optional[str]:
    """Retrieve IAM role ARN based on partial role name match.

    Args:
        role_name_part: Part of the role name to search for.

    Returns:
        Role ARN if found, None otherwise.
    """
    iam = boto3.client('iam')
    try:
        for page in iam.get_paginator('list_roles').paginate():
            for role in page['Roles']:
                if role_name_part in role['RoleName']:
                    return role['Arn']
        return None
    except Exception as e:
        print(f"Error retrieving role: {e}")
        return None
