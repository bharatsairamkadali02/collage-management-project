"""
Audit log service for tracking system operations and security events.
Stores entries in the cms_audit_logs DynamoDB table.
"""
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from flask import current_app, request

from app.services.dynamo import get_dynamo_service
from app.utils.helpers import format_date, iso_now

logger = logging.getLogger(__name__)


class AuditService:
    """Service to record and query immutable system audit logs."""

    def __init__(self):
        self.dynamo = get_dynamo_service()

    @property
    def table_name(self) -> str:
        """Get audit logs table name."""
        try:
            if current_app:
                return current_app.config.get("DYNAMODB_TABLE_AUDIT_LOGS", "cms_audit_logs")
        except RuntimeError:
            pass
        return os.getenv("DYNAMODB_TABLE_AUDIT_LOGS", "cms_audit_logs")

    def log(
        self,
        actor: str,
        action: str,
        resource: str,
        detail: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Record an action in the audit logs DynamoDB table.
        Primary Key: log_date (YYYY-MM-DD)
        Sort Key: ts_id ({timestamp}#{uuid})
        """
        now = datetime.now(timezone.utc)
        log_date = format_date(now)
        timestamp = now.isoformat()
        unique_id = uuid.uuid4().hex[:8]
        ts_id = f"{timestamp}#{unique_id}"

        if ip_address is None:
            try:
                if request:
                    ip_address = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
            except RuntimeError:
                ip_address = "system"

        item = {
            "log_date": log_date,
            "ts_id": ts_id,
            "actor": actor,
            "action": action,
            "resource": resource,
            "detail": detail or "",
            "ip_address": ip_address,
            "timestamp": timestamp,
        }

        try:
            self.dynamo.put_item(self.table_name, item)
            logger.info("AUDIT: [%s] by %s on %s - %s", action, actor, resource, detail)
            return item
        except Exception as e:
            logger.error("Failed to persist audit log: %s", e)
            return item

    def get_logs_by_date(self, log_date: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Query audit logs for a specific date (YYYY-MM-DD), newest first."""
        from boto3.dynamodb.conditions import Key
        try:
            items = self.dynamo.query(
                table_name=self.table_name,
                key_condition_expression=Key("log_date").eq(log_date),
                scan_index_forward=False,
                limit=limit,
            )
            return items
        except Exception as e:
            logger.error("Failed to query audit logs for date %s: %s", log_date, e)
            return []


_audit_service_instance: Optional[AuditService] = None


def get_audit_service() -> AuditService:
    """Return singleton AuditService instance."""
    global _audit_service_instance
    if _audit_service_instance is None:
        _audit_service_instance = AuditService()
    return _audit_service_instance


def log_action(actor: str, action: str, resource: str, detail: Optional[str] = None, ip_address: Optional[str] = None):
    """Convenience helper to record an audit action."""
    service = get_audit_service()
    return service.log(actor=actor, action=action, resource=resource, detail=detail, ip_address=ip_address)
