import datetime
import os
import shutil
import time

import psycopg2
from psycopg2.extras import DictCursor
import telegram
import git

# ------------ Telegram ------------
assert 'TLG_TOKEN' in os.environ, 'Environment variable TLG_TOKEN is not exist'
# Токен бота телеграма. Получаем у @botfather
TLG_TOKEN = os.environ.get('TLG_TOKEN')
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
    def __init__(self, last_checkout, url, repo_id, login='', password='', owner_id=''):
        self.owner_id = owner_id
        self.last_checkout = last_checkout
        self.login = login
        self.password = password
        self.id = repo_id
        if login:
            self.remote_url = f'https://{login}:{password}@{url.replace("https://", "")}'
        else:
            self.remote_url = f'https://{url.replace("https://", "")}'
        self.name = self.remote_url[self.remote_url.rfind('/') + 1: self.remote_url.rfind('.git')]

    @classmethod
    def from_dict(cls, data):
        owner_id = data['owner_id']
        url = data['url']
        login = data['login']
        password = data['pass']
        last_checkout = data['last_checkout']
        repo_id = data['id']
        return cls(last_checkout, url, repo_id, login, password, owner_id)


class Repo:
    def __init__(self, params):
        self.params = params
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

    @property
    def last_commits(self):
        self.clone()
        last_raw_commits = {}
        for branch_name in self.branches:
            last_raw_commits[branch_name] = list(self._repo.iter_commits(branch_name, max_count=50))

        for branch, raw_commits_list in last_raw_commits.items():
            for raw_commit in raw_commits_list[::-1]:
                if raw_commit.committed_date > self.params.last_checkout.timestamp():  # Фильтруем коммиты по таймстампу
                    commit = dict()
                    # Чистим сообщение от переносов строк, удаляем завершающие пробелы.
                    # TODO Экранировать подчёркивания и звёздочки нужно будет перед форматированием
                    commit['repo'] = self.params.name
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
                cursor.execute('SELECT id, url, login, pass, last_checkout, user_id as owner_id '
                               'FROM repos ORDER BY user_id')
                repos = cursor.fetchall()
        for repo in repos:
            yield Repo(RepoParams.from_dict(repo))

    def get_telegram_id(self, user_id):
        with psycopg2.connect(dbname=self.params.name, user=self.params.login,
                              password=self.params.password, host=self.params.host) as conn:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute('SELECT telegram_id FROM users WHERE id = %s', (str(user_id), ))
                return cursor.fetchone()[0]

    def get_user_timezone(self, user_id):
        with psycopg2.connect(dbname=self.params.name, user=self.params.login,
                              password=self.params.password, host=self.params.host) as conn:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute('SELECT timezone FROM users WHERE id = %s', (str(user_id), ))
                return cursor.fetchone()[0]

    def update_checkout_time(self, repo):
        with psycopg2.connect(dbname=self.params.name, user=self.params.login,
                              password=self.params.password, host=self.params.host) as conn:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute('UPDATE repos SET last_checkout = %s WHERE id = %s',
                               (datetime.datetime.now(), repo.params.id))


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

    bot = telegram.Bot(token=TLG_TOKEN, request=TLG_REQUEST if TLG_PROXIFY else None)
    database = Database(DBParams.from_dict(os.environ))
    for repo in database.get_repos():
        telegram_id = database.get_telegram_id(repo.params.owner_id)
        for commit in repo.last_commits:
            # Формируем пост для телеги
            telegram_message = (f'*{commit["repo"]}*\n'
                                f'`{commit["branch"]}`   *{commit["committer"]}*\n'
                                f'_{commit["timestamp"].strftime("%H:%M:%S %d/%m/%Y")}_\n\n'
                                f'{commit["message"]}'
                                )
            try_send_message(bot, chat_id=telegram_id, text=telegram_message)
        database.update_checkout_time(repo)
