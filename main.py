from openai import OpenAI
import requests
from tqdm import tqdm
import os
from typing import List, Tuple
from parses import start
from secret import BASE_URL, QUESTION_TEST

# Инициализация клиента OpenAI с параметрами из конфигурации
client = OpenAI(
    api_key="sk-1eBuYLztp8xhrMO1OkFXhA",  # В продакшене используйте переменные окружения!
    base_url=BASE_URL,  # Базовый URL API
)


def call_llm(prompt: str, model: str = "gpt-4o-mini") -> str:
    """
    Вызывает языковую модель OpenAI для генерации ответа

    Args:
        prompt: Текст запроса
        model: Используемая модель (по умолчанию 'gpt-4o-mini')

    Returns:
        Строка с ответом модели
    """
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты помощник, который отвечает строго по содержимому сайта. "
                        "Отвечай кратко, без рассуждений и догадок. "
                        "Не убирай важные данные (ссылки, расписания, даты). "
                        "Не пиши, что дополнительная информация есть на сайте."
                    )
                },
                {"role": "user", "content": f"Контент сайта: {prompt}"}
            ],
            max_tokens=500,
            temperature=0.3  # Для более детерминированных ответов
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Ошибка при вызове LLM: {str(e)}")


def fetch_html_text(url: str) -> str:
    """
    Загружает HTML-контент с указанного URL

    Args:
        url: URL для загрузки

    Returns:
        Текст HTML-страницы
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/119.0.0.0 Safari/537.36'
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"Ошибка загрузки URL {url}: {str(e)}")
        return ""


def summarize_text(text: str, max_length: int = 40000) -> str:
    """
    Обрабатывает текст перед отправкой в LLM

    Args:
        text: Исходный текст
        max_length: Максимальная длина текста для обработки

    Returns:
        Обработанный текст
    """
    # В будущем можно добавить предварительное суммаризирование
    return text[:max_length]


def answer_questions(summary: str, questions: List[str]) -> List[Tuple[str, str]]:
    """
    Генерирует ответы на список вопросов на основе текста

    Args:
        summary: Текст для анализа
        questions: Список вопросов

    Returns:
        Список кортежей (вопрос, ответ)
    """
    answers = []
    for question in tqdm(questions, desc="Обработка вопросов", unit="вопрос"):
        prompt = (
            f"На основе следующего текста:\n{summary}\n\n"
            f"Ответь точно на вопрос: {question}\n"
            f"Если информации нет, напиши 'Информация не найдена'"
        )
        answer = call_llm(prompt)
        answers.append((question, answer))
    return answers


def save_answers(answers: List[Tuple[str, str]], filename: str = "answers.txt"):
    """
    Сохраняет ответы в файл

    Args:
        answers: Список кортежей (вопрос, ответ)
        filename: Имя файла для сохранения
    """
    with open(filename, "w", encoding="utf-8") as f:
        for question, answer in answers:
            f.write(f"Вопрос: {question}\n")
            f.write(f"Ответ: {answer}\n")
            f.write("-" * 80 + "\n\n")


def main():
    """Основная функция выполнения скрипта"""
    try:
        # Чтение вопросов из конфигурации
        questions = QUESTION_TEST

        # URL для обработки (можно сделать ввод через аргументы командной строки)
        target_url = input("Введите URL сайта для анализа: ").strip()

        # Запуск парсера и сохранение результатов
        print("\n" + "=" * 50)
        print("Начало обработки сайта...")
        start(target_url)  # Функция из модуля parses

        # Чтение результатов парсинга
        results_file = "scrape_results/full_data.txt"
        if not os.path.exists(results_file):
            raise FileNotFoundError(f"Файл результатов не найден: {results_file}")

        with open(results_file, "r", encoding="utf-8") as f:
            site_content = f.read()

        site_content.replace("\n", " ")
        # Генерация ответов
        print("\n" + "=" * 50)
        print("Анализ контента и генерация ответов...")
        summary = summarize_text(site_content)
        answers = answer_questions(summary, questions)

        # Вывод и сохранение результатов
        print("\n" + "=" * 50)
        print("Результаты:\n")
        for question, answer in answers:
            print(f"Вопрос: {question}")
            print(f"Ответ: {answer}")
            print("-" * 80 + "\n")

        save_answers(answers)
        print(f"\nОтветы сохранены в файл answers.txt")

    except Exception as e:
        print(f"\nОшибка выполнения: {str(e)}")


if __name__ == "__main__":
    for i in range(6):
        main()
        os.system('cls')