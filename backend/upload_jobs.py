"""
In-memory upload job state for async GDD and Code uploads.
Used by app.py to track progress and results without changing behavior.
"""

import threading
import uuid

# Global dict: job_id -> progress info
UPLOAD_JOBS = {}
JOBS_LOCK = threading.Lock()


def new_job():
    """Create a new upload job and return its id."""
    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        UPLOAD_JOBS[job_id] = {
            "status": "running",
            "step": "Uploading file",
            "message": "",
            "doc_id": None,
            "chunks_count": None,
        }
    return job_id


def update_job(
    job_id,
    step=None,
    status=None,
    message=None,
    doc_id=None,
    chunks_count=None,
):
    """Update progress for an upload job."""
    with JOBS_LOCK:
        job = UPLOAD_JOBS.get(job_id)
        if not job:
            return
        if step is not None:
            job["step"] = step
        if status is not None:
            job["status"] = status
        if message is not None:
            job["message"] = message
        if doc_id is not None:
            job["doc_id"] = doc_id
        if chunks_count is not None:
            job["chunks_count"] = chunks_count


def get_job(job_id):
    """Return current job state or None."""
    with JOBS_LOCK:
        return UPLOAD_JOBS.get(job_id)
