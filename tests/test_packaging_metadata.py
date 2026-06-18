from pathlib import Path
import tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_pyproject_has_repository_and_release_urls() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    project_urls = pyproject["project"]["urls"]
    assert project_urls["Repository"] == "https://github.com/PythonFZ/fastapi-rfc9457"
    assert project_urls["Releases"] == "https://github.com/PythonFZ/fastapi-rfc9457/releases"


def test_readme_has_pypi_badge_and_absolute_image_urls() -> None:
    readme = (REPO_ROOT / "README.md").read_text()
    assert "[![PyPI](https://img.shields.io/pypi/v/fastapi-rfc9457)](" in readme
    assert "(docs/img/" not in readme
    assert (
        "https://raw.githubusercontent.com/PythonFZ/fastapi-rfc9457/main/docs/img/swagger-errors.png"
        in readme
    )
    assert "https://raw.githubusercontent.com/PythonFZ/fastapi-rfc9457/main/docs/img/doc-page.png" in readme


def test_license_file_exists() -> None:
    assert (REPO_ROOT / "LICENSE").is_file()
