import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime


# ============================================================
# НАСТРОЙКИ
# ============================================================

# Сайт, который парсим
SOURCE_URL = "https://standupclubulsk.ru/"

# Твой backend
BACKEND_URL = "https://astonishing-pastelito-e6e568.netlify.app"

# Supabase
SUPABASE_URL = "https://tgyqyrullvofkezmqrkj.supabase.co"

# ============================================================
# ВСТАВЬ СЮДА ДАННЫЕ
# ============================================================

# Supabase → Project Settings → API → anon public
SUPABASE_ANON_KEY = os.environ["SUPABASE_ANON_KEY"]

# Логин пользователя Supabase
BACKEND_LOGIN = os.environ["BACKEND_LOGIN"]

# Пароль пользователя Supabase
BACKEND_PASSWORD = os.environ["BACKEND_PASSWORD"]


# ============================================================
# URL BACKEND
# ============================================================

GET_EVENTS_URL = f"{BACKEND_URL}/api/events"
ADD_EVENT_URL = f"{BACKEND_URL}/api/events"


# ============================================================
# ПОЛУЧЕНИЕ ACCESS TOKEN
# ============================================================

def get_access_token():

    print("\nАвторизуемся в Supabase...")

    response = requests.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        headers={
            "apikey": SUPABASE_ANON_KEY,
            "Content-Type": "application/json"
        },
        json={
            "email": BACKEND_LOGIN,
            "password": BACKEND_PASSWORD
        },
        timeout=20
    )

    if response.status_code != 200:

        print("\nОШИБКА АВТОРИЗАЦИИ")
        print("HTTP:", response.status_code)
        print("Ответ:", response.text)

        response.raise_for_status()

    data = response.json()

    access_token = data.get("access_token")

    if not access_token:
        raise Exception("Supabase не вернул access_token")

    print("Авторизация успешна.")

    return access_token


# ============================================================
# ПОЛУЧЕНИЕ САЙТА
# ============================================================

def get_source_html():

    print("Получаем сайт...")

    response = requests.get(
        SOURCE_URL,
        timeout=30,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/138.0 Safari/537.36"
            )
        }
    )

    response.raise_for_status()

    return response.text


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def clean_text(text):

    if not text:
        return None

    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_price(text):

    if not text:
        return None

    text = clean_text(text)

    # Например:
    # "500 ₽"
    # "500руб"
    # "500 р."

    match = re.search(r"(\d+(?:[.,]\d+)?)", text)

    if not match:
        return None

    price = match.group(1).replace(",", ".")

    return price


def convert_date(date_text, time_text):

    """
    Преобразует:

    20/09
    19:30

    в:

    2026-09-20T19:30:00
    """

    date_text = clean_text(date_text)
    time_text = clean_text(time_text)

    if not date_text or not time_text:
        return None

    match = re.search(
        r"(\d{1,2})[./-](\d{1,2})",
        date_text
    )

    if not match:
        return None

    day = int(match.group(1))
    month = int(match.group(2))

    time_match = re.search(
        r"(\d{1,2}):(\d{2})",
        time_text
    )

    if not time_match:
        return None

    hour = int(time_match.group(1))
    minute = int(time_match.group(2))

    year = datetime.now().year

    try:

        dt = datetime(
            year,
            month,
            day,
            hour,
            minute
        )

        return dt.strftime("%Y-%m-%dT%H:%M:%S")

    except ValueError:

        return None


# ============================================================
# SOURCE ID
# ============================================================

def make_source_id(url):

    if not url:
        return None

    """
    Из:

    https://widget.afisha.yandex.ru/w/sessions/
    ticketsteam-9145@62866058?...

    получаем:

    ticketsteam-9145@62866058
    """

    match = re.search(
        r"(ticketsteam-\d+@\d+)",
        url
    )

    if match:
        return match.group(1)

    return None


# ============================================================
# ПОИСК ССЫЛКИ НА БИЛЕТЫ
# ============================================================

def find_ticket_url(block):

    links = block.find_all("a")

    for link in links:

        href = link.get("href")

        if not href:
            continue

        if "ticketsteam-" in href:
            return href

        if "afisha.yandex.ru" in href:
            return href

    return None


# ============================================================
# ПОИСК ТЕКСТОВЫХ ЭЛЕМЕНТОВ
# ============================================================

def get_block_texts(block):

    texts = []

    for elem in block.select(".tn-elem"):

        text = elem.get_text(" ", strip=True)

        text = clean_text(text)

        if text:
            texts.append(text)

    return texts


# ============================================================
# ОПРЕДЕЛЕНИЕ ДАТЫ
# ============================================================

def find_date(texts):

    for text in texts:

        match = re.search(
            r"\b\d{1,2}[./-]\d{1,2}\b",
            text
        )

        if match:
            return match.group(0)

    return None


