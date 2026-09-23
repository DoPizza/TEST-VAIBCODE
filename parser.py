import os
import re
import requests

from bs4 import BeautifulSoup
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


# ============================================================
# НАСТРОЙКИ
# ============================================================

SOURCE_URL = "https://standupclubulsk.ru/"

BACKEND_URL = "https://astonishing-pastelito-e6e568.netlify.app"

SUPABASE_URL = "https://tgyqyrullvofkezmqrkj.supabase.co"


# ============================================================
# GITHUB SECRETS
# ============================================================

SUPABASE_ANON_KEY = os.environ["SUPABASE_ANON_KEY"]

BACKEND_LOGIN = os.environ["BACKEND_LOGIN"]

BACKEND_PASSWORD = os.environ["BACKEND_PASSWORD"]


# ============================================================
# API
# ============================================================

GET_EVENTS_URL = f"{BACKEND_URL}/api/events"

ADD_EVENT_URL = f"{BACKEND_URL}/api/events"


# ============================================================
# ВРЕМЕННАЯ ЗОНА
# ============================================================

# Время мероприятий на сайте Stand Up клуба —
# время Ульяновска, UTC+4.

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

        print("\nОШИБКА АВТОРИЗАЦИИ")

        print(
            "HTTP:",
            response.status_code
        )

        print(
            "Ответ:",
            response.text
        )

        response.raise_for_status()

    data = response.json()

    access_token = data.get(
        "access_token"
    )

    if not access_token:

        raise Exception(
            "Supabase не вернул access_token"
        )

    print(
        "Авторизация успешна."
    )

    return access_token


# ============================================================
# ПОЛУЧЕНИЕ САЙТА
# ============================================================

def get_source_html():

    print(
        "\nПолучаем сайт Stand Up клуба..."
    )

    response = requests.get(

        SOURCE_URL,

        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/138.0 Safari/537.36"
            )
        },

        timeout=30
    )

    response.raise_for_status()

    print(
        "Сайт успешно получен."
    )

    return response.text


# ============================================================
# ОЧИСТКА ТЕКСТА
# ============================================================

