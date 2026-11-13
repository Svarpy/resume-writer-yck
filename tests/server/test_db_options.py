import os
import unittest
from unittest import mock

from resume_server.db import client_options


class ConnectionOptionTests(unittest.TestCase):
    def test_srv_uri_verifies_against_the_certifi_bundle(self) -> None:
        import certifi
        with mock.patch.dict(os.environ, {"MONGODB_TLS_CA_FILE": ""}):
            self.assertEqual(client_options("mongodb+srv://u:p@c.example.mongodb.net/")["tlsCAFile"], certifi.where())

    def test_plain_uri_does_not_switch_tls_on(self) -> None:
        self.assertNotIn("tlsCAFile", client_options("mongodb://localhost:27017"))

    def test_explicit_ca_file_wins(self) -> None:
        with mock.patch.dict(os.environ, {"MONGODB_TLS_CA_FILE": "/etc/my-ca.pem"}):
            self.assertEqual(client_options("mongodb+srv://c.example.net/")["tlsCAFile"], "/etc/my-ca.pem")
        self.assertNotIn("tlsCAFile", client_options("mongodb+srv://c/?tlsCAFile=/x.pem"))  # left to the URI


if __name__ == "__main__":
    unittest.main()
