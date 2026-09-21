# Пробний період Microsoft Store: 30 днів

## Обов’язкове налаштування Partner Center

Код не встановлює тривалість ліцензії Microsoft Store. Перед публікацією:

1. Відкрийте DocExplorer → submission → Pricing and availability.
2. Виберіть платну ціну застосунку.
3. Free trial → Time-limited → 30 days.
4. Збережіть та відправте оновлену submission разом із новою MSIX-збіркою.

Не вибирайте Unlimited або Free для моделі «30 днів, потім купівля».
Дату завершення видає Store; це не 30 днів від кожного встановлення або запуску.
AppxManifest.xml не містить параметра тривалості trial. Його Identity/Publisher
мають точно відповідати Product identity у Partner Center. Наявну identity не змінено.

## Збірка

У середовищі Python 3.10+, яким запускається PyInstaller:

```bat
python -m pip install -r store\requirements-msix.txt
python -m PyInstaller --clean DocExplorer.spec
powershell -ExecutionPolicy Bypass -File store\build_msix.ps1
```

Якщо використовуєте build.cmd, установіть залежності саме для його Python
(у цьому архіві шлях PyInstaller — D:\Python\Python310\Scripts\pyinstaller.exe).
Spec включає WinRT-модулі та перевіряє наявність основних залежностей.
Не пакуйте попередній EXE із dist: спочатку обов’язково перебудуйте його.

## Поведінка

- Без package identity: звичайний EXE та запуск Python не обмежені.
- З package identity: перевірка Store перед створенням головного вікна.
- Активна повна ліцензія: повний доступ.
- Активний trial: повний доступ та повідомлення про залишок днів і дату закінчення.
- Неактивна ліцензія або помилка: діалог «Перевірити знову / Відкрити Microsoft Store / Вийти».
- Перевірка ліцензії кожні п’ять хвилин; перевірка відомої дати завершення щосекунди.
- Після купівлі натисніть «Перевірити знову»; новий результат Store відкриє доступ.
- На завершенні trial вихід викликає звичайне збереження змін PDF.
  Скасування виходу або помилка збереження повертає діалог ліцензії, не знищує документи.
- Власного локального таймера, ключа активації або сервера немає.
- Офлайн приймається активна ліцензія, якщо Store API може її повернути з кешу.
  Помилка API не надає новий trial і не означає автоматичну втрату придбаної ліцензії.
- Нові повідомлення перекладено українською та англійською; для інших мов — англійський fallback.

## Перевірка на Windows перед публікацією

Потрібна справжня ліцензія Store. Самопідписана sideload MSIX без ліцензії може
показувати відмову — це очікувано. Для тесту використовуйте пов’язаний продукт,
встановлений зі Store (можна прихований від пошуку), та окремий обліковий запис,
який ще не придбав застосунок. Не додавайте виробничий перемикач обходу ліцензії.

Перевірте: звичайний EXE; trial; придбану ліцензію; відсутню/прострочену ліцензію;
відсутність інтернету; купівлю та повторну перевірку; закінчення під час роботи;
вихід із незбереженим PDF та скасування збереження. Windows UI, WinRT bridge,
PyInstaller EXE та справжню Store-ліцензію не перевірено в Linux-середовищі розробки.
Автоматичні тести логіки: `python -m unittest discover -s tests -p test_store_license.py`.

## Файли

Змінено: main.py, DocExplorer.spec, localization/__init__.py,
localization/localization_en.py, localization/localization_uk.py.
Додано: common/store_license.py, controls/store_license.py,
store/requirements-msix.txt, store/TRIAL_SETUP_UK.md, tests/test_store_license.py.

Офіційні джерела:
- https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/price-and-availability
- https://learn.microsoft.com/en-us/windows/uwp/monetize/implement-a-trial-version-of-your-app
- https://learn.microsoft.com/en-us/windows/uwp/monetize/in-app-purchases-and-trials
