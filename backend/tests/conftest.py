import importlib.util
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("LLM_PROVIDER", "mock")


def _load_script():
    spec = importlib.util.spec_from_file_location("create_sample_repo", ROOT / "scripts" / "create_sample_repo.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def sample_script():
    return _load_script()


@pytest.fixture(scope="session")
def sample_repo_master(tmp_path_factory, sample_script):
    return sample_script.create_sample_repo(tmp_path_factory.mktemp("master") / "sample_repo", force=True)


@pytest.fixture()
def sample_repo(tmp_path, sample_repo_master):
    """A fresh copy of the sample repo (with git history) per test."""
    import shutil

    dest = tmp_path / "repo"
    shutil.copytree(sample_repo_master, dest)
    return dest


@pytest.fixture()
def sample_repo_nogit(tmp_path, sample_script):
    return sample_script.create_sample_repo(tmp_path / "repo_nogit", force=True, with_git=False)
