"""
User model wrapping DynamoDB cms_users table with Flask-Login integration.
"""
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from flask import current_app
from flask_login import UserMixin

from app.extensions import bcrypt
from app.services.dynamo import get_dynamo_service
from app.utils.helpers import iso_now

logger = logging.getLogger(__name__)


class User(UserMixin):
    """
    User model representing an authenticated user (Admin, Faculty, Student)
    backed by DynamoDB 'cms_users' table.
    """

    def __init__(
        self,
        username: str,
        email: str,
        password_hash: str,
        role: str,
        status: str = "active",
        full_name: str = "",
        linked_id: Optional[str] = None,
        created_at: Optional[str] = None,
        last_login: Optional[str] = None,
    ):
        self.username = username
        self.email = email
        self.password_hash = password_hash
        self.role = role.lower() if role else "student"
        self.status = status.lower() if status else "active"
        self.full_name = full_name or ""
        self.linked_id = linked_id
        self.created_at = created_at or iso_now()
        self.last_login = last_login

    def get_id(self) -> str:
        """Return unique username identifier for Flask-Login."""
        return self.username

    @property
    def is_active(self) -> bool:
        """Check if user account is active."""
        return self.status == "active"

    @property
    def is_admin(self) -> bool:
        """Check if user is administrator."""
        return self.role == "admin"

    @property
    def is_faculty(self) -> bool:
        """Check if user is faculty."""
        return self.role == "faculty"

    @property
    def is_student(self) -> bool:
        """Check if user is student."""
        return self.role == "student"

    def check_password(self, password: str) -> bool:
        """Verify plain-text password against bcrypt hash."""
        if not self.password_hash:
            return False
        return bcrypt.check_password_hash(self.password_hash, password)

    def to_dict(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """Convert user instance to JSON-serializable dictionary."""
        data = {
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "status": self.status,
            "full_name": self.full_name,
            "linked_id": self.linked_id,
            "created_at": self.created_at,
            "last_login": self.last_login,
        }
        if include_sensitive:
            data["password_hash"] = self.password_hash
        return data

    @classmethod
    def _table_name(cls) -> str:
        """Get DynamoDB users table name."""
        try:
            if current_app:
                return current_app.config.get("DYNAMODB_TABLE_USERS", "cms_users")
        except RuntimeError:
            pass
        return os.getenv("DYNAMODB_TABLE_USERS", "cms_users")

    @classmethod
    def from_dynamo_item(cls, item: Dict[str, Any]) -> "User":
        """Instantiate User from DynamoDB item dictionary."""
        return cls(
            username=item.get("username", ""),
            email=item.get("email", ""),
            password_hash=item.get("password_hash", ""),
            role=item.get("role", "student"),
            status=item.get("status", "active"),
            full_name=item.get("full_name", ""),
            linked_id=item.get("linked_id"),
            created_at=item.get("created_at"),
            last_login=item.get("last_login"),
        )

    @classmethod
    def get_by_username(cls, username: str) -> Optional["User"]:
        """Fetch user by username (Partition Key)."""
        dynamo = get_dynamo_service()
        try:
            item = dynamo.get_item(cls._table_name(), {"username": username})
            if item:
                return cls.from_dynamo_item(item)
            return None
        except Exception as e:
            logger.error("Error fetching user %s: %s", username, e)
            return None

    @classmethod
    def get_by_email(cls, email: str) -> Optional["User"]:
        """Fetch user by email using Global Secondary Index EmailIndex."""
        from boto3.dynamodb.conditions import Key
        dynamo = get_dynamo_service()
        try:
            items = dynamo.query(
                table_name=cls._table_name(),
                index_name="EmailIndex",
                key_condition_expression=Key("email").eq(email.strip().lower()),
                limit=1,
            )
            if items:
                return cls.from_dynamo_item(items[0])
            return None
        except Exception as e:
            logger.error("Error querying user by email %s: %s", email, e)
            return None

    @classmethod
    def create(
        cls,
        username: str,
        email: str,
        password: str,
        role: str,
        full_name: str,
        linked_id: Optional[str] = None,
        status: str = "active",
    ) -> "User":
        """
        Hash password using bcrypt and create a new user record in DynamoDB.
        Enforces unique username check.
        """
        dynamo = get_dynamo_service()
        rounds = 12
        try:
            if current_app:
                rounds = current_app.config.get("BCRYPT_LOG_ROUNDS", 12)
        except RuntimeError:
            rounds = int(os.getenv("BCRYPT_LOG_ROUNDS", "12"))

        password_hash = bcrypt.generate_password_hash(password, rounds=rounds).decode("utf-8")
        now_str = iso_now()

        item = {
            "username": username.strip(),
            "email": email.strip().lower(),
            "password_hash": password_hash,
            "role": role.lower().strip(),
            "status": status.lower().strip(),
            "full_name": full_name.strip(),
            "linked_id": linked_id,
            "created_at": now_str,
            "last_login": None,
        }

        # Put with condition that username doesn't already exist
        dynamo.put_item(
            table_name=cls._table_name(),
            item=item,
            condition_expression="attribute_not_exists(username)",
        )
        return cls.from_dynamo_item(item)

    def update_last_login(self) -> None:
        """Update last login timestamp to now."""
        dynamo = get_dynamo_service()
        now_str = iso_now()
        self.last_login = now_str
        try:
            dynamo.update_item(
                table_name=self._table_name(),
                key={"username": self.username},
                update_expression="SET last_login = :ts",
                expression_attribute_values={":ts": now_str},
            )
        except Exception as e:
            logger.warning("Failed to update last_login for user %s: %s", self.username, e)

    def update_password(self, new_password: str) -> None:
        """Update user password with freshly computed bcrypt hash."""
        dynamo = get_dynamo_service()
        rounds = 12
        try:
            if current_app:
                rounds = current_app.config.get("BCRYPT_LOG_ROUNDS", 12)
        except RuntimeError:
            pass

        new_hash = bcrypt.generate_password_hash(new_password, rounds=rounds).decode("utf-8")
        self.password_hash = new_hash
        dynamo.update_item(
            table_name=self._table_name(),
            key={"username": self.username},
            update_expression="SET password_hash = :pwd",
            expression_attribute_values={":pwd": new_hash},
        )
