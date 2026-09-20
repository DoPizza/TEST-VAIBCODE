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


# ============================================================
# ДАННЫЕ ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ / GITHUB SECRETS
# ============================================================

SUPABASE_ANON_KEY = os.environ["SUPABASE_ANON_KEY"]
BACKEND_LOGIN = os.environ["BACKEND_LOGIN"]
BACKEND_PASSWORD = os.environ["BACKEND_PASSWORD"]


# ============================================================
# URL BACKEND
# ============================================================

GET_EVENTS_URL = f"{BACKEND_URL}/api/events"
ADD_EVENT_URL = f"{BACKEND_URL}/api/events"


# ============================================================
# ЧАСОВОЙ ПОЯС МЕРОПРИЯТИЙ
# ============================================================

# На сайте Stand Up клуба время указано по Ульяновску.
EVENT_TIMEZONE = ZoneInfo("Europe/Ulyanovsk")


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
        raise Exception(
            "Supabase не вернул access_token"
        )

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
# НОРМАЛИЗАЦИЯ ЦЕНЫ
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

    return match.group(1).replace(
        ",",
        "."
    )


# ============================================================
# ПРЕОБРАЗОВАНИЕ ДАТЫ И ВРЕМЕНИ
# ============================================================

def convert_date(date_text, time_text):

    """
    Сайт:

        20/09
        19:30

    Считаем это временем Ульяновска.

    Например:

        20/09 19:30
        Ульяновск UTC+4

    В БД отправляем:

        2026-09-20T15:30:00+00:00

    То есть в UTC.
    """

    date_text = clean_text(
        date_text
    )

    time_text = clean_text(
        time_text
    )

    if not date_text or not time_text:
        return None

    # --------------------------------------------------------
    # ДЕНЬ / МЕСЯЦ
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # ЧАС / МИНУТЫ
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # ГОД
    # --------------------------------------------------------

    year = datetime.now().year

    try:

        # Время с сайта считаем временем Ульяновска
        local_dt = datetime(
            year,
            month,
            day,
            hour,
            minute,
            tzinfo=EVENT_TIMEZONE
        )

        # Переводим в UTC для Supabase
        utc_dt = local_dt.astimezone(
            timezone.utc
        )

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
# ПОЛУЧЕНИЕ ТЕКСТОВЫХ ЭЛЕМЕНТОВ
# ============================================================

def get_block_texts(block):

    texts = []

    for elem in block.select(".tn-elem"):

        text = elem.get_text(
            " ",
            strip=True
        )

        text = clean_text(
            text
        )

        if text:
            texts.append(text)

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

        if (
            "₽" in text
            or "руб" in text.lower()
        ):

            price = normalize_price(
                text
            )

            if price:
                return price

    return None


# ============================================================
# ПОИСК НАЗВАНИЯ
# ============================================================

def find_title(
    texts,
    date_text,
    time_text,
    price
):

    candidates = []

    for text in texts:

        # Дата
        if (
            date_text
            and date_text in text
        ):
            continue

        # Время
        if (
            time_text
            and time_text in text
        ):
            continue

        # Цена
        if (
            "₽" in text
            or "руб" in text.lower()
        ):
            continue

        lower = text.lower()

        # Кнопки билетов
        if "купить билет" in lower:
            continue

        if "билет" in lower:
            continue

        # Технические короткие элементы
        if len(text) < 2:
            continue

        candidates.append(text)

    if not candidates:
        return None

    # Для текущего сайта название обычно
    # находится последним среди подходящих элементов.
    return candidates[-1]


# ============================================================
# ПОИСК ИЗОБРАЖЕНИЯ
# ============================================================

def find_image(block):

    images = block.find_all(
        "img"
    )

    for img in images:

        src = (
            img.get("src")
            or img.get("data-original")
            or img.get("data-img-zoom-url")
        )

        if not src:
            continue

        if src.startswith("//"):

            src = (
                "https:"
                + src
            )

        if src.startswith("/"):

            src = (
                SOURCE_URL.rstrip("/")
                + src
            )

        # Увеличиваем Tilda-картинку
        src = re.sub(
            r"/-/resize/\d+x/",
            "/-/resize/720x/",
            src
        )

        return src

    # --------------------------------------------------------
    # BACKGROUND-IMAGE
    # --------------------------------------------------------

    for elem in block.find_all():

        style = elem.get(
            "style",
            ""
        )

        match = re.search(
            r'background-image:\s*url\(["\']?([^"\')]+)',
            style
        )

        if match:

            src = match.group(1)

            if src.startswith("//"):

                src = (
                    "https:"
                    + src
                )

            if src.startswith("/"):

                src = (
                    SOURCE_URL.rstrip("/")
                    + src
                )

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

    for elem in soup.select(
        '[class*="uc-day"]'
    ):

        classes = elem.get(
            "class",
            []
        )

        is_event = False

        for cls in classes:

            if cls.startswith(
                "uc-day"
            ):

                is_event = True

                break

        if is_event:
            blocks.append(elem)

    return blocks


# ============================================================
# ПАРСИНГ ОДНОГО МЕРОПРИЯТИЯ
# ============================================================

