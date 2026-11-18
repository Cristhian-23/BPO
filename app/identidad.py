import hashlib
import json

from app.schemas import SolicitudEntrada


def normalizar_compania(nombre: str) -> str:
    return " ".join(nombre.upper().split())


def contenido_solicitud(solicitud: SolicitudEntrada) -> dict:
    contenido = solicitud.model_dump()
    contenido["compania"] = normalizar_compania(solicitud.compania)
    return contenido


def clave_solicitud(solicitud: SolicitudEntrada) -> str:
    identidad = json.dumps(
        [normalizar_compania(solicitud.compania), solicitud.solicitud_id], ensure_ascii=False
    )
    return hashlib.sha256(identidad.encode("utf-8")).hexdigest()
