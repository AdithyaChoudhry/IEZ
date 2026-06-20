"""
Deploy webhook — called by GitHub Actions on push to main.
Pulls latest code and rebuilds the frontend.
"""
import hashlib
import hmac
import os
import subprocess
import logging

from fastapi import APIRouter, Header, HTTPException, Request

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/deploy", tags=["Deploy"])

DEPLOY_SECRET = os.environ.get("DEPLOY_SECRET", "")
REPO_ROOT = "/var/www/iez"


def _verify(secret: str, body: bytes, sig_header: str) -> bool:
    if not secret:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig_header or "")


@router.post("")
async def webhook(
    request: Request,
    x_hub_signature_256: str = Header(default=""),
):
    body = await request.body()

    if DEPLOY_SECRET and not _verify(DEPLOY_SECRET, body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")

    logger.info("Deploy webhook triggered — pulling and building")

    result = subprocess.run(
        ["bash", "-c",
         f"cd {REPO_ROOT} && git pull origin main && cd frontend && npm run build"],
        capture_output=True, text=True, timeout=300,
    )

    if result.returncode != 0:
        logger.error("Deploy failed: %s", result.stderr)
        raise HTTPException(status_code=500, detail=result.stderr[-500:])

    logger.info("Deploy succeeded: %s", result.stdout[-200:])
    return {"status": "ok", "output": result.stdout[-500:]}
