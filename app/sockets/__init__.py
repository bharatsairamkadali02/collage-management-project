"""
Sockets package initialization.
"""
from app.sockets.events import (
    register_socket_events,
    emit_attendance_update,
    emit_result_update,
    emit_exam_status_changed,
    emit_dashboard_stats,
    get_online_users_stats,
)

__all__ = [
    "register_socket_events",
    "emit_attendance_update",
    "emit_result_update",
    "emit_exam_status_changed",
    "emit_dashboard_stats",
    "get_online_users_stats",
]
