"""
Тест диалога — симуляция целевой аудитории.
Женщина, 34 года, хочет зарабатывать больше, но застряла.
"""
import asyncio
import sys
sys.path.insert(0, '/Users/yaroslavsorokin/Desktop/ai_nastavnik')

from bot.memory.database import init_db
from bot.session_manager import process_message

TEST_USER_ID = 9999999  # фиктивный ID для теста
TEST_NAME = "Анна"

# Сценарий: типичная женщина 34 года, фриланс дизайнер, хочет 200к но застряла на 60к
MESSAGES = [
    "привет",
    "Анна",
    "деньги наверное",
    "ну 7 наверное... хочу зарабатывать больше но как то не получается",
    "я фриланс дизайнер, сейчас зарабатываю около 60 тысяч, хочу выйти на 200",
    "ну не знаю, наверное нет времени на поиск клиентов, много текущей работы",
    "да вроде бы... хотя может я просто боюсь что откажут",
    "наверное боюсь что скажут что я беру слишком дорого",
    "попробую написать паре клиентов на этой неделе",
    "ну когда будет время точно напишу",
]


async def run_test():
    await init_db()
    print("=" * 60)
    print(f"ТЕСТ ДИАЛОГА — симуляция: {TEST_NAME}, фриланс дизайнер, 60к→200к")
    print("=" * 60)

    for i, msg in enumerate(MESSAGES, 1):
        print(f"\n[{i}] ПОЛЬЗОВАТЕЛЬ: {msg}")
        print("-" * 40)
        response = await process_message(TEST_USER_ID, TEST_NAME, msg)
        print(f"БОТ: {response}")
        print()
        await asyncio.sleep(1)  # небольшая пауза между сообщениями

    print("=" * 60)
    print("ТЕСТ ЗАВЕРШЁН")


if __name__ == "__main__":
    asyncio.run(run_test())
