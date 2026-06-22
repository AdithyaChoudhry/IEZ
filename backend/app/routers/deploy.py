"""
Deploy webhook — called by GitHub Actions on push to main.
Pulls latest code, rebuilds the frontend, then restarts the service.
"""
import hashlib
import hmac
import os
import subprocess
import logging

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Request
from sqlalchemy.orm import Session

from ..deps import get_db
from fastapi import Depends

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
    import time, signal
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

    # os._exit(1) → process exits with non-zero code → systemd Restart=on-failure kicks in
    logger.info("Triggering restart via os._exit(1)")
    os._exit(1)


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
         f"cd {REPO_ROOT} && git pull origin main && pip3 install -q -r backend/requirements.txt; cd frontend && npm run build"],
        capture_output=True, text=True, timeout=300,
    )

    if result.returncode != 0:
        logger.error("Deploy failed: %s", result.stderr)
        raise HTTPException(status_code=500, detail=result.stderr[-500:])

    logger.info("Deploy succeeded: %s", result.stdout[-200:])

    # Restart backend in background so this response can return first
    background_tasks.add_task(_restart_service)

    return {"status": "ok", "output": result.stdout[-500:]}


@router.post("/seed-admin")
def seed_admin(key: str = Query(...), db: Session = Depends(get_db)):
    """One-time endpoint: create the ADMIN001 AdminUser if missing. Protected by DEPLOY_SECRET."""
    if not DEPLOY_SECRET or key != DEPLOY_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    from ..auth.models import AdminUser, User
    from ..auth.utils import get_password_hash

    result = {}

    # Create AdminUser if missing
    if not db.query(AdminUser).filter(AdminUser.employee_id == "ADMIN001").first():
        pw_hash = get_password_hash("Admin@iez2024")
        db.add(AdminUser(
            employee_id="ADMIN001",
            employee_name="System Admin",
            designation="System Administrator",
            department="IT",
            email_id="admin@iez.co.in",
            password_hash=pw_hash,
            role="Admin",
            status="active",
        ))
        result["admin_user"] = "created"
    else:
        result["admin_user"] = "already exists"

    # Ensure JWT User exists
    if not db.query(User).filter(User.email == "admin@iez.co.in").first():
        pw_hash = get_password_hash("Admin@iez2024")
        db.add(User(
            email="admin@iez.co.in",
            username="admin",
            hashed_password=pw_hash,
            is_active=True,
        ))
        result["jwt_user"] = "created"
    else:
        # Update existing JWT user's password to match
        u = db.query(User).filter(User.email == "admin@iez.co.in").first()
        u.hashed_password = get_password_hash("Admin@iez2024")
        result["jwt_user"] = "password synced"

    db.commit()
    return {"status": "ok", **result}
