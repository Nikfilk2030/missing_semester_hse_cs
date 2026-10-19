"""Сравните кэш модулей до и после импорта стандартной библиотеки."""

import sys


if __name__ == "__main__":
    before = set(sys.modules.copy())
    print("sys.modules до импорта:")
    print(sys.modules)

    import fractions

    added = sorted(set(sys.modules.copy()) - before)
    print("\nНовые модули:", ", ".join(added) or "нет — уже были загружены")
    print("fractions загружен:", "fractions" in sys.modules)
    print("Файл fractions:", fractions.__file__)
    print("\nЭто кэш загруженных модулей, а не список всех установленных пакетов.")
