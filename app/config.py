"""
Application configuration module.
Provides environment-specific settings loaded cleanly from environment variables.
"""
import os
from datetime import timedelta


class BaseConfig:
    """Base configuration with shared defaults."""
    SECRET_KEY = os.getenv("SECRET_KEY", "fallback-secret-key-for-development-only")
    
    # AWS & DynamoDB Configuration
    AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
    DYNAMODB_ENDPOINT_URL = os.getenv("DYNAMODB_ENDPOINT_URL", None)
    
    # DynamoDB Table Names
    DYNAMODB_TABLE_USERS = os.getenv("DYNAMODB_TABLE_USERS", "cms_users")
    DYNAMODB_TABLE_STUDENTS = os.getenv("DYNAMODB_TABLE_STUDENTS", "cms_students")
    DYNAMODB_TABLE_ATTENDANCE = os.getenv("DYNAMODB_TABLE_ATTENDANCE", "cms_attendance")
    DYNAMODB_TABLE_RESULTS = os.getenv("DYNAMODB_TABLE_RESULTS", "cms_results")
    DYNAMODB_TABLE_EXAMS = os.getenv("DYNAMODB_TABLE_EXAMS", "cms_exams")
    DYNAMODB_TABLE_QUESTIONS = os.getenv("DYNAMODB_TABLE_QUESTIONS", "cms_questions")
    DYNAMODB_TABLE_SUBMISSIONS = os.getenv("DYNAMODB_TABLE_SUBMISSIONS", "cms_submissions")
    DYNAMODB_TABLE_AUDIT_LOGS = os.getenv("DYNAMODB_TABLE_AUDIT_LOGS", "cms_audit_logs")
    
    # S3 Configuration
    S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", None)
    S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "cms-default-storage")
    S3_PRESIGNED_EXPIRATION_SECONDS = int(os.getenv("S3_PRESIGNED_EXPIRATION_SECONDS", "3600"))
    
    # Security Configuration
    BCRYPT_LOG_ROUNDS = int(os.getenv("BCRYPT_LOG_ROUNDS", "12"))
    LOGIN_RATE_LIMIT_PER_MINUTE = int(os.getenv("LOGIN_RATE_LIMIT_PER_MINUTE", "5"))
    PERMANENT_SESSION_LIFETIME = timedelta(days=1)
    
    # Session Cookies
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() in ("true", "1")
    
    # CORS Configuration
    CORS_ALLOWED_ORIGINS = os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000"
    ).split(",")


class DevelopmentConfig(BaseConfig):
    """Development environment configuration."""
    DEBUG = True
    TESTING = False
    SESSION_COOKIE_SECURE = False


class ProductionConfig(BaseConfig):
    """Production environment configuration with strict security defaults."""
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True
    
    def __init__(self):
        # Validate that SECRET_KEY is explicitly configured in production
        secret = os.getenv("SECRET_KEY")
        if not secret or secret == "fallback-secret-key-for-development-only":
            raise ValueError("SECRET_KEY must be set to a secure unique value in production.")


class TestingConfig(BaseConfig):
    """Testing environment configuration."""
    DEBUG = False
    TESTING = True
    BCRYPT_LOG_ROUNDS = 4  # Lower rounds for faster test suites
    DYNAMODB_ENDPOINT_URL = os.getenv("DYNAMODB_ENDPOINT_URL", "http://localhost:8000")
    S3_BUCKET_NAME = "cms-test-bucket"
    SESSION_COOKIE_SECURE = False


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
