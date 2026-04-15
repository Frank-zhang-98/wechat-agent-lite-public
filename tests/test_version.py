import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.core.version import DEFAULT_APP_VERSION, get_console_page_title, get_console_version
from app.main import app, scheduler_service


class VersionTests(unittest.TestCase):
    def test_get_console_version_reads_version_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            version_file = Path(tmpdir) / "VERSION"
            version_file.write_text("v1.1\n", encoding="utf-8")

            self.assertEqual(get_console_version(version_file=version_file), "v1.1")

    def test_get_console_version_uses_default_when_file_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            version_file = Path(tmpdir) / "missing-version"

            self.assertEqual(get_console_version(version_file=version_file), DEFAULT_APP_VERSION)

    def test_get_console_version_uses_default_when_file_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            version_file = Path(tmpdir) / "VERSION"
            version_file.write_text("   \n", encoding="utf-8")

            self.assertEqual(get_console_version(version_file=version_file), DEFAULT_APP_VERSION)

    def test_get_console_page_title_includes_version(self) -> None:
        self.assertEqual(get_console_page_title(version="v1.1"), "wechat-agent-lite 控制台 v1.1")

    def test_index_renders_version_in_heading_and_page_title(self) -> None:
        fake_settings = MagicMock()

        with (
            patch("app.main.get_console_version", return_value="v1.1"),
            patch("app.main.Base.metadata.create_all"),
            patch("app.main.ensure_runtime_indexes"),
            patch("app.main.SettingsService", return_value=fake_settings),
            patch("app.main.get_session"),
            patch("app.main.warm_pricing_catalog"),
            patch.object(scheduler_service, "start"),
            patch.object(scheduler_service, "stop"),
        ):
            with TestClient(app) as client:
                response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("<title>wechat-agent-lite 控制台 v1.1</title>", response.text)
        self.assertIn("wechat-agent-lite 控制台", response.text)
        self.assertIn(">v1.1</span>", response.text)

    def test_lifespan_logs_version_on_startup(self) -> None:
        fake_settings = MagicMock()
        fake_session = MagicMock()
        fake_session.execute.return_value.scalar_one.return_value = 0

        class _SessionContext:
            def __enter__(self):
                return fake_session

            def __exit__(self, exc_type, exc, tb):
                return False

        with (
            patch("app.main.get_console_version", return_value="v1.1"),
            patch("app.main.Base.metadata.create_all"),
            patch("app.main.ensure_runtime_indexes"),
            patch("app.main.SettingsService", return_value=fake_settings),
            patch("app.main.get_session", return_value=_SessionContext()),
            patch("app.main.warm_pricing_catalog"),
            patch.object(scheduler_service, "start"),
            patch.object(scheduler_service, "stop"),
            patch("app.main.logger.info") as logger_info,
        ):
            async def _run() -> None:
                async with app.router.lifespan_context(app):
                    pass

            asyncio.run(_run())

        logger_info.assert_called_once_with("starting wechat-agent-lite %s", "v1.1")


if __name__ == "__main__":
    unittest.main()
