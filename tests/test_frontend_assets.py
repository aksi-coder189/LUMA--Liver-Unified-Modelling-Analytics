import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def test_local_javascript_imports_resolve_to_packaged_modules():
    import_pattern = re.compile(
        r"\bfrom\s+['\"]([^'\"]+)['\"]|\bimport\s+['\"]([^'\"]+)['\"]"
    )
    sources = [ROOT / "web/app.js", *sorted((WEB / "assets/js").rglob("*.js"))]
    missing = []
    for source in sources:
        for match in import_pattern.finditer(source.read_text(encoding="utf-8")):
            specifier = urlsplit(next(item for item in match.groups() if item)).path
            if specifier.startswith((".", "/")):
                target = (
                    (source.parent / specifier).resolve()
                    if specifier.startswith(".")
                    else (WEB / specifier.lstrip("/")).resolve()
                )
                if WEB.resolve() not in target.parents and target != WEB.resolve():
                    missing.append(
                        f"{source.relative_to(ROOT)} imports outside web/: {specifier}"
                    )
                elif not target.is_file():
                    missing.append(
                        f"{source.relative_to(ROOT)} imports missing asset: {specifier}"
                    )
    assert not missing, "\n".join(missing)


def test_html_local_assets_resolve():
    class AssetParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.paths = []

        def handle_starttag(self, tag, attrs):
            values = dict(attrs)
            for attribute in ("src", "href"):
                value = values.get(attribute, "")
                if value and not value.startswith(
                    ("#", "data:", "http:", "https:", "mailto:")
                ):
                    self.paths.append(value)

    parser = AssetParser()
    parser.feed((WEB / "index.html").read_text(encoding="utf-8"))
    missing = [
        value
        for value in parser.paths
        if not (WEB / urlsplit(value).path.lstrip("/")).is_file()
    ]
    assert not missing, f"HTML references missing local assets: {missing}"
