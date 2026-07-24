from __future__ import annotations

import unittest

from ahg_pos.auth import hash_password, normalize_identifier, verify_password


class PasswordTests(unittest.TestCase):
    def test_scrypt_password_round_trip(self) -> None:
        stored = hash_password("Cambiar123!")
        self.assertTrue(verify_password("Cambiar123!", stored))
        self.assertFalse(verify_password("incorrecta", stored))

    def test_identifier_normalization(self) -> None:
        self.assertEqual(normalize_identifier("  ADMIN@AHG.LOCAL "), "admin@ahg.local")

    def test_rejects_invalid_hash(self) -> None:
        self.assertFalse(verify_password("password", "sha256$bad$value"))


if __name__ == "__main__":
    unittest.main()
