import json
from zipfile import ZipFile
import pytest
from tools.package_source import package_source


def test_portable_zip_excludes_venvs_secrets_and_artifacts(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "pyproject.toml").write_text('[project]\nname="fixture"')
    (root / "src").mkdir()
    (root / "src/core.py").write_text('"""fixture"""')
    (root / ".env").write_text("dummy_secret=fixture")
    (root / ".venv").mkdir()
    (root / ".venv/private.py").write_text("ignored")
    output = tmp_path / "source.zip"
    result = package_source(root, output)
    with ZipFile(output) as archive:
        assert set(archive.namelist()) == {"pyproject.toml", "src/core.py", "source_manifest.json"}
        assert "src/core.py" in json.loads(archive.read("source_manifest.json"))["files"]
    assert result["file_count"] == 2
    with pytest.raises(FileExistsError): package_source(root, output)
