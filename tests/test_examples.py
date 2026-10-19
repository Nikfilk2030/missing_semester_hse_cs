"""Проверки учебных примеров: без сетевых запросов и изменения окружения."""

from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "2026" / "amcs" / "year_1" / "seminar_2" / "examples"


class ModuleDemoTests(unittest.TestCase):
    def test_demo_shows_module_cache_and_imported_module(self):
        result = subprocess.run(
            [sys.executable, str(EXAMPLES / "modules.py")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("sys.modules до импорта", result.stdout)
        self.assertIn("Новые модули:", result.stdout)
        self.assertIn("fractions загружен: True", result.stdout)
        self.assertIn("Файл fractions:", result.stdout)
        self.assertEqual(result.stderr, "")


class MetadataDemoTests(unittest.TestCase):
    def test_demo_reads_installed_distribution_metadata(self):
        result = subprocess.run(
            [sys.executable, str(EXAMPLES / "package_metadata.py")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Name: Pygments", result.stdout)
        self.assertIn("Metadata-Version:", result.stdout)
        self.assertIn("METADATA", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_unknown_distribution_has_actionable_error_without_traceback(self):
        result = subprocess.run(
            [sys.executable, str(EXAMPLES / "package_metadata.py"),
             "missing-semester-distribution-does-not-exist-2026"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("Дистрибутив не установлен:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_missing_metadata_file_is_reported_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "missing_semester_empty_demo-0.0.0.dist-info").mkdir()
            environment = os.environ.copy()
            environment["PYTHONPATH"] = directory
            result = subprocess.run(
                [sys.executable, str(EXAMPLES / "package_metadata.py"),
                 "missing-semester-empty-demo"],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("METADATA отсутствует:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