# ============================================================
# ОПРЕДЕЛЕНИЕ ВРЕМЕНИ
# ============================================================

def find_time(texts):

    for text in texts:

        match = re.search(
            r"\b\d{1,2}:\d{2}\b",
            text
        )

        if match:
            return match.group(0)

    return None


# ============================================================
# ОПРЕДЕЛЕНИЕ ЦЕНЫ
# ============================================================

def find_price(texts):

    for text in texts:

        if "₽" in text or "руб" in text.lower():

            price = normalize_price(text)

            if price:
                return price

    return None


# ============================================================
# ОПРЕДЕЛЕНИЕ НАЗВАНИЯ
# ============================================================

def find_title(texts, date_text, time_text, price):

    candidates = []

    for text in texts:

        # Пропускаем дату
        if date_text and date_text in text:
            continue

        # Пропускаем время
        if time_text and time_text in text:
            continue

        # Пропускаем цену
        if "₽" in text or "руб" in text.lower():
            continue

        # Пропускаем кнопки
        lower = text.lower()

        if "купить билет" in lower:
            continue

        if "билет" in lower:
            continue

        # Пропускаем слишком короткие технические элементы
        if len(text) < 2:
            continue

        candidates.append(text)

    if not candidates:
        return None

    # Обычно название находится среди наиболее заметных
    # текстовых элементов.
    #
    # Для текущего сайта берем последний подходящий кандидат.
    return candidates[-1]


# ============================================================
# ПОИСК КАРТИНКИ
# ============================================================
def find_image(block):

    images = block.find_all("img")

    for img in images:

        src = (
            img.get("src")
            or img.get("data-original")
            or img.get("data-img-zoom-url")
        )

        if not src:
            continue

        if src.startswith("//"):
            src = "https:" + src

        if src.startswith("/"):
            src = SOURCE_URL.rstrip("/") + src

        # ============================================
        # Увеличиваем изображение Tilda до 720px
        # ============================================

        src = re.sub(
            r"/-/resize/\d+x/",
            "/-/resize/720x/",
            src
        )

        return src

    # ================================================
    # Если изображение находится в background-image
    # ================================================

    for elem in block.find_all():

        style = elem.get("style", "")

        match = re.search(
            r'background-image:\s*url\(["\']?([^"\')]+)',
            style
        )

        if match:

            src = match.group(1)

            if src.startswith("//"):
                src = "https:" + src

            # Увеличиваем Tilda-картинку
            src = re.sub(
                r"/-/resize/\d+x/",
                "/-/resize/720x/",
                src
            )

            return src

    return None

# ============================================================
# ПОИСК БЛОКОВ МЕРОПРИЯТИЙ
# ============================================================

def find_event_blocks(soup):

    blocks = []

    # На сайте мероприятия находятся в блоках uc-day...
    for elem in soup.select('[class*="uc-day"]'):

        classes = elem.get("class", [])

        is_event = False

        for cls in classes:

            if cls.startswith("uc-day"):
                is_event = True
                break

        if is_event:
            blocks.append(elem)

    return blocks


# ============================================================
# ПАРСИНГ ОДНОГО МЕРОПРИЯТИЯ
# ============================================================

def parse_event(block):

    texts = get_block_texts(block)

    if not texts:
        return None

    date_text = find_date(texts)

    time_text = find_time(texts)

    price = find_price(texts)

    ticket_url = find_ticket_url(block)

    source_id = make_source_id(ticket_url)

    title = find_title(
        texts,
        date_text,
        time_text,
        price
    )

    start_date = convert_date(
        date_text,
        time_text
    )

    # Если не нашли дату или название,
    # это скорее всего не мероприятие
    if not title or not start_date:
        return None

    image_url = find_image(block)

    return {
        "title": title,
        "description": None,
        "start_date": start_date,
        "end_date": None,
        "price": price,
        "image_url": image_url,
        "status": "pending",
        "18+": False,
        "source_url": ticket_url,
        "broadcaster": "Stand Up клуб. Ульяновск.",
        "source_id": source_id
    }


# ============================================================
# ПАРСИНГ ВСЕХ МЕРОПРИЯТИЙ
# ============================================================

def parse_events(html):

    print("Парсим мероприятия...")

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    blocks = find_event_blocks(soup)

    events = []

    used_source_ids = set()

    for block in blocks:

        event = parse_event(block)

        if not event:
            continue

        source_id = event.get("source_id")

        # Если нет уникального ID,
        # пропускаем мероприятие
        if not source_id:
            print(
                "Пропущено мероприятие без source_id:",
                event.get("title")
            )
            continue

        # Защита от дубликатов внутри сайта
        if source_id in used_source_ids:
            continue

        used_source_ids.add(source_id)

        events.append(event)

    # Сортируем по дате
    events.sort(
        key=lambda x: x["start_date"]
    )

    return events


