import unittest

from cryptography.fernet import Fernet

from app.core import security


class SecurityTests(unittest.TestCase):
    def test_derive_key_accepts_valid_fernet_key_verbatim(self) -> None:
        key = Fernet.generate_key().decode()

        derived = security._derive_key(key)

        self.assertEqual(derived, key.encode("utf-8"))

    def test_derive_key_hashes_plaintext_passphrase_into_valid_fernet_key(self) -> None:
        derived = security._derive_key("plain-text-passphrase")

        self.assertNotEqual(derived, b"plain-text-passphrase")
        Fernet(derived)

    def test_decrypt_with_fernets_can_fall_back_to_legacy_cipher(self) -> None:
        token = security._LEGACY_FERNET.encrypt(b"super-secret").decode()
        custom_fernet = Fernet(security._derive_key("another-passphrase"))

        value = security._decrypt_with_fernets(token, [custom_fernet, security._LEGACY_FERNET])

        self.assertEqual(value, "super-secret")


if __name__ == "__main__":
    unittest.main()
