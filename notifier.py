import datetime
import os
import shutil
import time

import psycopg2
from psycopg2.extras import DictCursor
import telegram
import git

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

class RepoParams:
    def __init__(self, last_checkout, url, login='', password='', owner=''):
        self.owner = owner
        self.last_checkout = last_checkout
        self.login = login
        self.password = password
        if login:
            self.remote_url = f'https://{login}:{password}@{url.replace("https://", "")}'
        else:
            self.remote_url = f'https://{url.replace("https://", "")}'
        self.name = self.remote_url[self.remote_url.rfind('/') + 1: self.remote_url.rfind('.git')]

    @classmethod
    def from_dict(cls, data):
        owner = data['owner']
        url = data['url']
        login = data['login']
        password = data['pass']
        last_checkout = data['last_checkout']
        return cls(last_checkout, url, login, password, owner)


class Repo:
    def __init__(self, params):
        self.params = params
        # TODO Проверить формирование адреса при отсутствии логина/пароля
        # TODO Приводить поля к нужному формату перед их добавлением в базу
        # репу будем клонировать в папку со скриптом
        self.local_path = os.getcwd() + '/temp/' + self.params.name
        self._repo = None
        self.origin = None
        self.branches = None

    def clone(self):
        self.clear_local_dir()
        while True:
            try:
                self._repo = git.Repo.clone_from(self.params.remote_url, self.local_path,
                                                 multi_options=['--no-checkout'])
            except git.exc.GitError as exception:
                print(exception)
                # TODO Оповещать кого-нибудь о косячной репе

                # TODO Избавиться от бесконечных попыток получить репу
                time.sleep(2)
            else:
               break

        self.origin = self._repo.remotes.origin
        self.branches = [branch.name for branch in self.origin.refs if branch.name != 'origin/HEAD']

    def clear_local_dir(self):
        if os.path.exists(self.local_path):
            shutil.rmtree(self.local_path)

    def last_commits(self):
        last_raw_commits = {}
        for branch_name in self.branches:
            # TODO Проверить, будет ли работать без приведения к листу
            last_raw_commits[branch_name] = list(self._repo.iter_commits(branch_name, max_count=50))

        for branch, raw_commits_list in last_raw_commits.items():
            for raw_commit in raw_commits_list:
                if raw_commit.committed_date > self.params.last_checkout.timestamp():  # Фильтруем коммиты по таймстампу
                    commit = dict()
                    # Чистим сообщение от переносов строк, удаляем завершающие пробелы.
                    # TODO Экранировать подчёркивания и звёздочки нужно будет перед форматированием
                    commit['branch'] = branch
                    commit['message'] = raw_commit.message.replace('\n', ' ').replace('_', '\_').replace('*', '\*').rstrip()
                    # commit['message'] = raw_commit.message
                    commit['committer'] = str(raw_commit.committer)
                    # Таймстамп коммита сразу преобразуем в datetime
                    commit['timestamp'] = datetime.datetime.fromtimestamp(raw_commit.committed_date)
                    yield commit

    def __del__(self):
        self.clear_local_dir()


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


class Database:
    def __init__(self, params):
        self.params = params

    def get_repos(self):
        with psycopg2.connect(dbname=self.params.name, user=self.params.login,
                              password=self.params.password, host=self.params.host) as conn:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute('SELECT url, login, pass, last_checkout, users.telegram_id as owner '
                               'FROM temp JOIN users ON users.id = temp.user_id '
                               'ORDER BY user_id')
                repos = cursor.fetchall()
        for repo in repos:
            yield Repo(RepoParams.from_dict(repo))

    def get_telegram_id(self, user_id):
        with psycopg2.connect(dbname=self.params.name, user=self.params.login,
                              password=self.params.password, host=self.params.host) as conn:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute('SELECT telegram_id FROM users WHERE id = %s', str(user_id))
                response = cursor.fetchone()
        return response['telegram_id'] if response else None


