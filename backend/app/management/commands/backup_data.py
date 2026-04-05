"""Management command to backup database and media files."""

from __future__ import annotations

import json
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


def _safe_label(value: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    return re.sub(r"[^a-z0-9_-]+", "-", text).strip("-")


class Command(BaseCommand):
    """Create a backup bundle containing DB fixture and media archive."""

    help = "Create automated database + media backup under a timestamped directory."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--output-dir",
            default="",
            help="Directory where backup bundle is created. Defaults to <BASE_DIR>/backups.",
        )
        parser.add_argument(
            "--label",
            default="",
            help="Optional label suffix for backup folder.",
        )
        parser.add_argument(
            "--skip-database",
            action="store_true",
            help="Skip database fixture backup.",
        )
        parser.add_argument(
            "--skip-media",
            action="store_true",
            help="Skip media archive backup.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        skip_database = bool(options.get("skip_database"))
        skip_media = bool(options.get("skip_media"))
        if skip_database and skip_media:
            raise CommandError("At least one backup target must be enabled.")

        default_output_dir = Path(getattr(settings, "BASE_DIR", Path.cwd())) / "backups"
        output_dir_raw = str(options.get("output_dir") or "").strip()
        output_dir = Path(output_dir_raw) if output_dir_raw else default_output_dir
        output_dir = output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
        label = _safe_label(str(options.get("label") or ""))
        backup_name = f"backup_{timestamp}"
        if label:
            backup_name = f"{backup_name}_{label}"
        backup_dir = output_dir / backup_name
        backup_dir.mkdir(parents=True, exist_ok=False)

        manifest: dict[str, Any] = {
            "version": 1,
            "created_at": timezone.now().isoformat(),
            "database_file": None,
            "media_file": None,
            "media_root": str(Path(getattr(settings, "MEDIA_ROOT", ""))),
        }

        try:
            if not skip_database:
                db_fixture_path = backup_dir / "database.json"
                with db_fixture_path.open("w", encoding="utf-8") as fixture_stream:
                    call_command(
                        "dumpdata",
                        indent=2,
                        exclude=["contenttypes", "auth.permission"],
                        stdout=fixture_stream,
                    )
                manifest["database_file"] = db_fixture_path.name

            if not skip_media:
                media_root = Path(getattr(settings, "MEDIA_ROOT", "")).resolve()
                media_archive_path = backup_dir / "media.zip"
                self._write_media_archive(media_root=media_root, archive_path=media_archive_path)
                manifest["media_file"] = media_archive_path.name

            manifest_path = backup_dir / "manifest.json"
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        except Exception as exc:
            shutil.rmtree(backup_dir, ignore_errors=True)
            raise CommandError(f"Backup failed: {exc}") from exc

        self.stdout.write(self.style.SUCCESS(f"Backup created at: {backup_dir}"))
        if manifest.get("database_file"):
            self.stdout.write(self.style.SUCCESS(f"- Database fixture: {manifest['database_file']}"))
        if manifest.get("media_file"):
            self.stdout.write(self.style.SUCCESS(f"- Media archive: {manifest['media_file']}"))

    def _write_media_archive(self, *, media_root: Path, archive_path: Path) -> None:
        with zipfile.ZipFile(archive_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            if not media_root.exists() or not media_root.is_dir():
                return

            for item in media_root.rglob("*"):
                if not item.is_file():
                    continue
                relative_path = item.relative_to(media_root).as_posix()
                archive.write(item, arcname=relative_path)
