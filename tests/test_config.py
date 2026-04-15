from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from app.core import config as config_module


class ConfigLoadingTests(unittest.TestCase):
    def test_load_config_reads_project_env_file_without_overriding_existing_env(self) -> None:
        with patch.object(config_module, "load_dotenv") as mocked_load_dotenv:
            cfg = config_module.load_config()

        project_root = Path(config_module.__file__).resolve().parents[2]
        mocked_load_dotenv.assert_called_once_with(project_root / ".env", override=False)
        self.assertEqual(cfg.app_name, "wechat-agent-lite")


if __name__ == "__main__":
    unittest.main()