class DBParams:
    def __init__(self, host, name, login, password):
        self.host = host
        self.name = name
        self.login = login
        self.password = password

    @classmethod
    def from_dict(cls, data):
        host = data['DB_HOST']
        name = data['DB_NAME']
        login = data['DB_USER']
        password = data['DB_PASS']
        return cls(host, name, login, password)

if __name__ == '__main__':

    database = Database(DBParams.from_dict(os.environ))
    for repo in database.get_repos():
        repo.clone()
        for commit in repo.last_commits():
            print(commit['message'])


    # print(locals())
    # Инициализируем бота
    # bot = telegram.Bot(token=TLG_TOKEN, request=TLG_REQUEST if TLG_PROXIFY else None)
    # while True:
    #
    #     for record in cursor:
    #         # some actions for getting repo and commits
    #         # some actions for sending messages
    #         print(dict(record))
    #
    #     time.sleep(60)



        #
        # conn = psycopg2.connect(dbname=db_name, user=db_user,
        #                         password=db_pass, host=db_host)
        # cursor = conn.cursor(cursor_factory=DictCursor)
        # cursor.execute(
        #     "SELECT users.telegram_id AS telegram_id, temp.* FROM temp JOIN users ON users.id = temp.user_id WHERE telegram_id='118750337' LIMIT 10")


    # try_send_message(bot, chat_id=TLG_CHAT_ID, text='Bot connected')
#
# # Текущее время чтобы пинать в чат коммиты, появившиеся после запуска скрипта
# last_timestamp = datetime.datetime.now()
#
# while True:
#     clear_repo_dir(LOCAL_REPO_PATH)     # На всякий случай проверяем и сносим директорию репы
#     repo = try_repo_clone(HTTPS_REMOTE_URL, LOCAL_REPO_PATH)
#     origin = repo.remotes.origin
#
#     # Получаем 50 последних коммитов из каждой ветки
#     repo_branches_names = [branch.name for branch in repo.remotes.origin.refs if branch.name != 'origin/HEAD']
#     last_raw_commits = {}
#     for branch_name in repo_branches_names:
#         last_raw_commits[branch_name] = list(repo.iter_commits(branch_name, max_count=50))
#
#     # Формируем свой список коммитов, с которым нам будет удобно работать
#     last_commits = []
#     for branch, raw_commits_list in last_raw_commits.items():
#         for raw_commit in raw_commits_list:
#             if raw_commit.committed_date > last_timestamp.timestamp():  # Фильтруем коммиты по таймстампу
#                 commit = dict()
#                 # Чистим сообщение от переносов строк, удаляем завершающие пробелы и экранируем подчёркивания и звёздочки
#                 commit['branch'] = branch
#                 commit['message'] = raw_commit.message.replace('\n', ' ').replace('_', '\_').replace('*', '\*').rstrip()
#                 commit['committer'] = str(raw_commit.committer)
#                 # Таймстамп коммита сразу преобразуем в datetime
#                 commit['timestamp'] = datetime.datetime.fromtimestamp(raw_commit.committed_date)
#                 last_commits.append(commit)
#
#     if last_commits:
#         print(f'{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")} '
#               f'[i] Git: We have {len(last_commits)} new commits')
#         # отсортируем коммиты не по ветке, а по таймстампу, чтобы получился хронологический лог
#         last_commits.sort(key=lambda commit: commit['timestamp'])
#         for commit in last_commits:
#             # Формируем пост для телеги
#             telegram_message = (f'`{commit["branch"]}`   *{commit["committer"]}*\n'
#                                 f'_{commit["timestamp"].strftime("%H:%M:%S %d/%m/%Y")}_\n\n'
#                                 f'{commit["message"]}'
#                                 )
#
#             # Отправляем пост в телеграм
#             bot.sendMessage(chat_id=TLG_CHAT_ID, text=telegram_message, parse_mode='Markdown')
#
#             # обновляем контрольный таймстамп временем последнего коммита
#             last_timestamp = commit['timestamp']
#     else:
#         print(f'{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")} [i] Git: No new commits')
#
#     clear_repo_dir(LOCAL_REPO_PATH)     # подчищаем за собой диск
#     time.sleep(60)
