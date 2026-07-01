from fastapi.responses import JSONResponse

from utils.serialization import serialize_for_json


def api_success(
    data=None,
    message: str = "ok",
    warnings: list[str] | None = None,
    meta: dict | None = None,
    status_code: int = 200,
):
    """Return a standardized successful API response."""
    body = {
        "ok": True,
        "message": message,
        "data": serialize_for_json(data),
        "warnings": serialize_for_json(warnings or []),
        "meta": serialize_for_json(meta or {}),
    }
    if status_code != 200:
        return JSONResponse(status_code=status_code, content=body)
    return body


def api_error(
    message: str,
    *,
    status_code: int = 400,
    data=None,
    warnings: list[str] | None = None,
    meta: dict | None = None,
    error_code: str | None = None,
):
    """Return a standardized failed API response."""
    body = {
        "ok": False,
        "message": message,
        "data": serialize_for_json(data),
        "warnings": serialize_for_json(warnings or []),
        "meta": serialize_for_json(meta or {}),
    }
    if error_code:
        body["error_code"] = error_code
    return JSONResponse(status_code=status_code, content=body)