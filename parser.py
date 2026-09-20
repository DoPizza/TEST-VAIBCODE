import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


# ============================================================
# НАСТРОЙКИ
# ============================================================

SOURCE_URL = "https://standupclubulsk.ru/"
BACKEND_URL = "https://astonishing-pastelito-e6e568.netlify.app"
SUPABASE_URL = "https://tgyqyrullvofkezmqrkj.supabase.co"

SUPABASE_ANON_KEY = os.environ["SUPABASE_ANON_KEY"]
BACKEND_LOGIN = os.environ["BACKEND_LOGIN"]
BACKEND_PASSWORD = os.environ["BACKEND_PASSWORD"]

GET_EVENTS_URL = f"{BACKEND_URL}/api/events"
ADD_EVENT_URL = f"{BACKEND_URL}/api/events"

# Время на сайте Stand Up клуба — Ульяновск, UTC+4.
EVENT_TIMEZONE = ZoneInfo("Europe/Ulyanovsk")


# ============================================================
# АВТОРИЗАЦИЯ
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
        print("ОШИБКА АВТОРИЗАЦИИ")
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
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
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

    match = re.search(
        r"(\d+(?:[.,]\d+)?)",
        text
    )

    if not match:
        return None

    return match.group(1).replace(",", ".")


def convert_date(date_text, time_text):
    """
    Время на исходном сайте считается временем Ульяновска.

    Например:
        20/09 19:30

    превращается в:
        2026-09-20T15:30:00+00:00

    Это важно, потому что Supabase хранит timestamptz
    в UTC.
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

    year = datetime.now(EVENT_TIMEZONE).year

    try:
        local_dt = datetime(
            year,
            month,
            day,
            hour,
            minute,
            tzinfo=EVENT_TIMEZONE
        )

        utc_dt = local_dt.astimezone(timezone.utc)

        return utc_dt.strftime(
            "%Y-%m-%dT%H:%M:%S+00:00"
        )

    except ValueError:
        return None


# ============================================================
# SOURCE ID
# ============================================================

def make_source_id(url):
    if not url:
        return None

    match = re.search(
        r"(ticketsteam-\d+@\d+)",
        url
    )

    if match:
        return match.group(1)

    return None


# ============================================================
# ССЫЛКА НА БИЛЕТЫ
# ============================================================

def find_ticket_url(block):
    for link in block.find_all("a"):
        href = link.get("href")

        if not href:
            continue

        if "ticketsteam-" in href:
            return href

        if "afisha.yandex.ru" in href:
            return href

    return None


# ============================================================
# ТЕКСТЫ БЛОКА
# ============================================================

def get_block_texts(block):
    texts = []

    # Сначала пробуем Tilda-элементы.
    elements = block.select(".tn-elem")

    # Если LCA оказался не Tilda-блоком,
    # берем весь текст.
    if not elements:
        text = clean_text(
            block.get_text(" ", strip=True)
        )

        return [text] if text else []

    for elem in elements:
        text = clean_text(
            elem.get_text(" ", strip=True)
        )

        if text:
            texts.append(text)

    return texts


# ============================================================
# ДАТА
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
# ВРЕМЯ
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
# ЦЕНА
# ============================================================

def find_price(texts):
    for text in texts:
        if "₽" in text or "руб" in text.lower():
            price = normalize_price(text)

            if price:
                return price

    return None


# ============================================================
# НАЗВАНИЕ
# ============================================================

def find_title(texts, date_text, time_text, price):
    candidates = []

    for text in texts:
        if date_text and date_text in text:
            continue

        if time_text and time_text in text:
            continue

        if "₽" in text or "руб" in text.lower():
            continue

        lower = text.lower()

        if "купить билет" in lower:
            continue

        if "билет" in lower:
            continue

        if len(text) < 2:
            continue

        candidates.append(text)

    if not candidates:
        return None

    return candidates[-1]


# ============================================================
# ИЗОБРАЖЕНИЕ
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

        src = re.sub(
            r"/-/resize/\d+x/",
            "/-/resize/720x/",
            src
        )

        return src

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

            if src.startswith("/"):
                src = SOURCE_URL.rstrip("/") + src

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

def count_matches(text, pattern):
    if not text:
        return 0
    return len(re.findall(pattern, text))


def block_signature(block):
    """
    Проверяет, похож ли контейнер на ОДНО мероприятие.
    Ключевой момент: в контейнере должна быть ровно одна
    дата, одно время и одна цена.

    Это не позволяет случайно взять контейнер дня,
    внутри которого находятся 2 мероприятия.
    """
    text = clean_text(block.get_text(" ", strip=True))
    if not text:
        return None

    dates = re.findall(r"\b\d{1,2}[./-]\d{1,2}\b", text)
    times = re.findall(r"\b\d{1,2}:\d{2}\b", text)

    prices = []
    for m in re.findall(r"\d+(?:[.,]\d+)?\s*(?:₽|руб(?:\.|лей|ля)?)", text, re.I):
        value = re.search(r"\d+(?:[.,]\d+)?", m)
        if value:
            prices.append(value.group(0))

    if len(dates) != 1 or len(times) != 1 or len(prices) != 1:
        return None

    return {
        "date": dates[0],
        "time": times[0],
        "price": prices[0],
    }


def find_event_blocks(soup):
    """
    Одно мероприятие определяется по уникальному source_id.

    ВАЖНО:
    На сайте изображение мероприятия находится в <img>, который
    является дочерним элементом <a> С ТЕМ ЖЕ ticketsteam source_id.

    Например:

    <a href="...ticketsteam-9145@62865734...">
        <img
            data-original="https://static.tildacdn.com/.../909_____1.png"
            src="./.../909_____1.png.webp"
        >
    </a>

    Поэтому изображение связываем НЕ с ближайшим общим контейнером,
    а непосредственно с anchor этого source_id.
    """

    groups = {}

    for link in soup.find_all("a", href=True):
        href = link.get("href", "").strip()

        if "ticketsteam-" not in href and "afisha.yandex.ru" not in href:
            continue

        source_id = make_source_id(href)
        if not source_id:
            continue

        if source_id not in groups:
            groups[source_id] = {
                "source_id": source_id,
                "ticket_url": href,
                "texts": [],
                "links": [],
                "image_url": None
            }

        value = clean_text(link.get_text(" ", strip=True))
        if value:
            groups[source_id]["texts"].append(value)

        groups[source_id]["links"].append(link)

        # ИЩЕМ ИЗОБРАЖЕНИЕ ИМЕННО ВНУТРИ ССЫЛКИ
        # ЭТОГО мероприятия.
        img = link.find("img")

        if img:
            image_url = (
                img.get("data-original")
                or img.get("data-src")
                or img.get("data-lazy-src")
                or img.get("data-original-image")
                or img.get("src")
            )

            if image_url:
                # data-original — правильный постоянный URL Tilda.
                # Относительный src оставляем только как запасной вариант.
                if image_url.startswith("//"):
                    image_url = "https:" + image_url
                elif image_url.startswith("/"):
                    image_url = "https://standupclubulsk.ru" + image_url

                groups[source_id]["image_url"] = image_url

    print(f"Уникальных ссылок на мероприятия: {len(groups)}")

    result = list(groups.values())

    print(f"Блоков мероприятий найдено: {len(result)}")

    # Показываем найденные изображения прямо в логе.
    for event in result:
        print(
            f"ИЗОБРАЖЕНИЕ: {event['source_id']} | "
            f"{event['image_url'] or 'НЕ НАЙДЕНО'}"
        )

    return result


# ============================================================
# ПАРСИНГ ОДНОГО МЕРОПРИЯТИЯ
# ============================================================

def parse_event(event_group):
    """
    Парсит данные непосредственно из ссылок одного source_id.
    Благодаря этому два мероприятия одного дня не объединяются.
    """

    texts = event_group.get("texts", [])
    ticket_url = event_group.get("ticket_url")
    source_id = event_group.get("source_id")
    container = event_group.get("container")

    if not texts or not source_id:
        return None

    date_text = find_date(texts)
    time_text = find_time(texts)
    price = find_price(texts)

    title_candidates = []

    for value in texts:
        lower = value.lower()

        if date_text and date_text in value:
            continue
        if time_text and time_text in value:
            continue
        if "₽" in value or "руб" in lower:
            continue
        if "купить билет" in lower or "билет" in lower:
            continue
        if len(value) >= 2:
            title_candidates.append(value)

    title = title_candidates[-1] if title_candidates else None
    start_date = convert_date(date_text, time_text)

    if not title or not start_date:
        return None

    start_dt = datetime.fromisoformat(start_date)
    end_dt = start_dt + timedelta(hours=4)
    end_date = end_dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")

    image_url = event_group.get("image_url")

    return {
        "title": title,
        "description": "парсер Stand Up клуба",
        "start_date": start_date,
        "end_date": end_date,
        "price": price,
        "image_url": image_url,
        "status": "approved",
        "18+": True,
        "source_url": ticket_url,
        "broadcaster": "Stand Up клуб. Ульяновск.",
        "source_id": source_id
    }


# ============================================================
# ПАРСИНГ ВСЕХ МЕРОПРИЯТИЙ
# ============================================================

def parse_events(html):
    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    blocks = find_event_blocks(
        soup
    )

    print(
        f"Блоков мероприятий найдено: "
        f"{len(blocks)}"
    )

    events = []

    for block in blocks:

        try:
            event = parse_event(
                block
            )

            if not event:
                print(
                    "Пропущен блок: "
                    "не удалось определить дату/время/название."
                )
                continue

            if not event.get(
                "source_id"
            ):
                print(
                    f"Пропущено без source_id: "
                    f"{event.get('title')}"
                )
                continue

            events.append(
                event
            )

        except Exception as error:
            print(
                f"Ошибка обработки блока: "
                f"{error}"
            )

    # --------------------------------------------------------
    # Финальная дедупликация
    # --------------------------------------------------------

    unique_events = []
    seen_ids = set()

    for event in events:

        source_id = event[
            "source_id"
        ]

        if source_id in seen_ids:
            continue

        seen_ids.add(
            source_id
        )

        unique_events.append(
            event
        )

    return unique_events


# ============================================================
# ПОЛУЧЕНИЕ СОБЫТИЙ ИЗ BACKEND
# ============================================================

def get_existing_events(
    access_token
):
    response = requests.get(
        GET_EVENTS_URL,
        headers={
            "Authorization":
                f"Bearer {access_token}"
        },
        timeout=20
    )

    if response.status_code == 401:
        print("\nBACKEND ВЕРНУЛ 401.")
        print(
            "Проверь логин, пароль "
            "и Supabase token."
        )
        print(response.text)

    response.raise_for_status()

    data = response.json()

    if not isinstance(
        data,
        list
    ):
        raise Exception(
            "Backend вернул неожиданный формат:\n"
            + str(data)
        )

    return data


# ============================================================
# SOURCE ID СУЩЕСТВУЮЩИХ СОБЫТИЙ
# ============================================================

def get_existing_source_ids(
    existing_events
):
    source_ids = set()

    for event in existing_events:

        source_url = event.get(
            "source_url"
        )

        if not source_url:
            continue

        source_id = make_source_id(
            source_url
        )

        if source_id:
            source_ids.add(
                source_id
            )

    return source_ids


# ============================================================
# ДОБАВЛЕНИЕ СОБЫТИЯ
# ============================================================

def add_event(
    event,
    access_token
):
    data = event.copy()

    # source_id используется только
    # для дедупликации.
    data.pop(
        "source_id",
        None
    )

    response = requests.post(
        ADD_EVENT_URL,
        headers={
            "Authorization":
                f"Bearer {access_token}",
            "Content-Type":
                "application/json"
        },
        json=data,
        timeout=20
    )

    if response.status_code not in (
        200,
        201
    ):
        print("\nОШИБКА ДОБАВЛЕНИЯ")
        print(
            "HTTP:",
            response.status_code
        )
        print(
            "Ответ:",
            response.text
        )
        response.raise_for_status()

    return response.json()


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print("ПАРСЕР МЕРОПРИЯТИЙ STAND UP КЛУБА")
    print("=" * 60)

    # --------------------------------------------------------
    # 1. Сайт
    # --------------------------------------------------------

    html = get_source_html()

    # --------------------------------------------------------
    # 2. Парсинг
    # --------------------------------------------------------

    events = parse_events(
        html
    )

    print(
        f"\nВсего распознано мероприятий: "
        f"{len(events)}"
    )

    print(
        "\nРАСПОЗНАННЫЕ МЕРОПРИЯТИЯ:"
    )

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
    # 4. Существующие события
    # --------------------------------------------------------

    print(
        "\nПолучаем мероприятия из backend..."
    )

    existing_events = get_existing_events(
        access_token
    )

    print(
        f"В backend найдено: "
        f"{len(existing_events)}"
    )

    existing_source_ids = (
        get_existing_source_ids(
            existing_events
        )
    )

    print(
        f"Уже известных source_id: "
        f"{len(existing_source_ids)}"
    )

    # --------------------------------------------------------
    # 5. Новые события
    # --------------------------------------------------------

    new_events = []

    for event in events:

        source_id = event[
            "source_id"
        ]

        if source_id in existing_source_ids:

            print(
                f"Уже существует: "
                f"{event['start_date']} | "
                f"{event['title']} | "
                f"{source_id}"
            )

        else:

            print(
                f"НОВОЕ: "
                f"{event['start_date']} | "
                f"{event['title']} | "
                f"{source_id}"
            )

            new_events.append(
                event
            )

    # --------------------------------------------------------
    # 6. Добавление
    # --------------------------------------------------------

    print(
        f"\nНовых мероприятий: "
        f"{len(new_events)}"
    )

    if not new_events:

        print(
            "\nНовых мероприятий нет."
        )

        return

    print(
        "\nДобавляем новые мероприятия..."
    )

    added = 0

    for event in new_events:

        try:

            result = add_event(
                event,
                access_token
            )

            added += 1

            print(
                f"✓ Добавлено: "
                f"{event['title']} | "
                f"{event['start_date']}"
            )

            if (
                isinstance(result, dict)
                and "id" in result
            ):
                print(
                    f"  ID backend: "
                    f"{result['id']}"
                )

        except Exception as error:

            print(
                f"✗ Ошибка добавления "
                f"{event['title']}: "
                f"{error}"
            )

    print("\n" + "=" * 60)
    print(
        f"ГОТОВО. Добавлено: {added}"
    )
    print("=" * 60)


# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":
    main()