# ============================================================
# ПОЛУЧЕНИЕ МЕРОПРИЯТИЙ ИЗ BACKEND
# ============================================================

def get_existing_events(access_token):

    response = requests.get(
        GET_EVENTS_URL,
        headers={
            "Authorization": f"Bearer {access_token}"
        },
        timeout=20
    )

    if response.status_code == 401:

        print("\nBACKEND ВЕРНУЛ 401.")
        print("Проверь логин, пароль и Supabase token.")
        print(response.text)

    response.raise_for_status()

    data = response.json()

    if not isinstance(data, list):

        raise Exception(
            "Backend вернул неожиданный формат:\n"
            + str(data)
        )

    return data


# ============================================================
# ПОЛУЧЕНИЕ SOURCE ID ИЗ BACKEND
# ============================================================

def get_existing_source_ids(existing_events):

    source_ids = set()

    for event in existing_events:

        source_url = event.get("source_url")

        if not source_url:
            continue

        source_id = make_source_id(
            source_url
        )

        if source_id:
            source_ids.add(source_id)

    return source_ids


# ============================================================
# ДОБАВЛЕНИЕ МЕРОПРИЯТИЯ
# ============================================================

def add_event(event, access_token):

    # source_id нужен только для нашей логики.
    # В БД его сейчас нет.
    #
    # Поэтому перед отправкой удаляем его.
    data = event.copy()

    data.pop("source_id", None)

    response = requests.post(
        ADD_EVENT_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        },
        json=data,
        timeout=20
    )

    if response.status_code not in (200, 201):

        print("\nОШИБКА ДОБАВЛЕНИЯ")
        print("HTTP:", response.status_code)
        print("Ответ:", response.text)

        response.raise_for_status()

    return response.json()


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print("ПАРСЕР МЕРОПРИЯТИЙ")
    print("=" * 60)

    # --------------------------------------------------------
    # 1. Получаем сайт
    # --------------------------------------------------------

    html = get_source_html()

    # --------------------------------------------------------
    # 2. Парсим мероприятия
    # --------------------------------------------------------

    events = parse_events(html)

    print(
        f"Найдено мероприятий: {len(events)}"
    )

    print("\nМЕРОПРИЯТИЯ НА САЙТЕ:")

    for event in events:

        print(
            f"- {event['start_date']} | "
            f"{event['title']} | "
            f"{event['price']} ₽ | "
            f"{event['source_id']}"
        )

    # --------------------------------------------------------
    # 3. Авторизация
    # --------------------------------------------------------

    access_token = get_access_token()

    # --------------------------------------------------------
    # 4. Получаем мероприятия из backend
    # --------------------------------------------------------

    print("\nПолучаем мероприятия из backend...")

    existing_events = get_existing_events(
        access_token
    )

    print(
        f"В backend найдено: "
        f"{len(existing_events)}"
    )

    # --------------------------------------------------------
    # 5. Получаем source_id существующих
    # --------------------------------------------------------

    existing_source_ids = get_existing_source_ids(
        existing_events
    )

    print(
        f"Уже известных source_id: "
        f"{len(existing_source_ids)}"
    )

    # --------------------------------------------------------
    # 6. Ищем новые мероприятия
    # --------------------------------------------------------

    new_events = []

    for event in events:

        source_id = event["source_id"]

        if source_id in existing_source_ids:

            print(
                f"\nУже существует: "
                f"{event['title']} "
                f"({source_id})"
            )

        else:

            print(
                f"\nНОВОЕ: "
                f"{event['title']} "
                f"({source_id})"
            )

            new_events.append(event)

    # --------------------------------------------------------
    # 7. Добавляем новые
    # --------------------------------------------------------

    print(
        f"\nНовых мероприятий: "
        f"{len(new_events)}"
    )

    if not new_events:

        print("\nНовых мероприятий нет.")
        print("Ничего добавлять не нужно.")

        return

    print("\nДобавляем новые мероприятия...")

    for event in new_events:

        print(
            f"\nДобавляем: "
            f"{event['title']} | "
            f"{event['start_date']}"
        )

        try:

            result = add_event(
                event,
                access_token
            )

            print(
                "✓ Добавлено"
            )

            if isinstance(result, dict):

                if "id" in result:
                    print(
                        f"  ID backend: "
                        f"{result['id']}"
                    )

        except Exception as error:

            print(
                f"✗ Ошибка добавления: "
                f"{error}"
            )

    print("\n" + "=" * 60)
    print("ГОТОВО")
    print("=" * 60)


# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":
    main()
