"""Queue routes for TeleDrive (Milestone 8)."""

from __future__ import annotations

import traceback

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import db

router = APIRouter()


def _error_response(error_code: str, message: str, technical: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error_code": error_code,
            "message": message,
            "technical": technical,
        },
    )


@router.get("")
def list_queue(request: Request) -> JSONResponse:
    try:
        jobs = db.list_jobs(request.app.state.db_conn)
        return JSONResponse({"items": jobs})
    except Exception as exc:
        return _error_response(
            error_code="QUEUE_LIST_FAILED",
            message="Failed to list queue jobs.",
            technical=f"{exc}\n{traceback.format_exc()}",
            status_code=500,
        )


@router.post("/{job_id}/retry")
async def retry_queue_job(job_id: int, request: Request) -> JSONResponse:
    queue_worker = request.app.state.queue_worker
    db_conn = request.app.state.db_conn

    try:
        job = db.get_job_by_id(db_conn, job_id)
        if job is None:
            return _error_response(
                error_code="JOB_NOT_FOUND",
                message="Queue job not found.",
                technical=f"job_id={job_id}",
                status_code=404,
            )

        if job["status"] != "failed":
            return _error_response(
                error_code="JOB_RETRY_INVALID_STATE",
                message="Only failed jobs can be retried.",
                technical=f"job_id={job_id} status={job['status']}",
                status_code=400,
            )

        await queue_worker.retry_failed_job(job_id)
        updated = db.get_job_by_id(db_conn, job_id)
        return JSONResponse({"status": "queued", "job": updated})
    except Exception as exc:
        return _error_response(
            error_code="JOB_RETRY_FAILED",
            message="Failed to retry queue job.",
            technical=f"{exc}\n{traceback.format_exc()}",
            status_code=500,
        )
