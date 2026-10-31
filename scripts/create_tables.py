"""
DynamoDB table creation script for College Management System.
Creates all required tables with primary keys, composite keys, and GSIs.
Safe for both AWS deployment (On-Demand billing) and local DynamoDB.
"""
import logging
import os
import sys
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# Load env variables
load_dotenv()

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("create_tables")


def get_dynamo_resource():
    """Create DynamoDB resource based on environment settings."""
    endpoint_url = os.getenv("DYNAMODB_ENDPOINT_URL")
    region_name = os.getenv("AWS_REGION", "us-east-1")
    kwargs = {"region_name": region_name}
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    return boto3.resource("dynamodb", **kwargs)


TABLE_DEFINITIONS = [
    {
        "TableName": os.getenv("DYNAMODB_TABLE_USERS", "cms_users"),
        "KeySchema": [
            {"AttributeName": "username", "KeyType": "HASH"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "username", "AttributeType": "S"},
            {"AttributeName": "email", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "EmailIndex",
                "KeySchema": [
                    {"AttributeName": "email", "KeyType": "HASH"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        "BillingMode": "PAY_PER_REQUEST",
    },
    {
        "TableName": os.getenv("DYNAMODB_TABLE_STUDENTS", "cms_students"),
        "KeySchema": [
            {"AttributeName": "student_id", "KeyType": "HASH"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "student_id", "AttributeType": "S"},
            {"AttributeName": "department", "AttributeType": "S"},
            {"AttributeName": "year", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "DeptYearIndex",
                "KeySchema": [
                    {"AttributeName": "department", "KeyType": "HASH"},
                    {"AttributeName": "year", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        "BillingMode": "PAY_PER_REQUEST",
    },
    {
        "TableName": os.getenv("DYNAMODB_TABLE_ATTENDANCE", "cms_attendance"),
        "KeySchema": [
            {"AttributeName": "student_id", "KeyType": "HASH"},
            {"AttributeName": "date_course", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "student_id", "AttributeType": "S"},
            {"AttributeName": "date_course", "AttributeType": "S"},
            {"AttributeName": "course_id", "AttributeType": "S"},
            {"AttributeName": "date", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "CourseDateIndex",
                "KeySchema": [
                    {"AttributeName": "course_id", "KeyType": "HASH"},
                    {"AttributeName": "date", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        "BillingMode": "PAY_PER_REQUEST",
    },
    {
        "TableName": os.getenv("DYNAMODB_TABLE_RESULTS", "cms_results"),
        "KeySchema": [
            {"AttributeName": "student_id", "KeyType": "HASH"},
            {"AttributeName": "sem_subject", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "student_id", "AttributeType": "S"},
            {"AttributeName": "sem_subject", "AttributeType": "S"},
        ],
        "BillingMode": "PAY_PER_REQUEST",
    },
    {
        "TableName": os.getenv("DYNAMODB_TABLE_EXAMS", "cms_exams"),
        "KeySchema": [
            {"AttributeName": "exam_id", "KeyType": "HASH"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "exam_id", "AttributeType": "S"},
            {"AttributeName": "status", "AttributeType": "S"},
            {"AttributeName": "start_time", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "StatusTimeIndex",
                "KeySchema": [
                    {"AttributeName": "status", "KeyType": "HASH"},
                    {"AttributeName": "start_time", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        "BillingMode": "PAY_PER_REQUEST",
    },
    {
        "TableName": os.getenv("DYNAMODB_TABLE_QUESTIONS", "cms_questions"),
        "KeySchema": [
            {"AttributeName": "exam_id", "KeyType": "HASH"},
            {"AttributeName": "question_id", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "exam_id", "AttributeType": "S"},
            {"AttributeName": "question_id", "AttributeType": "S"},
        ],
        "BillingMode": "PAY_PER_REQUEST",
    },
    {
        "TableName": os.getenv("DYNAMODB_TABLE_SUBMISSIONS", "cms_submissions"),
        "KeySchema": [
            {"AttributeName": "exam_id", "KeyType": "HASH"},
            {"AttributeName": "student_id", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "exam_id", "AttributeType": "S"},
            {"AttributeName": "student_id", "AttributeType": "S"},
        ],
        "BillingMode": "PAY_PER_REQUEST",
    },
    {
        "TableName": os.getenv("DYNAMODB_TABLE_AUDIT_LOGS", "cms_audit_logs"),
        "KeySchema": [
            {"AttributeName": "log_date", "KeyType": "HASH"},
            {"AttributeName": "ts_id", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "log_date", "AttributeType": "S"},
            {"AttributeName": "ts_id", "AttributeType": "S"},
        ],
        "BillingMode": "PAY_PER_REQUEST",
    },
]


def create_tables():
    """Create all configured tables in DynamoDB if they do not already exist."""
    dynamo = get_dynamo_resource()
    existing_tables = [t.name for t in dynamo.tables.all()]

    logger.info("Existing DynamoDB tables: %s", existing_tables)

    for definition in TABLE_DEFINITIONS:
        name = definition["TableName"]
        if name in existing_tables:
            logger.info("Table '%s' already exists. Skipping creation.", name)
            continue

        logger.info("Creating table '%s'...", name)
        try:
            table = dynamo.create_table(**definition)
            table.meta.client.get_waiter("table_exists").wait(TableName=name)
            logger.info("Table '%s' created successfully.", name)
        except ClientError as e:
            logger.error("Failed to create table '%s': %s", name, e)


if __name__ == "__main__":
    create_tables()
