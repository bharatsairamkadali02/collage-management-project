"""
Amazon S3 service layer for the College Management System.
Handles document uploads, presigned URLs for results and exports, and bucket prefix organization.
"""
import io
import logging
import os
from typing import Any, Dict, List, Optional, Union
import boto3
from botocore.exceptions import ClientError
from flask import current_app

logger = logging.getLogger(__name__)


class S3Service:
    """
    S3 storage service providing presigned URLs, uploads, downloads,
    and prefix-based resource management.
    """

    def __init__(
        self,
        bucket_name: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        region_name: Optional[str] = None,
    ):
        self._bucket_name = bucket_name or os.getenv("S3_BUCKET_NAME", "cms-default-storage")
        self._endpoint_url = endpoint_url or os.getenv("S3_ENDPOINT_URL")
        self._region_name = region_name or os.getenv("AWS_REGION", "us-east-1")
        self._client = None

    @property
    def bucket_name(self) -> str:
        """Get active S3 bucket name from Flask config or environment."""
        try:
            if current_app:
                return current_app.config.get("S3_BUCKET_NAME", self._bucket_name)
        except RuntimeError:
            pass
        return self._bucket_name

    @property
    def client(self):
        """Lazy load boto3 S3 client."""
        if self._client is None:
            endpoint = self._endpoint_url
            region = self._region_name
            try:
                if current_app:
                    endpoint = current_app.config.get("S3_ENDPOINT_URL", endpoint)
                    region = current_app.config.get("AWS_REGION", region)
            except RuntimeError:
                pass

            kwargs: Dict[str, Any] = {"region_name": region}
            if endpoint:
                kwargs["endpoint_url"] = endpoint

            self._client = boto3.client("s3", **kwargs)
        return self._client

    def generate_presigned_url(
        self,
        object_key: str,
        expiration: Optional[int] = None,
        client_method: str = "get_object",
        http_method: Optional[str] = None,
    ) -> str:
        """
        Generate a presigned URL to share an S3 object.
        Default expiration is 3600 seconds (1 hour).
        """
        if expiration is None:
            try:
                if current_app:
                    expiration = current_app.config.get("S3_PRESIGNED_EXPIRATION_SECONDS", 3600)
                else:
                    expiration = 3600
            except RuntimeError:
                expiration = 3600

        params = {"Bucket": self.bucket_name, "Key": object_key}
        try:
            url = self.client.generate_presigned_url(
                ClientMethod=client_method,
                Params=params,
                ExpiresIn=expiration,
                HttpMethod=http_method,
            )
            return url
        except ClientError as e:
            logger.error("Error generating presigned URL for key %s: %s", object_key, e)
            raise

    def upload_file(
        self,
        file_obj: Union[str, bytes, io.BytesIO],
        object_key: str,
        content_type: str = "application/octet-stream",
        metadata: Optional[Dict[str, str]] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Upload file content or stream to S3 with metadata and tagging.
        Returns the object key.
        """
        extra_args: Dict[str, Any] = {"ContentType": content_type}
        if metadata:
            extra_args["Metadata"] = metadata

        if tags:
            tag_string = "&".join([f"{k}={v}" for k, v in tags.items()])
            extra_args["Tagging"] = tag_string

        try:
            if isinstance(file_obj, (bytes, bytearray)):
                self.client.put_object(
                    Bucket=self.bucket_name,
                    Key=object_key,
                    Body=file_obj,
                    **extra_args,
                )
            elif hasattr(file_obj, "read"):
                self.client.upload_fileobj(
                    Fileobj=file_obj,
                    Bucket=self.bucket_name,
                    Key=object_key,
                    ExtraArgs=extra_args,
                )
            elif isinstance(file_obj, str):
                self.client.upload_file(
                    Filename=file_obj,
                    Bucket=self.bucket_name,
                    Key=object_key,
                    ExtraArgs=extra_args,
                )
            else:
                raise ValueError("Unsupported file_obj type for S3 upload.")

            logger.info("Successfully uploaded object to s3://%s/%s", self.bucket_name, object_key)
            return object_key
        except ClientError as e:
            logger.error("Error uploading object %s to S3: %s", object_key, e)
            raise

    def download_file_bytes(self, object_key: str) -> bytes:
        """Download an S3 object as in-memory bytes."""
        try:
            response = self.client.get_object(Bucket=self.bucket_name, Key=object_key)
            return response["Body"].read()
        except ClientError as e:
            logger.error("Error downloading S3 object %s: %s", object_key, e)
            raise

    def list_files(self, prefix: str = "") -> List[Dict[str, Any]]:
        """List objects matching a given prefix."""
        try:
            response = self.client.list_objects_v2(Bucket=self.bucket_name, Prefix=prefix)
            contents = response.get("Contents", [])
            results = []
            for item in contents:
                results.append({
                    "key": item["Key"],
                    "size": item["Size"],
                    "last_modified": item["LastModified"].isoformat(),
                })
            return results
        except ClientError as e:
            logger.error("Error listing S3 objects with prefix %s: %s", prefix, e)
            raise

    def delete_file(self, object_key: str) -> bool:
        """Delete an S3 object."""
        try:
            self.client.delete_object(Bucket=self.bucket_name, Key=object_key)
            return True
        except ClientError as e:
            logger.error("Error deleting S3 object %s: %s", object_key, e)
            raise


_s3_service_instance: Optional[S3Service] = None


def get_s3_service() -> S3Service:
    """Return singleton S3Service instance."""
    global _s3_service_instance
    if _s3_service_instance is None:
        _s3_service_instance = S3Service()
    return _s3_service_instance
