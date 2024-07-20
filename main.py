import aiohttp
import xml.etree.ElementTree as ET
import redis
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

API_TOKEN = 'TOKEN'
REDIS_HOST = 'localhost'
REDIS_PORT = 6379

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# Подключение к Redis
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)


# Получение курсов валют с сайта ЦБ РФ
async def fetch_exchange_rates():
    url = 'https://www.cbr.ru/scripts/XML_daily.asp'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                xml_data = await response.text()
                return xml_data
            else:
                print(f"Не удалось получить данные с сайта: {response.status}")
                return None


# Получение курсов валют
def parse_exchange_rates(xml_data):
    root = ET.fromstring(xml_data)
    exchange_rates = {}
    for valute in root.findall('Valute'):
        char_code = valute.find('CharCode').text
        value = valute.find('Value').text.replace(',', '.')
        exchange_rates[char_code] = float(value)

    # Извлечение даты из атрибута корневого элемента
    date = root.attrib.get('Date', None)
    if not date:
        print("Date не найден в XML-файле.")
        raise ValueError("Date не найден в XML-файле.")

    return exchange_rates, date


# Обновление курсов валют в Redis
async def update_redis():
    xml_data = await fetch_exchange_rates()
    if xml_data:
        try:
            exchange_rates, date = parse_exchange_rates(xml_data)
            for char_code, value in exchange_rates.items():
                r.set(char_code, value)
            r.set('LAST_UPDATE', date)
            print(f"Обновленные курсы обмена валют на дату: {date}")
        except Exception as e:
            print(f"Ошибка парсинга XML: {e}")
    else:
        print("Не удалось получить данные о курсах обмена валют")


# Обработчик команды /exchange
@dp.message_handler(commands=['exchange'])
async def exchange(message: types.Message):
    try:
        # Разделение команды на составляющие
        _, from_currency, to_currency, amount = message.text.split()
        amount = float(amount)
        # Конвертация валюты с учетом курса рубля
        if from_currency == 'RUB':
            to_rate = float(r.get(to_currency))
            result = amount / to_rate
        elif to_currency == 'RUB':
            from_rate = float(r.get(from_currency))
            result = amount * from_rate
        else:
            from_rate = float(r.get(from_currency))
            to_rate = float(r.get(to_currency))
            result = (amount * from_rate) / to_rate
        await message.reply(f"{amount} {from_currency} = {result:.5f} {to_currency}")
    except Exception as e:
        await message.reply("Ошибка при выполнении обмена. Проверьте правильность команды.")
        print(f"Ошибка обмена: {e}")

# Обработчик команды /rates
@dp.message_handler(commands=['rates'])
async def rates(message: types.Message):
    try:
        keys = r.keys()
        rates = {key.decode(): r.get(key).decode() for key in keys if key.decode() != 'LAST_UPDATE'}
        rates_str = "\n".join([f"{key}: {value}" for key, value in rates.items()])
        last_update = r.get('LAST_UPDATE').decode()
        await message.reply(f"Курсы валют на {last_update}:\n{rates_str}")
    except Exception as e:
        await message.reply("Ошибка при получении курсов валют.")
        print(f"Ошибка в курсах: {e}")

# Запуск бота
if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(update_redis())
    executor.start_polling(dp, skip_updates=True)

