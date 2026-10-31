import ssl
import unittest
from unittest.mock import patch

from research_agent import http


class _Response:
    status = 200
    headers = {"Content-Type": "application/json"}

    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return self.body[:size]


class HTTPSClientTests(unittest.TestCase):
    def test_request_pins_tls_12_and_keeps_certificate_validation(self):
        with patch.object(http, "build_opener") as build_opener:
            build_opener.return_value.open.return_value = _Response(b'{"ok":true}')
            status, body, _ = http.json_request("https://api.github.com/user")

        context = build_opener.call_args.args[0]._context
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        self.assertEqual(context.maximum_version, ssl.TLSVersion.TLSv1_2)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertEqual((status, body), (200, b'{"ok":true}'))

    def test_response_body_is_bounded(self):
        with patch.object(http, "MAX_RESPONSE_BYTES", 4), patch.object(
            http, "build_opener"
        ) as build_opener:
            build_opener.return_value.open.return_value = _Response(b"12345")
            with self.assertRaisesRegex(http.HTTPRequestError, "size limit"):
                http.json_request("https://api.github.com/user")


if __name__ == "__main__":
    unittest.main()
