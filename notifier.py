import datetime
import os
import shutil
import time

import telegram
from git import Repo, exc

# Подтягиваем чувствительные данные из переменных окружения
# ------------ GIT ------------
assert 'REPO_URL' in os.environ, 'Environment variable REPO_URL is not exist'
assert 'GIT_USERNAME' in os.environ, 'Environment variable GIT_USERNAME is not exist'
assert 'GIT_PASSWORD' in os.environ, 'Environment variable GIT_PASSWORD is not exist'
# Ссылка на репозиторий
REPO_URL = os.environ.get('REPO_URL')
# Имя пользователя, которое с @ в начале (не логин!)
GIT_USERNAME = os.environ.get('GIT_USERNAME')
# Пароль от учётки, либо personal access token (в гитлабе получаем в Settings -> Access Tokens
GIT_PASSWORD = os.environ.get('GIT_PASSWORD')

# собираем ссылку для работы с репозиторием
HTTPS_REMOTE_URL = f'https://{GIT_USERNAME}:{GIT_PASSWORD}@{REPO_URL.replace("https://", "")}'
# репу будем клонировать в папку со скриптом
DEST_NAME = HTTPS_REMOTE_URL[HTTPS_REMOTE_URL.rfind('/') + 1: HTTPS_REMOTE_URL.rfind('.git')]
LOCAL_REPO_PATH = os.getcwd() + '/' + DEST_NAME

# ------------ Telegram ------------
assert 'TLG_TOKEN' in os.environ, 'Environment variable TLG_TOKEN is not exist'
assert 'TLG_CHAT_ID' in os.environ, 'Environment variable TLG_CHAT_ID is not exist'
# Токен бота телеграма. Получаем у @botfather
TLG_TOKEN = os.environ.get('TLG_TOKEN')
# Chat ID получателя. Получаем по ссылке https://api.telegram.org/bot<ВАШ_ТОКЕН>/getUpdates
TLG_CHAT_ID = os.environ.get('TLG_CHAT_ID')
# Флаг работы через прокси. Если телега будет работать через прокси, то устанавливаем True
TLG_PROXIFY = False
TLG_PROXY = '54.38.81.12:54796'
# Данные для прокси, через которую будет работать телега. Брал отсюда: https://50na50.net/ru/proxy/socks5list
TLG_REQUEST = telegram.utils.request.Request(
    proxy_url='socks5://' + TLG_PROXY,
    # Раскомментить если нужна аутентификация на прокси:
    # urllib3_proxy_kwargs= {
    #     'username': 'PROXY_USER',
    #     'password': 'PROXY_PASSWORD',
    # }
)


def try_repo_clone(repo_url, repo_local_path):
    attempts_counter = 0  # Счётчик попыток подключения
    # Пытаемся достучаться до хоста, отлавливая исключения
    while True:
        attempts_counter += 1
        try:
            repo = Repo.clone_from(repo_url, repo_local_path, multi_options=['--no-checkout'])

        except exc.GitError as exception:
            print(
                f'{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")} [!] Git: Clone raised '
                f'exception {type(exception).__name__}. Retrying. Attempt {attempts_counter}')
            time.sleep(2)

        # При успешной попытке возвращаем ответ
        else:
            print(f'{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")} [i] Git: Repo cloned')
            return repo


def try_send_message(tlg_bot, chat_id, text):
    attempts_counter = 0  # Счётчик попыток подключения
    while True:
        attempts_counter += 1
        try:
            tlg_bot.sendMessage(chat_id=chat_id, text=text, parse_mode='Markdown')

        except telegram.error.NetworkError as exception:
            print(
                f'{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")} '
                f'[!] Telegram: Network error. Attempt {attempts_counter}'
            )
            time.sleep(2)

        # При успешной попытке возвращаем ответ
        else:
            print(f'{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")} '
                  f'[i] Telegram: Message sent')
            break


def clear_repo_dir(path):
    if os.path.exists(path):
        shutil.rmtree(path)


# Инициализируем бота
bot = telegram.Bot(token=TLG_TOKEN, request=TLG_REQUEST if TLG_PROXIFY else None)

try_send_message(bot, chat_id=TLG_CHAT_ID, text='Bot connected')

# Текущее время чтобы пинать в чат коммиты, появившиеся после запуска скрипта
last_timestamp = datetime.datetime.now()

while True:
    clear_repo_dir(LOCAL_REPO_PATH)     # На всякий случай проверяем и сносим директорию репы
    repo = try_repo_clone(HTTPS_REMOTE_URL, LOCAL_REPO_PATH)
    origin = repo.remotes.origin

    # Получаем 50 последних коммитов из каждой ветки
    repo_branches_names = [branch.name for branch in repo.remotes.origin.refs if branch.name != 'origin/HEAD']
    last_raw_commits = {}
    for branch_name in repo_branches_names:
        last_raw_commits[branch_name] = list(repo.iter_commits(branch_name, max_count=50))

    # Формируем свой список коммитов, с которым нам будет удобно работать
    last_commits = []
    for branch, raw_commits_list in last_raw_commits.items():
        for raw_commit in raw_commits_list:
            if raw_commit.committed_date > last_timestamp.timestamp():  # Фильтруем коммиты по таймстампу
                commit = dict()
                # Чистим сообщение от переносов строк, удаляем завершающие пробелы и экранируем подчёркивания и звёздочки
                commit['branch'] = branch
                commit['message'] = raw_commit.message.replace('\n', ' ').replace('_', '\_').replace('*', '\*').rstrip()
                commit['committer'] = str(raw_commit.committer)
                # Таймстамп коммита сразу преобразуем в datetime
                commit['timestamp'] = datetime.datetime.fromtimestamp(raw_commit.committed_date)
                last_commits.append(commit)

    if last_commits:
        print(f'{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")} '
              f'[i] Git: We have {len(last_commits)} new commits')
        # отсортируем коммиты не по ветке, а по таймстампу, чтобы получился хронологический лог
        last_commits.sort(key=lambda commit: commit['timestamp'])
        for commit in last_commits:
            # Формируем пост для телеги
            telegram_message = (f'`{commit["branch"]}`   *{commit["committer"]}*\n'
                                f'_{commit["timestamp"].strftime("%H:%M:%S %d/%m/%Y")}_\n\n'
                                f'{commit["message"]}'
                                )

            # Отправляем пост в телеграм
            bot.sendMessage(chat_id=TLG_CHAT_ID, text=telegram_message, parse_mode='Markdown')

            # обновляем контрольный таймстамп временем последнего коммита
            last_timestamp = commit['timestamp']
    else:
        print(f'{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")} [i] Git: No new commits')

    clear_repo_dir(LOCAL_REPO_PATH)     # подчищаем за собой диск
    time.sleep(60)
