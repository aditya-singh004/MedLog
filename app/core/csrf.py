import secrets

from fastapi import HTTPException, Request


CSRF_COOKIE_NAME = "csrf_token"
CSRF_FORM_FIELD = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
PUBLIC_AUTH_PATHS = {"/api/auth/login", "/api/auth/register"}


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def tokens_match(submitted: str | None, cookie: str | None) -> bool:
    return bool(submitted and cookie and secrets.compare_digest(submitted, cookie))


async def validate_web_csrf(request: Request) -> None:
    """Protect cookie-authenticated HTML form submissions."""
    if request.method.upper() in SAFE_METHODS:
        return
    if request.url.path in PUBLIC_AUTH_PATHS:
        return
    form = await request.form()
    if not tokens_match(str(form.get(CSRF_FORM_FIELD, "")), request.cookies.get(CSRF_COOKIE_NAME)):
        raise HTTPException(status_code=403, detail="Security token is missing or expired. Refresh the page and try again.")


async def validate_api_csrf(request: Request) -> None:
    """Protect API mutations that authenticate through the browser cookie.

    API clients using an Authorization bearer token are not vulnerable to
    browser cookie CSRF and therefore do not need this additional token.
    """
    if request.method.upper() in SAFE_METHODS:
        return
    if request.url.path in PUBLIC_AUTH_PATHS:
        return
    if request.headers.get("Authorization", "").lower().startswith("bearer "):
        return
    if not request.cookies.get("access_token"):
        return
    if not tokens_match(request.headers.get(CSRF_HEADER_NAME), request.cookies.get(CSRF_COOKIE_NAME)):
        raise HTTPException(status_code=403, detail="Valid X-CSRF-Token header required")
