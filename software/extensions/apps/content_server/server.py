"""
Dissertation Content Server - Flask backend + Vite frontend.
"""

import os
import subprocess
import atexit

from backend.app import create_app

BASE_DIR = os.path.dirname(__file__)
FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend')
CONTENT_DIR = os.path.join(BASE_DIR, 'content')

# Vite process reference
vite_process = None


def start_vite_dev_server(port=9300, host="localhost"):
    """Start the Vite development server"""
    global vite_process

    if not os.path.isdir(FRONTEND_DIR):
        print(f"Frontend directory not found: {FRONTEND_DIR}")
        return None

    if not os.path.isfile(os.path.join(FRONTEND_DIR, "package.json")):
        print(f"No package.json found in: {FRONTEND_DIR}")
        return None

    command = ["npm", "run", "dev", "--", "--port", str(port), "--host", host]

    vite_process = subprocess.Popen(
        command,
        cwd=FRONTEND_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    print(f"Vite dev server starting at http://{host}:{port}/ (PID: {vite_process.pid})")
    return vite_process


def stop_vite_dev_server():
    """Stop the Vite development server"""
    global vite_process
    if vite_process:
        vite_process.terminate()
        vite_process.wait()
        print("Vite dev server stopped")


if __name__ == '__main__':
    print(f"Content directory: {CONTENT_DIR}")

    app = create_app(CONTENT_DIR)

    # Start Vite dev server
    start_vite_dev_server(port=9300, host="0.0.0.0")
    atexit.register(stop_vite_dev_server)

    # Start Flask server
    app.run(host='0.0.0.0', port=5050, debug=True, use_reloader=False)
