# telegram-commit-notifier

Бот мониторит репозиторий на наличие новых коммитов (для ускорения работы тянутся только метаданные репозитория) и отправляет метаданные новых коммитов в Телеграм. Бот задеплоен на Heroku больше полутора лет назад и продолжает работать до сих пор.

![git_notifier](https://user-images.githubusercontent.com/11722336/178275040-144ebeca-bcd7-4c78-8072-3435a0c576e0.png)


Сконфигурирован для деплоя на Heroku.

В переменных окружения следует прописать ряд значений:
```
REPO_URL - ссылка на репозиторий
GIT_USERNAME - имя пользователя
GIT_PASSWORD - пароль
TLG_TOKEN - токен телеграм-бота. Получить можно у @botfather
TLG_CHAT_ID - Chat ID получателя. Получаем по ссылке https://api.telegram.org/bot<ВАШ_ТОКЕН>/getUpdates
```
