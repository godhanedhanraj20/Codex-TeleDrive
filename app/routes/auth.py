"""Auth routes for TeleDrive (Milestone 4)."""

from __future__ import annotations

import traceback

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter()


class SendCodeRequest(BaseModel):
    phone: str


class SignInRequest(BaseModel):
    phone: str
    phone_code_hash: str
    code: str


class CheckPasswordRequest(BaseModel):
    password: str


def _error_response(error_code: str, message: str, technical: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error_code": error_code,
            "message": message,
            "technical": technical,
        },
    )


@router.post("/send-code")
async def send_code(payload: SendCodeRequest, request: Request) -> JSONResponse:
    telegram_client = request.app.state.telegram_client

    try:
        if not telegram_client.started:
            await telegram_client.start()

        sent = await telegram_client.send_code(payload.phone)
        return JSONResponse({"status": "code_sent", "phone": payload.phone, "phone_code_hash": sent["phone_code_hash"]})
    except Exception as exc:
        return _error_response(
            error_code="AUTH_SEND_CODE_FAILED",
            message="Failed to send Telegram login code.",
            technical=f"{exc}\n{traceback.format_exc()}",
            status_code=500,
        )


@router.post("/sign-in")
async def sign_in(payload: SignInRequest, request: Request) -> JSONResponse:
    telegram_client = request.app.state.telegram_client

    try:
        if not telegram_client.started:
            await telegram_client.start()

        result = await telegram_client.sign_in(
            phone=payload.phone,
            phone_code_hash=payload.phone_code_hash,
            code=payload.code,
        )
        return JSONResponse(result)
    except Exception as exc:
        return _error_response(
            error_code="AUTH_SIGN_IN_FAILED",
            message="Telegram sign-in failed.",
            technical=f"{exc}\n{traceback.format_exc()}",
            status_code=500,
        )


@router.post("/check-password")
async def check_password(payload: CheckPasswordRequest, request: Request) -> JSONResponse:
    telegram_client = request.app.state.telegram_client

    try:
        if not telegram_client.started:
            await telegram_client.start()

        result = await telegram_client.check_password(payload.password)
        return JSONResponse(result)
    except Exception as exc:
        return _error_response(
            error_code="AUTH_CHECK_PASSWORD_FAILED",
            message="Telegram 2FA password check failed.",
            technical=f"{exc}\n{traceback.format_exc()}",
            status_code=500,
        )


@router.get("/status")
async def auth_status(request: Request) -> JSONResponse:
    telegram_client = request.app.state.telegram_client

    try:
        status = await telegram_client.get_status()
        return JSONResponse(status)
    except Exception as exc:
        return _error_response(
            error_code="AUTH_STATUS_FAILED",
            message="Failed to fetch Telegram auth status.",
            technical=f"{exc}\n{traceback.format_exc()}",
            status_code=500,
        )
