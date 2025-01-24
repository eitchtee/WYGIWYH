import json
from pathlib import Path

from apps.import_app.models import ImportProfile


class PresetService:
    PRESET_PATH = "/usr/src/app/import_presets"

    @classmethod
    def get_all_presets(cls):
        presets = []

        for folder in Path(cls.PRESET_PATH).iterdir():
            if folder.is_dir():
                manifest_path = folder / "manifest.json"
                config_path = folder / "config.yml"

                if manifest_path.exists() and config_path.exists():
                    with open(manifest_path) as f:
                        manifest = json.load(f)

                    with open(config_path) as f:
                        config = json.dumps(f.read())

                    try:
                        preset = {
                            "name": manifest.get("name", folder.name),
                            "description": manifest.get("description", ""),
                            "message": json.dumps(manifest.get("message", "")),
                            "authors": manifest.get("author", "").split(","),
                            "schema_version": (int(manifest.get("schema_version", 1))),
                            "folder_name": folder.name,
                            "config": config,
                        }

                        ImportProfile.Versions(
                            preset["schema_version"]
                        )  # Check if schema version is valid
                    except Exception as e:
                        pass
                    else:
                        presets.append(preset)

        return presets
