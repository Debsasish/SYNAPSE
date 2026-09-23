from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS_INDEX = ROOT / "docs" / "index.html"
README = ROOT / "README.md"


def test_docs_site_reproduction_commands_match_repo_entrypoints():
    html = DOCS_INDEX.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")

    assert "python run_all.py" in html
    assert "pytest -q tests/" in html

    assert (ROOT / "run_all.py").is_file()
    assert (ROOT / "tests").is_dir()
    assert (ROOT / "tests" / "test_conformance.py").is_file()

    assert "python run_all.py" in readme
    assert "pytest -q tests/" in readme or "python -m pytest -q tests/" in readme
