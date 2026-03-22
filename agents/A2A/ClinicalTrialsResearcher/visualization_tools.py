"""
Visualization tools for creating charts and uploading to S3.

This module provides tools for generating data visualizations (pie charts)
and uploading them to S3 with presigned URLs for access.
"""

import os
import uuid
from typing import List, Optional
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import boto3
from botocore.exceptions import ClientError
from strands import tool


@tool
def create_pie_chart(
    title: str,
    data: List[dict],
    colors: Optional[List[str]] = None,
    folder: str = "charts"
) -> str:
    """
    Create a pie chart and upload to S3.
    
    Args:
        title: Chart title
        data: List of dicts with 'label' and 'value' keys
        colors: Optional list of color codes (hex or named colors)
        folder: S3 folder path for organizing charts
    
    Returns:
        Presigned URL for the chart image (valid for 1 hour)
    
    Raises:
        ValueError: If data is empty or invalid
        RuntimeError: If S3 upload fails
    """
    if not data:
        raise ValueError("Data cannot be empty")
    
    if not all('label' in item and 'value' in item for item in data):
        raise ValueError("Each data item must have 'label' and 'value' keys")
    
    # Extract labels and values
    labels = [item['label'] for item in data]
    values = [item['value'] for item in data]
    
    # Validate values are numeric
    try:
        values = [float(v) for v in values]
    except (ValueError, TypeError) as e:
        raise ValueError(f"All values must be numeric: {e}")
    
    # Generate unique filename
    filename = f"{uuid.uuid4()}.png"
    file_path = f"/tmp/{filename}"
    s3_key = f"{folder}/{filename}"
    
    try:
        # Generate chart
        plt.figure(figsize=(8, 8))
        plt.title(title, fontsize=16, fontweight='bold')
        plt.pie(
            values,
            labels=labels,
            autopct='%1.1f%%',
            colors=colors,
            startangle=90
        )
        plt.axis('equal')  # Equal aspect ratio ensures circular pie
        plt.tight_layout()
        plt.savefig(file_path, dpi=100, bbox_inches='tight')
        plt.close()
        
        # Get bucket name from environment
        bucket_name = os.environ.get("CHART_IMAGE_BUCKET")
        if not bucket_name:
            raise RuntimeError("CHART_IMAGE_BUCKET environment variable not set")
        
        # Upload to S3
        s3_client = boto3.client('s3')
        s3_client.upload_file(
            file_path,
            bucket_name,
            s3_key,
            ExtraArgs={"ContentType": "image/png"}
        )
        
        # Generate presigned URL (valid for 1 hour)
        presigned_url = s3_client.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": bucket_name, "Key": s3_key},
            ExpiresIn=3600  # 1 hour
        )
        
        return presigned_url
        
    except ClientError as e:
        raise RuntimeError(f"S3 upload failed: {e}")
    
    finally:
        # Cleanup temporary file
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass  # Best effort cleanup
