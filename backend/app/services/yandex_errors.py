class YandexServiceError(Exception):
    """Ошибка вызова Yandex Search или YandexGPT при включённой конфигурации."""

    def __init__(self, service: str, message: str, status_code: int | None = None):
        self.service = service
        self.status_code = status_code
        super().__init__(message)
