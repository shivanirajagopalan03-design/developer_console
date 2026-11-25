import tempfile
import unittest
from pathlib import Path
import os
import sys

main_root = Path(
    os.getenv(
        "APP_PROJECT_ROOT",
        Path(__file__).resolve().parent.parent
        / "Gen_AI_Hybrid_Eval"
        / "ai_hybrid_evaluator",
    )
).resolve()
if main_root.is_dir() and str(main_root) not in sys.path:
    sys.path.insert(0, str(main_root))

from backend.storage.api_provider import APIStorageProvider
from backend.storage.folder_provider import FolderStorageProvider
from backend.storage.mysql_provider import MySQLStorageProvider
from backend.storage.provider import (
    StorageAccessError,
    StorageConfigurationError,
    StorageCorruptionError,
)


class FolderStorageProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.provider = FolderStorageProvider(Path(self.temp.name))
        self.provider.initialize()

    def test_crud_and_atomic_file_persistence(self):
        record = {"id": "1", "name": "Initial"}
        self.provider.create_record("candidates", record)
        self.assertEqual(
            self.provider.read_record("candidates", "1"),
            record,
        )
        updated = self.provider.update_record(
            "candidates",
            "1",
            {"name": "Updated"},
        )
        self.assertEqual(updated["name"], "Updated")
        self.assertTrue(self.provider.delete_record("candidates", "1"))
        self.assertEqual(self.provider.list_records("candidates"), [])

    def test_missing_and_corrupted_documents_are_distinct(self):
        self.assertEqual(
            self.provider.read_json("missing", default=[]),
            [],
        )
        path = Path(self.temp.name) / "corrupt.json"
        path.write_text("{bad json", encoding="utf-8")
        with self.assertRaises(StorageCorruptionError):
            self.provider.read_json("corrupt")

    def test_path_traversal_is_rejected(self):
        with self.assertRaises(StorageAccessError):
            self.provider.list_records("../outside")

    def test_invalid_configuration_is_rejected(self):
        with self.assertRaises(StorageConfigurationError):
            self.provider.validate_config({"path": "relative.json"})

    def test_health_check_and_missing_directory(self):
        self.assertEqual(
            self.provider.health()["status"].value,
            "healthy",
        )
        missing = FolderStorageProvider(
            Path(self.temp.name) / "missing"
        )
        self.assertEqual(
            missing.health()["status"].value,
            "unhealthy",
        )


class FutureProviderContractTests(unittest.TestCase):
    def test_mysql_configuration_is_validated_but_operations_are_disabled(self):
        provider = MySQLStorageProvider()
        normalized = provider.validate_config(
            {
                "host": "db.example.test",
                "port": "3306",
                "database": "evaluation",
                "ssl_mode": "PREFERRED",
            }
        )
        self.assertEqual(normalized["port"], 3306)
        self.assertFalse(provider.capabilities.read)
        with self.assertRaises(StorageConfigurationError):
            provider.list_records("candidates")

    def test_api_rejects_http_and_private_destinations(self):
        provider = APIStorageProvider()
        with self.assertRaises(StorageConfigurationError):
            provider.validate_config(
                {"base_url": "http://api.example.test", "api_version": "v1"}
            )
        with self.assertRaises(StorageConfigurationError):
            provider.validate_config(
                {"base_url": "https://localhost", "api_version": "v1"}
            )
        self.assertFalse(provider.capabilities.read)
