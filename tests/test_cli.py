import unittest

from frontdoor_lab.probe import lab_base_url


class EndpointTests(unittest.TestCase):
    def test_https_and_loopback(self):
        self.assertEqual(lab_base_url("https://origin.example.invalid/"), "https://origin.example.invalid")
        self.assertEqual(lab_base_url("http://127.0.0.1:8080"), "http://127.0.0.1:8080")
        self.assertEqual(lab_base_url("http://[::1]:8080/"), "http://[::1]:8080")

    def test_credentials_queries_and_nonlocal_http_are_rejected(self):
        for value in (
            "https://user:password@origin.example.invalid", "https://@origin.example.invalid",
            "https://origin.example.invalid?token=example", "https://origin.example.invalid#fragment",
            "https://origin.example.invalid/path", "http://origin.example.invalid", "https://",
            "https://origin.example.invalid:invalid",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                lab_base_url(value)


if __name__ == "__main__":
    unittest.main()
