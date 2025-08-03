"""Flask wrapper for the FastAPI application."""

from app.main import app as fastapi_app
from flask import Flask
import uvicorn
import threading
import time

# Create Flask app for deployment compatibility
flask_app = Flask(__name__)

# Start FastAPI in a separate thread
def start_fastapi():
    uvicorn.run(fastapi_app, host="0.0.0.0", port=8000)

# Start FastAPI server
fastapi_thread = threading.Thread(target=start_fastapi, daemon=True)
fastapi_thread.start()

# Give FastAPI time to start
time.sleep(2)

@flask_app.route('/')
def index():
    return """
    <html>
    <head>
        <meta http-equiv="refresh" content="0; url=http://localhost:8000">
    </head>
    <body>
        <p>Redirecting to FastAPI application...</p>
        <p>If you are not redirected, <a href="http://localhost:8000">click here</a>.</p>
    </body>
    </html>
    """

if __name__ == '__main__':
    flask_app.run(host='0.0.0.0', port=5000)

