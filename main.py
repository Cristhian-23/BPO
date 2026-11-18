import json
import logging
import os
from contextlib import ExitStack, asynccontextmanager
from typing import Annotated

import httpx
from fastapi import Body, FastAPI, Request

from app.analizador_groq import AnalizadorGroq
from app.configuracion import (
    RAIZ_PROYECTO,
    cargar_configuracion,
    cargar_entorno,
    directorio_datos,
    validar_integraciones,
)
from app.errores import ErrorServicio, respuesta_error
from app.plataforma import ADAPTADORES_PLATAFORMA
from app.prioridades import ESTRATEGIAS_PRIORIDAD
from app.repositorio import RepositorioSolicitudes
from app.schemas import ResultadoSolicitud, SolicitudEntrada
from app.servicio_solicitudes import ServicioSolicitudes


@asynccontextmanager
async def lifespan(api: FastAPI):
    cargar_entorno()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    configuracion = cargar_configuracion()
    validar_integraciones(
        configuracion, set(ESTRATEGIAS_PRIORIDAD), set(ADAPTADORES_PLATAFORMA)
    )
    with ExitStack() as recursos:
        cliente = httpx.Client(timeout=5.0)
        recursos.callback(cliente.close)
        analizador = AnalizadorGroq(
            api_key=os.getenv("GROQ_API_KEY"),
            modelo=os.getenv("GROQ_MODEL") or "openai/gpt-oss-20b",
        )
        recursos.callback(analizador.close)
        api.state.servicio = ServicioSolicitudes(
            configuracion,
            RepositorioSolicitudes(directorio_datos()),
            analizador.analizar,
            cliente,
        )
        yield


app = FastAPI(
    title="Servicio de procesamiento de solicitudes BPO",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_exception_handler(ErrorServicio, respuesta_error)
ejemplos = json.loads(
    (RAIZ_PROYECTO / "examples" / "solicitudes.json").read_text(encoding="utf-8")
)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/solicitudes", response_model=ResultadoSolicitud)
def recibir_solicitud(
    solicitud: Annotated[SolicitudEntrada, Body(openapi_examples=ejemplos)],
    request: Request,
) -> ResultadoSolicitud:
    return request.app.state.servicio.procesar(solicitud)
