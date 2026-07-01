import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, Request, UploadFile

from whitespace.api.models import JobResponse
from whitespace.domain import JobStatus
from whitespace.middleware.auth import CurrentUser, get_current_user
from whitespace.middleware.usage import check_usage
from whitespace.queue.base import JobQueue

logger = logging.getLogger(__name__)
router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".csv", ".xlsx"}


@router.post("/profile", response_model=JobResponse)
async def upload_profile(
    files: list[UploadFile],
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    _usage: None = Depends(check_usage),
) -> JobResponse:
    """Accept professional document uploads, enqueue profile extraction."""
    logger.info(
        "Profile upload: %d files from user=%s",
        len(files),
        user.user_id,
    )

    saved_paths: list[str] = []
    for upload in files:
        filename = upload.filename or "upload"
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            logger.warning("Skipping unsupported file type: %s", filename)
            continue

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=ext,
            prefix="ws_profile_",
        ) as tmp:
            content = await upload.read()
            tmp.write(content)
            saved_paths.append(tmp.name)

    queue: JobQueue = request.app.state.queue
    job_id = await queue.enqueue(
        "profile_extraction",
        {"doc_paths": saved_paths},
    )
    return JobResponse(job_id=job_id, status=JobStatus.PENDING)
