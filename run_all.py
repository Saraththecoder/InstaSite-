import os
import sys
import subprocess
import threading
import time

def start_bot():
    """Runs the Telegram bot polling process with auto-restart and diagnostics."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("=" * 60, file=sys.stderr)
        print("❌ CRITICAL: TELEGRAM_BOT_TOKEN is NOT set in Environment!", file=sys.stderr)
        print("Please add TELEGRAM_BOT_TOKEN in Render Dashboard -> Environment", file=sys.stderr)
        print("=" * 60, file=sys.stderr)

    while True:
        print("Starting DukaanMitra Telegram Bot...")
        result = subprocess.run([sys.executable, "-m", "app.bot"])
        print(f"⚠️ Telegram Bot exited with return code: {result.returncode}. Retrying in 5 seconds...", file=sys.stderr)
        time.sleep(5)

def start_server():
    """Runs the FastAPI uvicorn web server."""
    port = os.getenv("PORT", "8000")
    print(f"Starting DukaanMitra Web Server on port {port}...")
    subprocess.run([
        sys.executable,
        "-m",
        "uvicorn",
        "app.server:app",
        "--host",
        "0.0.0.0",
        "--port",
        str(port),
    ])

if __name__ == "__main__":
    # Start bot in a background thread
    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()
    
    # Give the bot half a second to initialize
    time.sleep(1)
    
    # Start the web server (keeps the main thread alive)
    start_server()
