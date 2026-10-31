"""
Socket.IO event handlers and broadcasting helpers.
Enables real-time push notifications for attendance, results, exams, and active user tracking.
"""
import logging
from typing import Any, Dict
from flask import request
from flask_login import current_user
from flask_socketio import emit, join_room, leave_room

from app.extensions import socketio

logger = logging.getLogger(__name__)

# In-memory mapping of active socket sessions: { sid: { "username": ..., "role": ... } }
connected_clients: Dict[str, Dict[str, Any]] = {}


def get_online_users_stats() -> Dict[str, Any]:
    """Calculate current online user counts broken down by role."""
    counts = {"admin": 0, "faculty": 0, "student": 0, "anonymous": 0}
    for client in connected_clients.values():
        role = client.get("role", "anonymous")
        if role in counts:
            counts[role] += 1
        else:
            counts["anonymous"] += 1
    counts["total"] = len(connected_clients)
    return counts


def register_socket_events(sio):
    """Register all Socket.IO listeners."""

    @sio.on("connect")
    def handle_connect(auth=None):
        sid = request.sid
        username = "guest"
        role = "anonymous"

        if current_user and current_user.is_authenticated:
            username = current_user.username
            role = current_user.role
        elif isinstance(auth, dict) and "username" in auth:
            username = auth.get("username", "guest")
            role = auth.get("role", "anonymous")

        connected_clients[sid] = {
            "username": username,
            "role": role,
        }

        # Join role-based room for targeted broadcasts
        join_room(f"role_{role}")
        logger.info("Socket connected: sid=%s, user=%s, role=%s", sid, username, role)

        # Broadcast updated active users summary to all connected clients
        emit("online_users", get_online_users_stats(), broadcast=True)

    @sio.on("disconnect")
    def handle_disconnect():
        sid = request.sid
        user_info = connected_clients.pop(sid, None)
        if user_info:
            role = user_info.get("role", "anonymous")
            leave_room(f"role_{role}")
            logger.info("Socket disconnected: sid=%s, user=%s", sid, user_info.get("username"))

        # Broadcast updated active users summary
        emit("online_users", get_online_users_stats(), broadcast=True)

    @sio.on("join_exam")
    def handle_join_exam(data):
        """Allow a student or faculty to join a specific exam room for real-time exam alerts."""
        exam_id = data.get("exam_id") if isinstance(data, dict) else None
        if exam_id:
            join_room(f"exam_{exam_id}")
            logger.info("Socket %s joined exam room exam_%s", request.sid, exam_id)
            emit("exam_joined", {"exam_id": exam_id, "status": "joined"})

    @sio.on("leave_exam")
    def handle_leave_exam(data):
        exam_id = data.get("exam_id") if isinstance(data, dict) else None
        if exam_id:
            leave_room(f"exam_{exam_id}")
            emit("exam_left", {"exam_id": exam_id, "status": "left"})


def emit_attendance_update(data: Dict[str, Any]) -> None:
    """Broadcast attendance changes to interested clients."""
    try:
        socketio.emit("attendance_updated", data)
    except Exception as e:
        logger.warning("Failed to emit attendance_updated event: %s", e)


def emit_result_update(data: Dict[str, Any]) -> None:
    """Broadcast examination/assessment result changes."""
    try:
        # Also emit to student-specific channel if student_id is present
        student_id = data.get("student_id")
        if student_id:
            socketio.emit(f"student_result_{student_id}", data)
        socketio.emit("result_updated", data)
    except Exception as e:
        logger.warning("Failed to emit result_updated event: %s", e)


def emit_exam_status_changed(data: Dict[str, Any]) -> None:
    """Broadcast exam status transition (draft -> open -> closed)."""
    try:
        exam_id = data.get("exam_id")
        if exam_id:
            socketio.emit("exam_status_changed", data, room=f"exam_{exam_id}")
        socketio.emit("exam_status_changed", data)
    except Exception as e:
        logger.warning("Failed to emit exam_status_changed event: %s", e)


def emit_dashboard_stats(data: Dict[str, Any]) -> None:
    """Broadcast global metrics update to administrative and faculty listeners."""
    try:
        socketio.emit("dashboard_stats", data)
    except Exception as e:
        logger.warning("Failed to emit dashboard_stats event: %s", e)
