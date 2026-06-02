import unittest

from app.core.config import Settings
from app.core.production_guards import assert_production_security


class TestProductionGuards(unittest.TestCase):
    def test_allows_development_with_default_secret(self):
        assert_production_security(
            Settings(environment="development", jwt_secret="change-me-in-production")
        )

    def test_blocks_production_with_default_secret(self):
        with self.assertRaises(RuntimeError):
            assert_production_security(
                Settings(environment="production", jwt_secret="change-me-in-production")
            )

    def test_allows_production_with_custom_secret(self):
        assert_production_security(
            Settings(environment="production", jwt_secret="a" * 48)
        )
