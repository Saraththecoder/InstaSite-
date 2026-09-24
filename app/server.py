import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, Response

from app.config import BASE_DIR
from app.db.database import SessionLocal, init_db
from app.db.models import Business

# Ensure static directories exist
STATIC_DIR = BASE_DIR / "static"
STATIC_STORE_DIR = STATIC_DIR / "store"
STATIC_IMAGES_DIR = STATIC_DIR / "images"

STATIC_STORE_DIR.mkdir(parents=True, exist_ok=True)
STATIC_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# Initialize database
init_db()

app = FastAPI(title="DukaanMitra AI", description="Voice-First Digital Storefront for Indian Micro-Businesses")

# Mount static assets (images, css, etc.)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Mount generated static storefronts at /store
app.mount("/store", StaticFiles(directory=STATIC_STORE_DIR, html=True), name="store")


@app.api_route("/health", methods=["GET", "HEAD"])
def health():
    return {"status": "ok", "service": "DukaanMitra AI"}


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
def home():
    session = SessionLocal()
    try:
        businesses = session.query(Business).order_by(Business.business_id.desc()).all()
        biz_links = "".join(
            f'<li class="py-2"><a href="/store/{b.slug}" class="text-orange-600 hover:underline font-semibold text-lg">{b.business_name}</a> <span class="text-stone-500 text-sm">({b.category})</span></li>'
            for b in businesses
        )
        if not biz_links:
            biz_links = '<li class="text-stone-400 py-4">No storefronts created yet. Send a voice message to the Telegram bot!</li>'

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>DukaanMitra AI - Server</title>
            <script src="https://cdn.tailwindcss.com"></script>
        </head>
        <body class="bg-stone-50 text-stone-900 p-8 max-w-4xl mx-auto font-sans">
            <div class="bg-white rounded-2xl p-8 border border-stone-200 shadow-sm">
                <div class="flex items-center gap-3 mb-6">
                    <span class="text-4xl">🏪</span>
                    <div>
                        <h1 class="text-2xl font-bold">DukaanMitra AI Server</h1>
                        <p class="text-stone-500 text-sm">Voice-First Storefront Generation Active</p>
                    </div>
                </div>
                <hr class="border-stone-200 mb-6"/>
                <h2 class="text-lg font-bold mb-3">Live Storefronts</h2>
                <ul class="divide-y divide-stone-100">{biz_links}</ul>
            </div>
        </body>
        </html>
        """
    finally:
        session.close()
