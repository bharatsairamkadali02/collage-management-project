"""
WSGI and Socket.IO entry point for College Management System backend.
Supports Eventlet async worker with Gunicorn or direct execution.
"""
import os
from dotenv import load_dotenv

# Load environment variables before initializing the application
load_dotenv()

from app import create_app
from app.extensions import socketio

app = create_app(os.getenv("FLASK_ENV", "development"))

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "0").lower() in ("1", "true", "yes")
    socketio.run(app, host=host, port=port, debug=debug)
