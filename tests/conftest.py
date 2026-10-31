"""
Pytest configuration, fixtures, and AWS DynamoDB/S3 mocks.
"""
import os
import pytest
import boto3
from moto import mock_aws

# Ensure testing environment variables are configured before importing app
os.environ["FLASK_ENV"] = "testing"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SECURITY_TOKEN"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"
os.environ["DYNAMODB_ENDPOINT_URL"] = ""
os.environ["S3_ENDPOINT_URL"] = ""

from app import create_app
from app.extensions import bcrypt
from app.models.user import User
from app.services.dynamo import DynamoDBService, get_dynamo_service
from scripts.create_tables import TABLE_DEFINITIONS


@pytest.fixture(scope="session", autouse=True)
def aws_credentials():
    """Mocked AWS Credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture
def app():
    """Create Flask application configured for testing."""
    application = create_app("testing")
    application.config.update({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key-32-bytes-long-string",
        "DYNAMODB_ENDPOINT_URL": None,
        "S3_ENDPOINT_URL": None,
    })
    return application


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture(autouse=True)
def setup_mock_aws(app):
    """
    Mock DynamoDB and S3 for each test.
    Automatically provisions all 8 tables and seeds test users.
    """
    with mock_aws():
        # Reset DynamoDB service singleton resource
        dynamo_svc = get_dynamo_service()
        dynamo_svc._resource = boto3.resource("dynamodb", region_name="us-east-1")

        # Create all tables in moto
        for table_def in TABLE_DEFINITIONS:
            dynamo_svc.resource.create_table(**table_def)

        # Create test S3 bucket
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="cms-test-bucket")

        # Seed initial test users inside app context
        with app.app_context():
            User.create(
                username="admin_user",
                email="admin@test.edu",
                password="Password@123",
                role="admin",
                full_name="Admin User",
            )
            User.create(
                username="faculty_user",
                email="faculty@test.edu",
                password="Password@123",
                role="faculty",
                full_name="Faculty User",
                linked_id="FAC001",
            )
            User.create(
                username="student_user",
                email="student@test.edu",
                password="Password@123",
                role="student",
                full_name="Student User",
                linked_id="STU001",
            )
            User.create(
                username="other_student",
                email="other@test.edu",
                password="Password@123",
                role="student",
                full_name="Other Student",
                linked_id="STU002",
            )

        yield


def login_as(client, username: str, password: str = "Password@123"):
    """Helper to authenticate a test client via /api/auth/login."""
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, f"Login failed for {username}: {response.get_json()}"
    return response


@pytest.fixture
def admin_client(client):
    """Client authenticated as administrator."""
    login_as(client, "admin_user")
    return client


@pytest.fixture
def faculty_client(client):
    """Client authenticated as faculty."""
    login_as(client, "faculty_user")
    return client


@pytest.fixture
def student_client(client):
    """Client authenticated as student."""
    login_as(client, "student_user")
    return client
