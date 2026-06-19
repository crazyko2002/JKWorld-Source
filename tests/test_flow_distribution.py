"""Published Flow bundles are hashed and applied atomically."""

from pathlib import Path
import json
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import flow_distribution as distribution  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "templates").mkdir()
        (root / "recordings").mkdir()
        (root / "numpad").mkdir()
        (root / "config.yaml").write_text("rules: []\n", encoding="utf-8")
        (root / "macro_config.yaml").write_text("events: []\n", encoding="utf-8")
        (root / "templates" / "hello.png").write_bytes(b"template-v1")
        manifest_path = distribution.prepare_published_bundle(
            root, version="1.2.3"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["flow_version"] == "1.2.3"
        assert manifest["bundle"]["source"] == "bundles/flow-1.2.3.zip"
        assert {item["path"] for item in manifest["files"]} >= {
            "config.yaml",
            "macro_config.yaml",
            "templates/hello.png",
        }

        install = root / "install"
        install.mkdir()
        (install / "update_settings.json").write_text(json.dumps({
            "manifest_url": "https://example.test/manifest.json",
            "asset_base_url": "https://example.test/",
        }), encoding="utf-8")
        bundle_source = manifest["bundle"]["source"]
        payloads = {
            bundle_source: (root / "published" / bundle_source).read_bytes()
        }
        original_json = distribution._download_json
        original_bytes = distribution._download_bytes
        distribution._download_json = lambda _url, _timeout: manifest
        distribution._download_bytes = lambda url, _timeout: payloads[
            url.split("https://example.test/", 1)[1].split("?", 1)[0]
        ]
        try:
            result = distribution.check_and_apply_updates(
                install, log=lambda _message: None
            )
        finally:
            distribution._download_json = original_json
            distribution._download_bytes = original_bytes
        assert result.updated
        assert result.version == "1.2.3"
        assert (install / "templates" / "hello.png").read_bytes() == b"template-v1"
        assert distribution.installed_flow_version(install) == "1.2.3"
    print("Flow distribution update OK")


if __name__ == "__main__":
    main()
