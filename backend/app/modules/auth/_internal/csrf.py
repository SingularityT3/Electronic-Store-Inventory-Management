"""CSRF protection for state-changing requests (SEC-SES-4).

Double-submit token: login sets a readable `esims_csrf` cookie and the web app echoes it in
the `X-CSRF-Token` header. A page on another site can make the browser send the cookies but
cannot read this one, so it cannot supply a matching header.
"""

import secrets

from fastapi import HTTPException, Request, Response, status

CSRF_COOKIE = "esims_csrf"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def set_csrf_cookie(response: Response, secure: bool) -> None:
    response.set_cookie(
        CSRF_COOKIE,
        secrets.token_urlsafe(32),
        httponly=False,  # the web app must read it to echo it in the header
        secure=secure,
        samesite="strict",
        path="/",
    )


def clear_csrf_cookie(response: Response) -> None:
    response.delete_cookie(CSRF_COOKIE, path="/")


def csrf_protect_except(public_paths: set[str]):
    """Dependency: reject unsafe-method requests whose header does not match the cookie.

    `public_paths` have no session to forge (login, password reset), so they are exempt.
    """

    def csrf_protect(request: Request) -> None:
        if request.method in SAFE_METHODS or request.url.path in public_paths:
            return
        cookie = request.cookies.get(CSRF_COOKIE)
        header = request.headers.get(CSRF_HEADER)
        if not cookie or not header or not secrets.compare_digest(cookie, header):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing or invalid CSRF token")

    return csrf_protect
