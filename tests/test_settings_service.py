import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.services.settings_service import SettingsService


class SettingsServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine)
        SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)
        self.session = SessionLocal()
        self.settings = SettingsService(self.session)

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def test_get_reads_pending_defaults_before_flush(self) -> None:
        self.settings.ensure_defaults()

        self.assertEqual(self.settings.get("selection.stale_hard_hours_news"), "168")
        self.assertEqual(self.settings.get_float("selection.stale_hard_hours_news", 336.0), 168.0)
        self.assertEqual(self.settings.get("selection.stale_hard_hours_technical"), "1440")
        self.assertEqual(self.settings.get_float("selection.stale_hard_hours_technical", 336.0), 1440.0)

    def test_secret_values_are_masked_in_public_dict(self) -> None:
        self.settings.ensure_defaults()
        with patch("app.services.settings_service.ensure_secret_storage_allowed") as guard:
            guard.return_value = None
            self.settings.set("wechat.app_secret", "super-secret")

        self.assertEqual(self.settings.as_dict(include_secrets=False)["wechat.app_secret"], "******")
        self.assertEqual(self.settings.as_dict(include_secrets=True)["wechat.app_secret"], "super-secret")

    def test_masked_secret_value_does_not_overwrite_existing_secret(self) -> None:
        self.settings.ensure_defaults()
        with patch("app.services.settings_service.ensure_secret_storage_allowed") as guard:
            guard.return_value = None
            self.settings.set("wechat.app_secret", "super-secret")
            self.settings.set("wechat.app_secret", "******")

        self.assertEqual(self.settings.get("wechat.app_secret"), "super-secret")

    def test_setting_secret_requires_external_key_or_explicit_override(self) -> None:
        self.settings.ensure_defaults()

        with self.assertRaisesRegex(RuntimeError, "WAL_ENCRYPTION_KEY"):
            self.settings.set("wechat.app_secret", "super-secret")


if __name__ == "__main__":
    unittest.main()
