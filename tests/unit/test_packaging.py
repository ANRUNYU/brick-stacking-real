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

def test_package_keeps_calibration_tools_and_exact_environment_files(tmp_path):
    root=tmp_path/'p';root.mkdir();(root/'pyproject.toml').write_text('[project]\nname="fixture"')
    for d in ('calibration/examples','calibration/approved','config/planning'):(root/d).mkdir(parents=True)
    (root/'calibration/examples/synthetic.json').write_text('{}')
    (root/'calibration/approved/actual.json').write_text('{}')
    (root/'config/planning/requirements-linux-fcl.txt').write_text('python-fcl==0.7.0.11')
    (root/'config/planning/private.txt').write_text('not source')
    out=tmp_path/'package.zip';package_source(root,out)
    with ZipFile(out) as archive:
        assert 'calibration/examples/synthetic.json' in archive.namelist()
        assert 'config/planning/requirements-linux-fcl.txt' in archive.namelist()
        assert 'calibration/approved/actual.json' not in archive.namelist()
        assert 'config/planning/private.txt' not in archive.namelist()
