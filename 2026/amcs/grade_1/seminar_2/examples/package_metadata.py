"""Покажите метаданные установленного дистрибутива, не импортируя его код."""

import argparse
import sys
from importlib.metadata import PackageNotFoundError, distribution


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", nargs="?", default="Pygments")
    args = parser.parse_args()
    try:
        package = distribution(args.name)
    except PackageNotFoundError:
        print("Дистрибутив не установлен:", args.name, file=sys.stderr)
        print("Для примера установите examples/requirements.txt в отдельное окружение.",
              file=sys.stderr)
        return 2

    raw_metadata = package.read_text("METADATA")
    if raw_metadata is None:
        print("METADATA отсутствует:", args.name, file=sys.stderr)
        print("Этот пример рассчитан на установленный wheel с каталогом .dist-info.",
              file=sys.stderr)
        return 2

    print("Дистрибутив:", package.metadata["Name"])
    print("Версия:", package.version)
    print("Требует Python:", package.metadata.get("Requires-Python", "не указано"))
    print("Зависимости:", package.requires or "нет объявленных зависимостей")
    for path in package.files or []:
        if str(path).endswith(".dist-info/METADATA"):
            print("Файл METADATA:", package.locate_file(path))
            break
    print("\nMETADATA — заголовки до описания проекта:\n")
    print(raw_metadata.split("\n\n", 1)[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
