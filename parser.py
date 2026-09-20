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

def find_event_blocks(soup):
    """
    ВАЖНО:

    Старый вариант искал [class*="uc-day"].
    Это была ошибка: такой блок соответствует ДНЮ,
    а не отдельному мероприятию.

    Если в один день два мероприятия, старый парсер
    видел только один блок и поэтому получалось:

        19/09 -> 1
        20/09 -> 1
        23/09 -> 1
        ...

    Новый вариант ищет КАЖДУЮ уникальную ссылку
    ticketsteam-... и собирает вокруг нее отдельный
    блок мероприятия.

    На текущем сайте это позволяет получить все события,
    включая два мероприятия в один день.
    """

    # --------------------------------------------------------
    # 1. Собираем ссылки на все мероприятия
    # --------------------------------------------------------

    links_by_href = {}

    for link in soup.find_all("a"):
        href = link.get("href")

        if not href:
            continue

        if (
            "ticketsteam-" not in href
            and "afisha.yandex.ru" not in href
        ):
            continue

        # Удаляем якоря и лишние пробелы.
        href = href.strip()

        links_by_href.setdefault(
            href,
            []
        ).append(link)

    print(
        f"Уникальных ссылок на мероприятия: "
        f"{len(links_by_href)}"
    )

    blocks = []

    # --------------------------------------------------------
    # 2. Для каждой ссылки на билет ищем
    #    общий минимальный контейнер
    # --------------------------------------------------------

    for href, links in links_by_href.items():

        if not links:
            continue

        first_link = links[0]

        # Собираем множества родителей для каждого
        # повторения одной и той же ссылки.
        ancestor_lists = []

        for link in links:

            ancestors = []
            current = link

            while current is not None:

                if getattr(
                    current,
                    "name",
                    None
                ):

                    ancestors.append(
                        current
                    )

                current = current.parent

            ancestor_lists.append(
                ancestors
            )

        # Ищем ближайшего общего родителя.
        common = None

        for candidate in ancestor_lists[0]:

            if all(
                candidate in ancestors
                for ancestors in ancestor_lists[1:]
            ):

                common = candidate
                break

        if common is None:
            common = first_link.parent

        # ----------------------------------------------------
        # Проверяем, что это действительно мероприятие.
        # ----------------------------------------------------

        texts = get_block_texts(
            common
        )

        date_text = find_date(
            texts
        )

        time_text = find_time(
            texts
        )

        price = find_price(
            texts
        )

        if (
            not date_text
            or not time_text
        ):
            # Иногда общий родитель слишком маленький.
            # Поднимаемся вверх до подходящего контейнера.
            current = common

            for _ in range(8):

                current = current.parent

                if current is None:
                    break

                texts = get_block_texts(
                    current
                )

                date_text = find_date(
                    texts
                )

                time_text = find_time(
                    texts
                )

                price = find_price(
                    texts
                )

                if (
                    date_text
                    and time_text
                ):

                    common = current
                    break

        blocks.append(
            common
        )

    # --------------------------------------------------------
    # 3. Убираем дубли контейнеров
    # --------------------------------------------------------

    unique_blocks = []
    seen_objects = set()

    for block in blocks:

        object_id = id(block)

        if object_id in seen_objects:
            continue

        seen_objects.add(
            object_id
        )

        unique_blocks.append(
            block
        )

    return unique_blocks


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

    if not title or not start_date:
        return None

    # --------------------------------------------------------
    # END DATE = START DATE + 4 ЧАСА
    # --------------------------------------------------------

    start_dt = datetime.fromisoformat(
        start_date
    )

    end_dt = start_dt + timedelta(
        hours=4
    )

    end_date = end_dt.strftime(
        "%Y-%m-%dT%H:%M:%S+00:00"
    )

    image_url = find_image(
        block
    )

    return {
        "title": title,
        "description": "парсер Stand Up клуба",
        "start_date": start_date,
        "end_date": end_date,
        "price": price,
        "image_url": image_url,
        "status": "approved",
        "18+": False,
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
