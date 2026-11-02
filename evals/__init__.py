# диалоги написаны под тестовое меню
import os
from pathlib import Path

os.environ.setdefault("MENU_PATH", str(Path(__file__).resolve().parent.parent / "tests" / "data" / "menu_test.json"))
