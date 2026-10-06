def is_api_request(request):
    """
    Determina de forma robusta si una solicitud HTTP entrante espera una respuesta en formato JSON (API)
    basado en las cabeceras HTTP y en los prefijos de las rutas de URL del sistema.
    """
    return (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
        request.headers.get('Content-Type') == 'application/json' or
        request.path.startswith('/api/') or
        request.path.startswith('/sales/api/')
    )
