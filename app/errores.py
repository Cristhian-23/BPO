class ErrorServicio(Exception):
    """Error controlado con un código público y un mensaje sin datos sensibles."""

    def __init__(
        self,
        codigo: str,
        mensaje: str,
        estado_http: int,
        reintentar_en: int | None = None,
    ):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje
        self.estado_http = estado_http
        self.reintentar_en = reintentar_en


def respuesta_error(_request, exc: ErrorServicio):
    from starlette.responses import JSONResponse

    headers = {"Retry-After": str(exc.reintentar_en)} if exc.reintentar_en is not None else None
    return JSONResponse(
        status_code=exc.estado_http,
        content={"detail": {"codigo": exc.codigo, "mensaje": exc.mensaje}},
        headers=headers,
    )