def parse_event(block):

    texts = get_block_texts(
        block
    )

    if not texts:
        return None

    # --------------------------------------------------------
    # ОСНОВНЫЕ ДАННЫЕ
    # --------------------------------------------------------

    date_text = find_date(
        texts
    )

    time_text = find_time(
        texts
    )

    price = find_price(
        texts
    )

    ticket_url = find_ticket_url(
        block
    )

    source_id = make_source_id(
        ticket_url
    )

    title = find_title(
        texts,
        date_text,
        time_text,
        price
    )

    # --------------------------------------------------------
    # START DATE
    # --------------------------------------------------------

    start_date = convert_date(
        date_text,
        time_text
    )

    # Если нет названия или даты,
    # это не нормальное мероприятие.
    if not title or not start_date:

        return None

    # --------------------------------------------------------
    # END DATE
    # --------------------------------------------------------
    #
    # Продолжительность мероприятия
    # условно принимаем равной 4 часам.
    #
    # start_date уже находится в UTC.
    # Поэтому просто прибавляем 4 часа.
    # --------------------------------------------------------

    start_dt = datetime.fromisoformat(
        start_date
    )

    end_dt = (
        start_dt
        + timedelta(hours=4)
    )

    end_date = end_dt.strftime(
        "%Y-%m-%dT%H:%M:%S+00:00"
    )

    # --------------------------------------------------------
    # ИЗОБРАЖЕНИЕ
    # --------------------------------------------------------

    image_url = find_image(
        block
    )

    # --------------------------------------------------------
    # РЕЗУЛЬТАТ
    # --------------------------------------------------------

    return {

        "title": title,

        "description":
            "парсер Stand Up клуба",

        "start_date":
            start_date,

        "end_date":
            end_date,

        "price":
            price,

        "image_url":
            image_url,

        "status":
            "approved",

        "18+":
            False,

        "source_url":
            ticket_url,

        "broadcaster":
            "Stand Up клуб. Ульяновск.",

        # Нужен только для дедупликации.
        # В БД не отправляется.
        "source_id":
            source_id
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
        f"Найдено блоков: {len(blocks)}"
    )

    events = []

    for block in blocks:

        try:

            event = parse_event(
                block
            )

            if not event:
                continue

            # Без source_id невозможно
            # надежно определить дубль.
            if not event.get(
                "source_id"
            ):

                print(
                    "Пропущено без source_id: "
                    f"{event.get('title')}"
                )

                continue

            events.append(
                event
            )

        except Exception as error:

            print(
                "Ошибка обработки блока: "
                f"{error}"
            )

    # --------------------------------------------------------
    # УБИРАЕМ ДУБЛИ ВНУТРИ САМОГО САЙТА
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
# ПОЛУЧЕНИЕ МЕРОПРИЯТИЙ ИЗ BACKEND
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

        print(
            "\nBACKEND ВЕРНУЛ 401."
        )

        print(
            "Проверь логин, пароль "
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
            "Backend вернул неожиданный "
            "формат:\n"
            + str(data)
        )

    return data


# ============================================================
# SOURCE ID СУЩЕСТВУЮЩИХ МЕРОПРИЯТИЙ
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
# ДОБАВЛЕНИЕ МЕРОПРИЯТИЯ
# ============================================================

def add_event(
    event,
    access_token
):

    # Делаем копию,
    # чтобы не менять исходный объект.
    data = event.copy()

    # source_id сейчас нужен только
    # для дедупликации и не хранится в БД.
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
        "ПАРСЕР МЕРОПРИЯТИЙ"
    )

    print(
        "=" * 60
    )

    # --------------------------------------------------------
    # 1. Получаем сайт
    # --------------------------------------------------------

    html = get_source_html()

    # --------------------------------------------------------
    # 2. Парсим мероприятия
    # --------------------------------------------------------

    events = parse_events(
        html
    )

    print(
        f"\nНайдено мероприятий: "
        f"{len(events)}"
    )

    print(
        "\nМЕРОПРИЯТИЯ НА САЙТЕ:"
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

    access_token = (
        get_access_token()
    )

    # --------------------------------------------------------
    # 4. Получаем мероприятия из backend
    # --------------------------------------------------------

    print(
        "\nПолучаем мероприятия "
        "из backend..."
    )

    existing_events = (
        get_existing_events(
            access_token
        )
    )

    print(
        f"В backend найдено: "
        f"{len(existing_events)}"
    )

    # --------------------------------------------------------
    # 5. Получаем существующие source_id
    # --------------------------------------------------------

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
    # 6. Ищем новые мероприятия
    # --------------------------------------------------------

    new_events = []

    for event in events:

        source_id = event[
            "source_id"
        ]

        if source_id in (
            existing_source_ids
        ):

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

            new_events.append(
                event
            )

    # --------------------------------------------------------
    # 7. Добавляем новые
    # --------------------------------------------------------

    print(
        f"\nНовых мероприятий: "
        f"{len(new_events)}"
    )

    if not new_events:

        print(
            "\nНовых мероприятий нет."
        )

        print(
            "Ничего добавлять не нужно."
        )

        return

    print(
        "\nДобавляем новые мероприятия..."
    )

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

            if isinstance(
                result,
                dict
            ):

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

    print(
        "\n"
        + "=" * 60
    )

    print(
        "ГОТОВО"
    )

    print(
        "=" * 60
    )


# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":
    main()
