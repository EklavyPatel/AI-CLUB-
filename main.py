"""Vercel entrypoint: Cloudflare D1 in production, existing SQLAlchemy app locally."""
import os
from dotenv import load_dotenv

load_dotenv()
if os.getenv('D1_GATEWAY_URL'):
    from app.gateway import app
else:
    from app.main import app
