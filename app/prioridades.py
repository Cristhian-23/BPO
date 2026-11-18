from collections.abc import Callable
from dataclasses import dataclass

import httpx
from pydantic import ValidationError

from app.configuracion import ConfigCategoria, ConfigCompania, resolver_url
from app.errores import ErrorServicio
from app.schemas import AnalisisSolicitud, CampoMinimo, DecisionPrioridad


def prioridad_por_categoria(
    _compania: ConfigCompania,
    categoria: ConfigCategoria,
    _analisis: AnalisisSolicitud,
    _cliente: httpx.Client,
) -> DecisionPrioridad:
    return DecisionPrioridad(
        prioridad=categoria.prioridad_base,
        justificacion="Prioridad definida por las reglas de la categoría.",
    )


def prioridad_por_servicio(
    compania: ConfigCompania,
    _categoria: ConfigCategoria,
    analisis: AnalisisSolicitud,
    cliente: httpx.Client,
) -> DecisionPrioridad:
    try:
        respuesta = cliente.post(
            resolver_url(compania.prioridad_url_env),
            json={
                "tipo_documento": analisis.tipo_documento,
                "numero_documento_cliente": analisis.numero_documento_cliente,
                "tipo_solicitud": analisis.categoria,
            },
        )
        respuesta.raise_for_status()
    except httpx.TimeoutException as exc:
        raise ErrorServicio(
            "PRIORIDAD_EXTERNA_TIEMPO_AGOTADO",
            "El servicio de prioridad no respondió a tiempo.",
            504,
        ) from exc
    except (httpx.HTTPError, httpx.InvalidURL) as exc:
        raise ErrorServicio(
            "PRIORIDAD_EXTERNA_NO_DISPONIBLE",
            "No fue posible consultar el servicio de prioridad.",
            503,
        ) from exc
    try:
        return DecisionPrioridad.model_validate_json(respuesta.text)
    except ValidationError as exc:
        raise ErrorServicio(
            "RESPUESTA_PRIORIDAD_EXTERNA_INVALIDA",
            "El servicio de prioridad devolvió una respuesta inválida.",
            502,
        ) from exc


@dataclass(frozen=True)
class EstrategiaPrioridad:
    calcular: Callable[
        [ConfigCompania, ConfigCategoria, AnalisisSolicitud, httpx.Client],
        DecisionPrioridad,
    ]
    campos_minimos: tuple[CampoMinimo, ...] = ()


ESTRATEGIAS_PRIORIDAD = {
    "reglas": EstrategiaPrioridad(prioridad_por_categoria),
    "servicio_externo": EstrategiaPrioridad(
        prioridad_por_servicio, ("tipo_documento", "numero_documento_cliente")
    ),
}


def requisitos_prioridad(compania: ConfigCompania) -> tuple[CampoMinimo, ...]:
    return ESTRATEGIAS_PRIORIDAD[compania.estrategia_prioridad].campos_minimos


def calcular_prioridad(
    compania: ConfigCompania,
    categoria: ConfigCategoria,
    analisis: AnalisisSolicitud,
    cliente: httpx.Client,
) -> DecisionPrioridad:
    estrategia = ESTRATEGIAS_PRIORIDAD[compania.estrategia_prioridad]
    return estrategia.calcular(compania, categoria, analisis, cliente)
