"""Verified HTTPS requests pinned to TLS 1.2 for current GitHub network needs."""

import ssl
from urllib.error import HTTPError, URLError
from urllib.request import HTTPSHandler, Request, build_opener

import truststore

MAX_RESPONSE_BYTES = 2_000_000


class HTTPRequestError(RuntimeError):
    """Sanitized HTTPS failure."""


def json_request(url: str, *, method: str = "GET", headers: dict | None = None,
                 payload: dict | None = None, timeout: int = 30) -> tuple[int, bytes, dict]:
    context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.maximum_version = ssl.TLSVersion.TLSv1_2
    request_headers = {"Accept": "application/json", "User-Agent": "research-agent"}
    if headers:
        request_headers.update(headers)
    data = None
    if payload is not None:
        import json

        data = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=request_headers, method=method)
    try:
        with build_opener(HTTPSHandler(context=context)).open(request, timeout=timeout) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise HTTPRequestError("HTTPS response exceeded the size limit.")
            return response.status, body, dict(response.headers.items())
    except HTTPError as error:
        raise HTTPRequestError(f"HTTPS request returned HTTP {error.code}.") from None
    except (URLError, TimeoutError, ssl.SSLError, OSError):
        raise HTTPRequestError("HTTPS request failed during TLS or network communication.") from None
