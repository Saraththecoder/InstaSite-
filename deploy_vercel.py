import os
import sys
import base64
import httpx
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.config import require_vercel_token, BASE_DIR

VERCEL_API_URL = "https://api.vercel.com/v13/deployments"


def deploy_to_vercel(project_name: str = "dukaanmitra-store") -> str:
    """
    Deploys the static storefronts directly to Vercel using the VERCEL_TOKEN via REST API.
    Returns the live production URL.
    """
    token = require_vercel_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # 1. Verify token
    print("🔑 Verifying Vercel Token...")
    with httpx.Client(timeout=15.0) as client:
        user_res = client.get("https://api.vercel.com/v2/user", headers={"Authorization": f"Bearer {token}"})
        if user_res.status_code != 200:
            raise ValueError(f"Invalid VERCEL_TOKEN (HTTP {user_res.status_code}): {user_res.text}")
        user_data = user_res.json().get("user", {})
        print(f"✓ Authenticated as: {user_data.get('username') or user_data.get('email')}")

        # Ensure SSO protection is disabled so stores are publicly viewable
        try:
            client.patch(
                f"https://api.vercel.com/v9/projects/{project_name}",
                headers=headers,
                json={"ssoProtection": None}
            )
        except Exception as e:
            print(f"Warning: Could not patch SSO protection: {e}")

    # 2. Collect files to deploy
    print("📦 Packing storefront files for Vercel...")
    files_payload = []

    static_store_dir = BASE_DIR / "static" / "store"
    static_images_dir = BASE_DIR / "static" / "images"

    # Add all generated stores
    if static_store_dir.exists():
        for file_path in static_store_dir.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(BASE_DIR / "static").as_posix()
                content = file_path.read_text(encoding="utf-8")
                files_payload.append({
                    "file": rel_path,
                    "data": content
                })

    # Add all images (placeholder, uploaded product photos, etc.)
    if static_images_dir.exists():
        for img_path in static_images_dir.rglob("*"):
            if img_path.is_file():
                rel_path = img_path.relative_to(BASE_DIR / "static").as_posix()
                if img_path.suffix.lower() in [".svg", ".txt", ".json", ".html"]:
                    files_payload.append({
                        "file": rel_path,
                        "data": img_path.read_text(encoding="utf-8")
                    })
                else:
                    files_payload.append({
                        "file": rel_path,
                        "data": base64.b64encode(img_path.read_bytes()).decode("utf-8"),
                        "encoding": "base64"
                    })

    # Add root index.html to list all stores or redirect to first store
    stores = [d.name for d in static_store_dir.iterdir() if d.is_dir()] if static_store_dir.exists() else []
    links_html = "".join(f'<li class="py-3"><a href="/store/{s}/" class="text-orange-600 font-bold text-xl hover:underline">🏪 {s.replace("-", " ").title()}</a></li>' for s in stores)
    root_index = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>DukaanMitra AI - Live Storefronts</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-stone-50 text-stone-900 min-h-screen p-8 max-w-3xl mx-auto font-sans">
  <div class="bg-white rounded-3xl p-8 border border-stone-200 shadow-sm mt-10">
    <div class="flex items-center gap-3 mb-6">
      <span class="text-4xl">🇮🇳</span>
      <div>
        <h1 class="text-2xl font-extrabold text-stone-900">DukaanMitra AI Storefronts</h1>
        <p class="text-stone-500 text-sm">Deployed live on Vercel</p>
      </div>
    </div>
    <hr class="border-stone-200 mb-6">
    <h2 class="text-base font-bold text-stone-700 uppercase tracking-wider mb-4">Active Digital Storefronts</h2>
    <ul class="divide-y divide-stone-100">{links_html}</ul>
  </div>
</body>
</html>"""
    files_payload.append({
        "file": "index.html",
        "data": root_index
    })

    # Also add vercel.json rewrite rules for clean store URLs
    vercel_cfg = """{
  "cleanUrls": true,
  "rewrites": [
    { "source": "/store/:slug", "destination": "/store/:slug/index.html" },
    { "source": "/static/images/:path*", "destination": "/images/:path*" }
  ]
}"""
    files_payload.append({
        "file": "vercel.json",
        "data": vercel_cfg
    })

    print(f"✓ Uploading {len(files_payload)} files to Vercel API...")

    payload = {
        "name": project_name,
        "target": "production",
        "files": files_payload,
        "projectSettings": {
            "framework": None
        }
    }

    with httpx.Client(timeout=60.0) as client:
        res = client.post(VERCEL_API_URL, headers=headers, json=payload)
        if res.status_code not in [200, 201]:
            raise RuntimeError(f"Vercel Deployment Failed (HTTP {res.status_code}): {res.text}")

        data = res.json()
        aliases = data.get("alias", [])
        if aliases:
            deployment_url = f"https://{aliases[0]}"
        else:
            raw_url = data.get("url")
            deployment_url = f"https://{raw_url}"

        print(f"\n🎉 DEPLOYMENT SUCCESSFUL!")
        print(f"👉 Live URL: {deployment_url}")
        for s in stores:
            print(f"👉 Store '{s}': {deployment_url}/store/{s}/")

        return deployment_url


if __name__ == "__main__":
    try:
        url = deploy_to_vercel()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
