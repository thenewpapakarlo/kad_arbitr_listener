from datetime import datetime, timezone
from os import path
from telethon.sync import TelegramClient
from telethon import events
from time import sleep

import asyncio
import configparser
import glob
import logging
# import os
import re

# Считываем учетные данные
config = configparser.ConfigParser()
config.read('config.ini')

# Присваиваем значения внутренним переменным
api_id = int(config['Telegram']['api_id'])
api_hash = config['Telegram']['api_hash']
username = config['Telegram']['username']
messages_path = config['Telegram']['messages_path']
inns_path = config['Telegram']['inns_path']
SOURCE_CHANNEL = config['Telegram']['SOURCE_CHANNEL']

client = TelegramClient(username, api_id, api_hash)


def utc_to_local(utc_dt):
    return utc_dt.replace(tzinfo=timezone.utc).astimezone(tz=None)


# Обработчик новых сообщений
@client.on(events.NewMessage)
async def handler_new_message(event):
    # event.message содержит информацию о новом сообщении
    if event.message.sender_id == 615917143:
        message_text = str(event.message.text)
        print(event.message)
        if not event.message.out:
            logger.info('Message received')
            message_time = utc_to_local(event.message.date).strftime('%Y-%m-%d_%H-%M-%S')
            if message_text.find('Подписка на участника') == 0:
                # Пришёл ответ на попытку подписать новый ИНН. Участник либо подписан, либо уже был.
                # В любом случае добавляем ИНН в список подписанных
                with open('subscribed_inns.csv', 'a', encoding='utf8') as subscribed_inns_file:
                    inn = message_text.split(' ')[3]
                    subscribed_inns_file.writelines(inn + '\n')
                    logger.info(f'New INN <{inn}> successfully subscribed')
            elif message_text.find('Подписка') == 0 and \
                    (message_text.find('добавлена.') > -1 or message_text.find('уже существует') > -1):
                # Пришёл ответ на попытку подписаться на новое дело. Подписка либо добавляется, либо уже была.
                # В любом случае добавляем номер дела в список подписанных, предварительно проверив,
                # что номера дела нет в списке подписанных
                if message_text.find('Подписка на дело') == 0:
                    case = message_text.split(' ')[3] + '\n'
                else:
                    case = message_text.split(' ')[6] + '\n'
                subscribed_cases = await get_items_set('subscribed_cases.csv')
                if case not in subscribed_cases:
                    with open('subscribed_cases.csv', 'a', encoding='utf8') as subscribed_list_file:
                        subscribed_list_file.writelines(case)
                        logger.debug(f'Case <{case.strip()}> added to subscribed list')

            message_parts = message_text.split('\n')
            first_message = True
            text_to_write = ''
            for message_part in message_parts:
                result = re.match(r'[А-Я,0-9]+-[А-Я,0-9/]+[-]?[[А-Я,0-9]*]?', message_part)
                if result is not None:
                    year = message_part.split('/')[-1]
                    if len(year) == 2:
                        if year == '20':
                            year = '/2020\n'
                        else:
                            year = '/2021\n'
                        case = message_part.split('/')[0] + year
                    else:
                        case = message_part + '\n'
                    subscribed_cases = await get_items_set('subscribed_cases.csv')
                    if case not in subscribed_cases:
                        logger.info(f'Subscribing for new case <{case.strip()}>')
                        await client.send_message(SOURCE_CHANNEL, '/follow ' + case)
                    if not first_message:
                        write_message(text_to_write, message_time)
                    first_message = False
                    text_to_write = ''
                text_to_write += message_part + '\n'
            write_message(text_to_write, message_time)
            logger.debug('Done!')

    print('Waiting for new message...')
    logger.debug('Waiting for new message...')


def write_message(message_text, time_):
    count = len(glob.glob(path.join(messages_path, time_) + '_?.msg'))
    print(f'Writing message #{count}')
    logger.debug(f'Writing message #{count}')
    with open(path.join(messages_path, f'{time_}_{count}.msg'), 'w', encoding='utf8') as message:
        message.write(time_ + '\n' + message_text)


async def subscribe():
    await subscribe_inns()

    print('Subscribing for cases...')
    logger.debug('Subscribing for cases in <cases_list.csv>...')
    if not path.exists('subscribed_cases.csv'):
        with open('subscribed_cases.csv', 'x', encoding='utf8'):
            pass
    cases = await get_items_set(path.join(inns_path, 'cases_list.csv'))
    subscribed = await get_items_set('subscribed_cases.csv')
    to_subscribe = cases - subscribed
    for case in to_subscribe:
        logger.info(f'Subscribing for case <{case.strip()}>')
        await client.send_message(SOURCE_CHANNEL, '/follow ' + case)
        sleep(5)
    print('Waiting for new message...')
    logger.debug('Waiting for new message...')


async def get_items_set(filename):
    with open(filename, 'r', encoding='utf8') as list_file:
        items_list = list_file.readlines()
    return set(items_list)


async def subscribe_inns():
    print('Subscribing for new INNs...')
    logger.debug('Subscribing for new INNs...')
    if not path.exists('subscribed_inns.csv'):
        with open('subscribed_inns.csv', 'x', encoding='utf8'):
            pass
    inns = await get_items_set(path.join(inns_path, 'INN.csv'))
    subscribed = await get_items_set('subscribed_inns.csv')
    to_subscribe = inns - subscribed
    if len(subscribed) == 0:
        logger.info('Starting telegram bot...')
        await client.send_message(SOURCE_CHANNEL, '/start')
    for inn in to_subscribe:
        logger.info(f'Subscribing new INN <{inn.strip()}>...')
        await client.send_message(SOURCE_CHANNEL, '/follow ' + inn)
        sleep(1)


async def schedule_subscribe_inns():
    while True:
        ct = datetime.now()
        if ct.hour == 0 and ct.minute == 45 and ct.second == 0:
            await subscribe()
            # await subscribe_inns()
        await asyncio.sleep(1)


if __name__ == '__main__':
    logger = logging.getLogger('MainLogger')
    logger.setLevel(logging.DEBUG)
    handler = logging.FileHandler(filename='kadadrbitr_bot.log', encoding='utf8')
    logger.addHandler(handler)
    formatter = logging.Formatter(fmt='{asctime} [{levelname}]: {message}', style='{')
    handler.setFormatter(formatter)

    logger.debug('Starting...')
    client.start()

    client.loop.create_task(subscribe())
    client.loop.create_task(schedule_subscribe_inns())
    client.loop.run_forever()

    client.run_until_disconnected()
