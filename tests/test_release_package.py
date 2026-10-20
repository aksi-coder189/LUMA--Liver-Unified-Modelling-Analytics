import os
from zipfile import ZipFile

from scripts.package_release import ROOT, create_archive


def test_release_archive_contains_project_and_excludes_generated_runtime_files():
    target = ROOT / f".test-release-{os.getpid()}.zip"
    try:
        count = create_archive(target)
        assert count > 20
        with ZipFile(target) as archive:
            names = archive.namelist()
        assert f"{ROOT.name}/README.md" in names
        assert f"{ROOT.name}/web/assets/models/liver.glb" in names
        assert f"{ROOT.name}/model/synthetic_ode_model.json" in names
        assert not any(
            "__pycache__" in name or name.endswith((".pyc", ".pyo", ".pyd"))
            for name in names
        )
        assert not any("node_modules" in name or "/.venv/" in name for name in names)
    finally:
        target.unlink(missing_ok=True)