def clean_text(text):

    if not text:
        return None

    text = text.replace(
        "\xa0",
        " "
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ============================================================
# ЦЕНА
# ============================================================

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

    value = match.group(1)

    value = value.replace(
        ",",
        "."
    )

    try:

        # В БД price имеет тип bigint.

        return int(
            float(value)
        )

    except ValueError:

        return None


# ============================================================
# ПРЕОБРАЗОВАНИЕ ДАТЫ
# ============================================================

def convert_date(
    date_text,
    time_text
):

    """
    Например:

    20/09
    19:30

    превращается в:

    2026-09-20T15:30:00+00:00

    Потому что Ульяновск = UTC+4.
    """

    if not date_text or not time_text:

        return None

    date_text = clean_text(
        date_text
    )

    time_text = clean_text(
        time_text
    )

    # День и месяц.

    match = re.search(
        r"(\d{1,2})[./-](\d{1,2})",
        date_text
    )

    if not match:

        return None

    day = int(
        match.group(1)
    )

    month = int(
        match.group(2)
    )

    # Часы и минуты.

    time_match = re.search(
        r"(\d{1,2}):(\d{2})",
        time_text
    )

    if not time_match:

        return None

    hour = int(
        time_match.group(1)
    )

    minute = int(
        time_match.group(2)
    )

    year = datetime.now(
        EVENT_TIMEZONE
    ).year

    try:

        local_dt = datetime(
            year,
            month,
            day,
            hour,
            minute,
            tzinfo=EVENT_TIMEZONE
        )

        utc_dt = local_dt.astimezone(
            timezone.utc
        )

        return utc_dt.strftime(
            "%Y-%m-%dT%H:%M:%S+00:00"
        )

    except ValueError:

        return None


# ============================================================
# EXTERNAL ID
# ============================================================

def make_external_id(url):

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
# ПОИСК ССЫЛКИ НА БИЛЕТ
# ============================================================

def find_ticket_url(block):

    for link in block.find_all(
        "a",
        href=True
    ):

        href = link.get(
            "href",
            ""
        ).strip()

        if not href:

            continue

        if "ticketsteam-" in href:

            return href

        if "afisha.yandex.ru" in href:

            return href

    return None


# ============================================================
# ПОЛУЧЕНИЕ ТЕКСТОВ
# ============================================================

def get_block_texts(block):

    texts = []

    elements = block.select(
        ".tn-elem"
    )

    # Если это не Tilda-блок.

    if not elements:

        text = clean_text(
            block.get_text(
                " ",
                strip=True
            )
        )

        return (
            [text]
            if text
            else []
        )

    for element in elements:

        text = clean_text(
            element.get_text(
                " ",
                strip=True
            )
        )

        if text:

            texts.append(
                text
            )

    return texts


# ============================================================
# ПОИСК ДАТЫ
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
# ПОИСК ВРЕМЕНИ
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
# ПОИСК ЦЕНЫ
# ============================================================

def find_price(texts):

    for text in texts:

        lower = text.lower()

        if (
            "₽" in text
            or "руб" in lower
        ):

            price = normalize_price(
                text
            )

            if price is not None:

                return price

    return None


# ============================================================
# ПОИСК НАЗВАНИЯ
# ============================================================

def find_title(
    texts,
    date_text,
    time_text
):

    candidates = []

    for text in texts:

        lower = text.lower()

        # Дата.

        if (
            date_text
            and date_text in text
        ):

            continue

        # Время.

        if (
            time_text
            and time_text in text
        ):

            continue

        # Цена.

        if "₽" in text:

            continue

        if "руб" in lower:

            continue

        # Служебные надписи.

        if "купить билет" in lower:

            continue

        if "билет" in lower:

            continue

        if len(text) < 2:

            continue

        candidates.append(
            text
        )

    if not candidates:

        return None

    return candidates[-1]


# ============================================================
# НОРМАЛИЗАЦИЯ URL ИЗОБРАЖЕНИЯ
# ============================================================

def normalize_image_url(
    image_url
):

    if not image_url:

        return None

    image_url = image_url.strip()

    if image_url.startswith("//"):

        image_url = (
            "https:"
            + image_url
        )

    elif image_url.startswith("/"):

        image_url = (
            SOURCE_URL.rstrip("/")
            + image_url
        )

    # Если Tilda отдаёт уменьшенную
    # картинку, просим вариант 720px.

    image_url = re.sub(
        r"/-/resize/\d+x/",
        "/-/resize/720x/",
        image_url
    )

    return image_url


# ============================================================
# ПОИСК ИЗОБРАЖЕНИЯ
# ============================================================

def find_image_from_link(
    link
):

    img = link.find(
        "img"
    )

    if not img:

        return None

    # В первую очередь берём data-original,
    # потому что там обычно нормальный
    # оригинальный URL Tilda.

    image_url = (

        img.get("data-original")

        or img.get("data-src")

        or img.get("data-lazy-src")

        or img.get("data-original-image")

        or img.get("src")
    )

    return normalize_image_url(
        image_url
    )


# ============================================================
# ПОИСК МЕРОПРИЯТИЙ
# ============================================================

def find_event_blocks(soup):

    groups = {}

    for link in soup.find_all(
        "a",
        href=True
    ):

        href = link.get(
            "href",
            ""
        ).strip()

        # Нас интересуют ссылки
        # на Ticketsteam или Яндекс Афишу.

        if (
            "ticketsteam-" not in href
            and "afisha.yandex.ru" not in href
        ):

            continue

        # Получаем уникальный external_id.

        external_id = make_external_id(
            href
        )

        if not external_id:

            continue

        # Создаём группу.

        if external_id not in groups:

            groups[external_id] = {

                "external_id":
                    external_id,

                "ticket_url":
                    href,

                "texts":
                    [],

                "links":
                    [],

                "image_url":
                    None
            }

        # Текст ссылки.

        value = clean_text(
            link.get_text(
                " ",
                strip=True
            )
        )

        if value:

            groups[
                external_id
            ][
                "texts"
            ].append(
                value
            )

        # Сохраняем ссылку.

        groups[
            external_id
        ][
            "links"
        ].append(
            link
        )

        # Ищем картинку непосредственно
        # внутри ссылки мероприятия.

        image_url = find_image_from_link(
            link
        )

        if image_url:

            groups[
                external_id
            ][
                "image_url"
            ] = image_url

    print(
        f"\nУникальных мероприятий: "
        f"{len(groups)}"
    )

    # Вывод изображений в лог.

    for external_id, event in groups.items():

        print(
            f"ИЗОБРАЖЕНИЕ: "
            f"{external_id} | "
            f"{event['image_url'] or 'НЕ НАЙДЕНО'}"
        )

    return list(
        groups.values()
    )


# ============================================================
# ПАРСИНГ ОДНОГО МЕРОПРИЯТИЯ
# ============================================================

def parse_event(
    event_group
):

    texts = event_group.get(
        "texts",
        []
    )

    ticket_url = event_group.get(
        "ticket_url"
    )

    external_id = event_group.get(
        "external_id"
    )

    image_url = event_group.get(
        "image_url"
    )

    if (
        not texts
        or not external_id
    ):

        return None

    # Дата.

    date_text = find_date(
        texts
    )

    # Время.

    time_text = find_time(
        texts
    )

    # Цена.

    price = find_price(
        texts
    )

    # Название.

    title = find_title(
        texts,
        date_text,
        time_text
    )

    # Дата в формате Supabase.

    start_date = convert_date(
        date_text,
        time_text
    )

    if (
        not title
        or not start_date
    ):

        return None

    # ========================================================
    # СОБЫТИЕ ПОД НОВУЮ ТАБЛИЦУ
    # ========================================================

    event = {

        # ------------------------------
        # Название
        # ------------------------------

        "title": title,

        # ------------------------------
        # Описание
        # ------------------------------

        "description":
            "Мероприятие Stand Up клуба",

        # ------------------------------
        # Статус
        # ------------------------------

        "status":
            "approved",

        # ------------------------------
        # Дата начала
        # ------------------------------

        "start_date":
            start_date,

        # ------------------------------
        # Дата окончания
        # ------------------------------
        #
        # Оставляем None.
        #
        # Твой Supabase trigger должен
        # поставить start_date + 12 часов.

        "end_date":
            None,

        # ------------------------------
        # Цена
        # ------------------------------

        "price":
            price,

        # ------------------------------
        # Картинка
        # ------------------------------

        "image_url":
            image_url,

        # ------------------------------
        # Источник
        # ------------------------------

        "source_url":
            ticket_url,

        "source":
            "standupclub",

        # ------------------------------
        # Организатор
        # ------------------------------

        "broadcaster":
            "Stand Up клуб. Ульяновск.",

        "broadcaster_url":
            SOURCE_URL,

        # ------------------------------
        # Возраст
        # ------------------------------

        "age":
            18,

        # ------------------------------
        # Тип мероприятия
        # ------------------------------

        "type":
            "стендап",

        # ------------------------------
        # Адрес
        # ------------------------------

        "address":
            "Ульяновск",

        # ------------------------------
        # Уникальный ID
        # ------------------------------

        "external_id":
            external_id
    }

    return event


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
        f"\nБлоков мероприятий найдено: "
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
                    "Пропущено мероприятие: "
                    "не удалось определить "
                    "дату/время/название."
                )

                continue

            events.append(
                event
            )

        except Exception as error:

            print(
                f"Ошибка обработки: "
                f"{error}"
            )

    # ========================================================
    # ФИНАЛЬНАЯ ДЕДУПЛИКАЦИЯ
    # ========================================================

    unique_events = []

    seen_ids = set()

    for event in events:

        external_id = event.get(
            "external_id"
        )

        if not external_id:

            continue

        if external_id in seen_ids:

            continue

        seen_ids.add(
            external_id
        )

        unique_events.append(
            event
        )

    return unique_events


