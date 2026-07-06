import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

from whitespace.api.models import JobResponse
from whitespace.domain import JobStatus
from whitespace.middleware.auth import CurrentUser, get_current_user
from whitespace.middleware.usage import check_usage
from whitespace.queue.base import JobQueue

logger = logging.getLogger(__name__)
router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".csv", ".xlsx"}


async def _save_uploads(uploads: list[UploadFile], prefix: str) -> list[str]:
    paths: list[str] = []
    for upload in uploads:
        filename = upload.filename or "upload"
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            logger.warning("Skipping unsupported file type: %s", filename)
            continue
        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=ext,
            prefix=f"ws_{prefix}_",
        ) as tmp:
            content = await upload.read()
            tmp.write(content)
            paths.append(tmp.name)
    return paths


@router.post("/ingest", response_model=JobResponse)
async def trigger_ingest(
    request: Request,
    domain: str = Form(...),
    cpc_class: str | None = Form(None),
    profile_files: list[UploadFile] = File(default=[]),
    domain_files: list[UploadFile] = File(default=[]),
    user: CurrentUser = Depends(get_current_user),
    _usage: None = Depends(check_usage),
) -> JobResponse:
    logger.info("Ingest requested by user=%s domain=%s", user.user_id, domain)

    profile_paths = await _save_uploads(profile_files, "profile")
    domain_paths = await _save_uploads(domain_files, "domain")

    queue: JobQueue = request.app.state.queue
    job_id = await queue.enqueue(
        "ingest",
        {
            "domain_keywords": [kw.strip() for kw in domain.split(",") if kw.strip()],
            "cpc_classes": [cpc_class] if cpc_class else [],
            "profile_paths": profile_paths,
            "domain_paths": domain_paths,
        },
    )
    return JobResponse(job_id=job_id, status=JobStatus.PENDING)
