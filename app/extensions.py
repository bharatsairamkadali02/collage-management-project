"""
Shared Flask extension instances.
Prevents circular import dependencies across models, services, and routes.
"""
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_socketio import SocketIO

bcrypt = Bcrypt()
login_manager = LoginManager()
socketio = SocketIO()