# ============================================================
# ПОЛУЧЕНИЕ СУЩЕСТВУЮЩИХ МЕРОПРИЯТИЙ
# ============================================================

def get_existing_events(
    access_token
):

    print(
        "\nПолучаем мероприятия из backend..."
    )

    response = requests.get(

        GET_EVENTS_URL,

        headers={
            "Authorization":
                f"Bearer {access_token}"
        },

        timeout=20
    )

    if response.status_code == 401:

        print(
            "\nBACKEND ВЕРНУЛ 401."
        )

        print(
            "Проверь BACKEND_LOGIN, "
            "BACKEND_PASSWORD "
            "и Supabase token."
        )

        print(
            response.text
        )

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

    print(
        f"В backend найдено: "
        f"{len(data)}"
    )

    return data


# ============================================================
# ПОЛУЧЕНИЕ EXISTING EXTERNAL_ID
# ============================================================

def get_existing_external_ids(
    existing_events
):

    external_ids = set()

    for event in existing_events:

        external_id = event.get(
            "external_id"
        )

        if not external_id:

            continue

        external_ids.add(
            str(external_id)
        )

    return external_ids


# ============================================================
# ДОБАВЛЕНИЕ МЕРОПРИЯТИЯ
# ============================================================

def add_event(
    event,
    access_token
):

    response = requests.post(

        ADD_EVENT_URL,

        headers={

            "Authorization":
                f"Bearer {access_token}",

            "Content-Type":
                "application/json"
        },

        json=event,

        timeout=20
    )

    if response.status_code not in (
        200,
        201
    ):

        print(
            "\nОШИБКА ДОБАВЛЕНИЯ"
        )

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

    print(
        "=" * 60
    )

    print(
        "ПАРСЕР STAND UP КЛУБА"
    )

    print(
        "=" * 60
    )

    # ========================================================
    # 1. Получение сайта
    # ========================================================

    html = get_source_html()

    # ========================================================
    # 2. Парсинг
    # ========================================================

    events = parse_events(
        html
    )

    print(
        f"\nВсего распознано мероприятий: "
        f"{len(events)}"
    )

    # ========================================================
    # 3. Вывод распознанных
    # ========================================================

    print(
        "\nРАСПОЗНАННЫЕ МЕРОПРИЯТИЯ:"
    )

    for event in events:

        print(

            f"- "
            f"{event.get('start_date')} | "
            f"{event.get('title')} | "
            f"{event.get('price')} ₽ | "
            f"age={event.get('age')} | "
            f"type={event.get('type')} | "
            f"external_id={event.get('external_id')}"
        )

    # ========================================================
    # 4. Авторизация
    # ========================================================

    access_token = get_access_token()

    # ========================================================
    # 5. Существующие мероприятия
    # ========================================================

    existing_events = get_existing_events(
        access_token
    )

    # ========================================================
    # 6. Существующие external_id
    # ========================================================

    existing_external_ids = (
        get_existing_external_ids(
            existing_events
        )
    )

    print(
        f"\nУже известных external_id: "
        f"{len(existing_external_ids)}"
    )

    # ========================================================
    # 7. Определяем новые мероприятия
    # ========================================================

    new_events = []

    for event in events:

        external_id = str(
            event.get(
                "external_id"
            )
        )

        if external_id in existing_external_ids:

            print(

                f"УЖЕ СУЩЕСТВУЕТ: "
                f"{event['title']} | "
                f"{external_id}"
            )

        else:

            print(

                f"НОВОЕ: "
                f"{event['title']} | "
                f"{event['start_date']} | "
                f"age={event['age']} | "
                f"external_id={external_id}"
            )

            new_events.append(
                event
            )

    # ========================================================
    # 8. Добавление
    # ========================================================

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
                f"\n✓ Добавлено: "
                f"{event['title']}"
            )

            print(
                f"  external_id: "
                f"{event['external_id']}"
            )

            print(
                f"  start_date: "
                f"{event['start_date']}"
            )

            print(
                f"  end_date: "
                f"{event['end_date']}"
            )

            print(
                f"  price: "
                f"{event['price']}"
            )

            print(
                f"  age: "
                f"{event['age']}"
            )

            print(
                f"  type: "
                f"{event['type']}"
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

                f"\n✗ Ошибка добавления "
                f"{event['title']}: "
                f"{error}"
            )

    # ========================================================
    # 9. Готово
    # ========================================================

    print(
        "\n" + "=" * 60
    )

    print(
        f"ГОТОВО. Добавлено: {added}"
    )

    print(
        "=" * 60
    )


# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":

    main()
