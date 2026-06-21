"""
Deploy webhook — called by GitHub Actions on push to main.
Pulls latest code, rebuilds the frontend, then restarts the service.
"""
import hashlib
import hmac
import os
import subprocess
import logging
import asyncio

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/deploy", tags=["Deploy"])

DEPLOY_SECRET = os.environ.get("DEPLOY_SECRET", "")
REPO_ROOT = "/var/www/iez"


def _verify(secret: str, body: bytes, sig_header: str) -> bool:
    if not secret:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig_header or "")


def _restart_service():
    """Run in background AFTER the HTTP response is sent."""
    import time, signal, os
    time.sleep(4)  # let the response flush

    # Try systemctl (works if sudo is passwordless for this user)
    try:
        r = subprocess.run(["sudo", "systemctl", "restart", "iez.service"],
                           capture_output=True, timeout=10)
        if r.returncode == 0:
            logger.info("Service restarted via systemctl")
            return
        logger.warning("systemctl failed: %s", r.stderr)
    except Exception as e:
        logger.warning("systemctl exception: %s", e)

    # Fallback: SIGTERM self — systemd restarts if Restart=on-failure/always
    logger.info("Falling back to self-SIGTERM")
    try:
        os.kill(os.getpid(), signal.SIGTERM)
    except Exception as e:
        logger.error("Restart failed: %s", e)


@router.post("")
async def webhook(
    request: Request,
    background_tasks: BackgroundTasks,
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

    # Restart backend in background so this response can return first
    background_tasks.add_task(_restart_service)

    return {"status": "ok", "output": result.stdout[-500:]}
