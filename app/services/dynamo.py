"""
DynamoDB service layer for the College Management System.
Wraps boto3 resource operations with Decimal conversion, error handling, and clean dictionary responses.
"""
import logging
import os
from typing import Any, Dict, List, Optional
import boto3
from botocore.exceptions import ClientError
from flask import current_app

from app.utils.helpers import clean_none_values, from_decimal, to_decimal

logger = logging.getLogger(__name__)


class DynamoDBService:
    """
    Centralized service for managing DynamoDB operations across tables.
    Works seamlessly with AWS IAM Instance Profile or local DynamoDB container.
    """

    def __init__(self, endpoint_url: Optional[str] = None, region_name: Optional[str] = None):
        self.endpoint_url = endpoint_url or os.getenv("DYNAMODB_ENDPOINT_URL")
        self.region_name = region_name or os.getenv("AWS_REGION", "us-east-1")
        self._resource = None

    @property
    def resource(self):
        """Lazy load and return boto3 DynamoDB resource."""
        if self._resource is None:
            # Check Flask config if inside application context
            endpoint = self.endpoint_url
            region = self.region_name
            try:
                if current_app:
                    endpoint = current_app.config.get("DYNAMODB_ENDPOINT_URL", endpoint)
                    region = current_app.config.get("AWS_REGION", region)
            except RuntimeError:
                pass  # Running outside Flask app context (e.g. scripts/seed)

            kwargs: Dict[str, Any] = {"region_name": region}
            if endpoint:
                kwargs["endpoint_url"] = endpoint

            self._resource = boto3.resource("dynamodb", **kwargs)
        return self._resource

    def get_table(self, table_name: str):
        """Return a boto3 DynamoDB Table instance."""
        return self.resource.Table(table_name)

    def put_item(
        self,
        table_name: str,
        item: Dict[str, Any],
        condition_expression: Optional[str] = None,
        expression_attribute_names: Optional[Dict[str, str]] = None,
        expression_attribute_values: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Put an item into DynamoDB.
        Automatically converts numeric types to Decimal and strips null values.
        """
        table = self.get_table(table_name)
        cleaned_item = to_decimal(clean_none_values(item))

        put_kwargs: Dict[str, Any] = {"Item": cleaned_item}
        if condition_expression:
            put_kwargs["ConditionExpression"] = condition_expression
        if expression_attribute_names:
            put_kwargs["ExpressionAttributeNames"] = expression_attribute_names
        if expression_attribute_values:
            put_kwargs["ExpressionAttributeValues"] = to_decimal(expression_attribute_values)

        try:
            table.put_item(**put_kwargs)
            return from_decimal(cleaned_item)
        except ClientError as e:
            logger.error("DynamoDB put_item error on table %s: %s", table_name, e.response["Error"]["Message"])
            raise

    def get_item(self, table_name: str, key: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Get an item by its primary key.
        Returns None if not found.
        """
        table = self.get_table(table_name)
        try:
            response = table.get_item(Key=to_decimal(key))
            item = response.get("Item")
            if item:
                return from_decimal(item)
            return None
        except ClientError as e:
            logger.error("DynamoDB get_item error on table %s: %s", table_name, e.response["Error"]["Message"])
            raise

    def query(
        self,
        table_name: str,
        key_condition_expression: Any,
        index_name: Optional[str] = None,
        filter_expression: Optional[Any] = None,
        expression_attribute_names: Optional[Dict[str, str]] = None,
        expression_attribute_values: Optional[Dict[str, Any]] = None,
        scan_index_forward: bool = True,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Query items from table or GSI.
        Handles pagination automatically up to optional limit.
        """
        table = self.get_table(table_name)
        query_kwargs: Dict[str, Any] = {
            "KeyConditionExpression": key_condition_expression,
            "ScanIndexForward": scan_index_forward,
        }

        if index_name:
            query_kwargs["IndexName"] = index_name
        if filter_expression:
            query_kwargs["FilterExpression"] = filter_expression
        if expression_attribute_names:
            query_kwargs["ExpressionAttributeNames"] = expression_attribute_names
        if expression_attribute_values:
            query_kwargs["ExpressionAttributeValues"] = to_decimal(expression_attribute_values)
        if limit:
            query_kwargs["Limit"] = limit

        try:
            items: List[Dict[str, Any]] = []
            while True:
                response = table.query(**query_kwargs)
                items.extend(response.get("Items", []))

                if limit and len(items) >= limit:
                    items = items[:limit]
                    break

                last_key = response.get("LastEvaluatedKey")
                if not last_key:
                    break
                query_kwargs["ExclusiveStartKey"] = last_key

            return from_decimal(items)
        except ClientError as e:
            logger.error("DynamoDB query error on table %s: %s", table_name, e.response["Error"]["Message"])
            raise

    def scan(
        self,
        table_name: str,
        filter_expression: Optional[Any] = None,
        expression_attribute_names: Optional[Dict[str, str]] = None,
        expression_attribute_values: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Scan a table, optionally with a filter expression.
        """
        table = self.get_table(table_name)
        scan_kwargs: Dict[str, Any] = {}

        if filter_expression:
            scan_kwargs["FilterExpression"] = filter_expression
        if expression_attribute_names:
            scan_kwargs["ExpressionAttributeNames"] = expression_attribute_names
        if expression_attribute_values:
            scan_kwargs["ExpressionAttributeValues"] = to_decimal(expression_attribute_values)
        if limit:
            scan_kwargs["Limit"] = limit

        try:
            items: List[Dict[str, Any]] = []
            while True:
                response = table.scan(**scan_kwargs)
                items.extend(response.get("Items", []))

                if limit and len(items) >= limit:
                    items = items[:limit]
                    break

                last_key = response.get("LastEvaluatedKey")
                if not last_key:
                    break
                scan_kwargs["ExclusiveStartKey"] = last_key

            return from_decimal(items)
        except ClientError as e:
            logger.error("DynamoDB scan error on table %s: %s", table_name, e.response["Error"]["Message"])
            raise

    def update_item(
        self,
        table_name: str,
        key: Dict[str, Any],
        update_expression: str,
        expression_attribute_names: Optional[Dict[str, str]] = None,
        expression_attribute_values: Optional[Dict[str, Any]] = None,
        condition_expression: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update item attributes with expressions.
        Returns the updated item attributes.
        """
        table = self.get_table(table_name)
        update_kwargs: Dict[str, Any] = {
            "Key": to_decimal(key),
            "UpdateExpression": update_expression,
            "ReturnValues": "ALL_NEW",
        }

        if expression_attribute_names:
            update_kwargs["ExpressionAttributeNames"] = expression_attribute_names
        if expression_attribute_values:
            update_kwargs["ExpressionAttributeValues"] = to_decimal(expression_attribute_values)
        if condition_expression:
            update_kwargs["ConditionExpression"] = condition_expression

        try:
            response = table.update_item(**update_kwargs)
            return from_decimal(response.get("Attributes", {}))
        except ClientError as e:
            logger.error("DynamoDB update_item error on table %s: %s", table_name, e.response["Error"]["Message"])
            raise

    def delete_item(
        self,
        table_name: str,
        key: Dict[str, Any],
        condition_expression: Optional[str] = None,
    ) -> bool:
        """Delete an item by primary key."""
        table = self.get_table(table_name)
        delete_kwargs: Dict[str, Any] = {"Key": to_decimal(key)}
        if condition_expression:
            delete_kwargs["ConditionExpression"] = condition_expression

        try:
            table.delete_item(**delete_kwargs)
            return True
        except ClientError as e:
            logger.error("DynamoDB delete_item error on table %s: %s", table_name, e.response["Error"]["Message"])
            raise

    def batch_write(self, table_name: str, items: List[Dict[str, Any]]) -> int:
        """
        Batch write a list of items using the boto3 batch_writer.
        Handles unwritten items automatically.
        """
        table = self.get_table(table_name)
        count = 0
        try:
            with table.batch_writer() as batch:
                for item in items:
                    cleaned = to_decimal(clean_none_values(item))
                    batch.put_item(Item=cleaned)
                    count += 1
            return count
        except ClientError as e:
            logger.error("DynamoDB batch_write error on table %s: %s", table_name, e.response["Error"]["Message"])
            raise


# Global singleton instance
_dynamo_service_instance: Optional[DynamoDBService] = None


def get_dynamo_service() -> DynamoDBService:
    """Return singleton DynamoDBService instance."""
    global _dynamo_service_instance
    if _dynamo_service_instance is None:
        _dynamo_service_instance = DynamoDBService()
    return _dynamo_service_instance
