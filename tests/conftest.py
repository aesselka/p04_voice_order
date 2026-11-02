# тесты на фиксированном меню, чтобы цены не ломались при смене настоящего меню
import os
from pathlib import Path

TEST_MENU = Path(__file__).parent / "data" / "menu_test.json"
os.environ["MENU_PATH"] = str(TEST_MENU)
