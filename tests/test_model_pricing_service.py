import unittest
from unittest.mock import patch

from app.services import model_pricing_service


class ModelPricingServiceTests(unittest.TestCase):
    def test_pricing_catalog_meta_does_not_auto_sync(self) -> None:
        with patch("app.services.model_pricing_service.get_pricing_catalog", return_value={"meta": {"pricing_mode": "built_in_fallback"}}) as mocked:
            meta = model_pricing_service.pricing_catalog_meta()

        self.assertEqual(meta["pricing_mode"], "built_in_fallback")
        mocked.assert_called_once_with(auto_sync=False)


if __name__ == "__main__":
    unittest.main()
