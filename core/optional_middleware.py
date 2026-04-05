try:
    from whitenoise.middleware import WhiteNoiseMiddleware as _WhiteNoiseMiddleware
except ModuleNotFoundError:
    _WhiteNoiseMiddleware = None


class WhiteNoiseMiddleware:
    """
    Wrapper opcional para WhiteNoise.

    - En producción (si `whitenoise` está instalado), delega al middleware real.
    - En entornos mínimos (tests/CI) donde `whitenoise` no esté instalado,
      actúa como no-op para no romper el arranque.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self._delegate = _WhiteNoiseMiddleware(get_response) if _WhiteNoiseMiddleware else None

    def __call__(self, request):
        if self._delegate is not None:
            return self._delegate(request)
        return self.get_response(request)

