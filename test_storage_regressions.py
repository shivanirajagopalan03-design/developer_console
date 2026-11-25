"""Safety and compatibility checks for the provider integration."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine

from backend.database.mysql_json_store import MySQLJSONStore
from backend.repositories.json_repository import JSONRepository, repository_read_scope
from backend.storage.factory import StorageProviderFactory
from backend.storage.folder_provider import FolderStorageProvider
from backend.storage.mysql_provider import MySQLStorageProvider
from backend.storage.provider import StorageConfigurationError, StorageOperationError
import backend.repositories.json_repository as repository
import developer_console.developer_console as console


def test_console_credentials_are_owned_by_console():
    assert console.CONSOLE_ENV_FILE == console.CONSOLE_PROJECT_ROOT / ".env"


def test_parallel_creates_do_not_lose_records(tmp_path):
    def create(index):
        FolderStorageProvider(tmp_path).create_record("items", {"id": str(index)})
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(create, range(40)))
    assert len(FolderStorageProvider(tmp_path).list_records("items")) == 40


def test_failed_atomic_replace_preserves_original(tmp_path):
    provider = FolderStorageProvider(tmp_path)
    provider.write_json("items", [{"id": "original"}])
    before = (tmp_path / "items.json").read_bytes()
    with patch("os.replace", side_effect=OSError("simulated failure")):
        with pytest.raises(OSError):
            provider.write_json("items", [])
    assert (tmp_path / "items.json").read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))
    with pytest.raises(StorageOperationError):
        provider.write_json("items", float("nan"))
    assert (tmp_path / "items.json").read_bytes() == before


def test_factory_requires_explicit_absolute_folder():
    with pytest.raises(StorageConfigurationError):
        StorageProviderFactory.create("folder")
    with pytest.raises(StorageConfigurationError):
        StorageProviderFactory.create("folder", {"path": "relative"})


def test_connection_checks_requested_folder(tmp_path):
    provider = FolderStorageProvider(tmp_path / "missing")
    assert provider.check_connection({"path": str(tmp_path)})


def test_mysql_factory_normalizes_configuration_before_binding():
    with patch("backend.database.mysql_json_store.MySQLJSONStore") as store:
        provider = StorageProviderFactory.create("mysql", {
            "host": "db.example.test", "database": "evaluation", "port": "3306",
            "username": "test-user", "password": "test-only-password",
        })
    assert provider.store is store.return_value
    assert store.call_args.args[0]["port"] == 3306
    assert store.call_args.args[0]["ssl_mode"] == "PREFERRED"


def test_mysql_adapter_and_read_scope_work_without_folder_file(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'mysql-contract.sqlite'}")
    try:
        store = MySQLJSONStore({}, engine=engine)
        provider = MySQLStorageProvider(store)
        assert provider.capabilities.read
        provider.create_record("items", {"id": "one"})
        provider.update_record("items", "one", {"name": "Updated"})
        assert provider.read_record("items", "one")["name"] == "Updated"
        assert provider.delete_record("items", "one")
        monkeypatch.setattr(repository, "_mysql_target", lambda path: (Path(path), store, "items.json"))
        repo = JSONRepository(tmp_path / "items.json")
        with repository_read_scope():
            assert repo.get_all() == []
            repo.save_all([{"id": "two"}])
            assert repo.get_all() == [{"id": "two"}]
        assert not (tmp_path / "items.json").exists()
    finally:
        engine.dispose()
