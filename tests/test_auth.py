from __future__ import annotations

import unittest

from ahg_pos.auth import ALL_MODULES, AuthUser, hash_password, normalize_identifier, normalize_user_modules, verify_password


class PasswordTests(unittest.TestCase):
    def test_scrypt_password_round_trip(self) -> None:
        stored = hash_password("Cambiar123!")
        self.assertTrue(verify_password("Cambiar123!", stored))
        self.assertFalse(verify_password("incorrecta", stored))

    def test_identifier_normalization(self) -> None:
        self.assertEqual(normalize_identifier("  ADMIN@AHG.LOCAL "), "admin@ahg.local")

    def test_rejects_invalid_hash(self) -> None:
        self.assertFalse(verify_password("password", "sha256$bad$value"))

    def test_module_permissions_use_role_defaults_and_filter_unknown_values(self) -> None:
        self.assertEqual(normalize_user_modules(None, "almacen"), ("products", "suppliers", "purchases", "inventory"))
        self.assertEqual(normalize_user_modules(["audit", "unknown", "sale"], "cajero"), ("sale", "audit"))
        self.assertEqual(normalize_user_modules([], "admin"), ALL_MODULES)

    def test_public_user_exposes_modules_and_checks_access(self) -> None:
        user = AuthUser(7, "Auditor", "auditor@example.com", "", "cajero", ("audit",))
        self.assertTrue(user.can_access("audit"))
        self.assertFalse(user.can_access("sale"))
        self.assertEqual(user.public()["modules"], ["audit"])


if __name__ == "__main__":
    unittest.main()
