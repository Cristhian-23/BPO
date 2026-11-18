import hashlib
import json
from pathlib import Path
from uuid import uuid4

from app.configuracion import ConfigCompania
from app.errores import ErrorServicio
from app.identidad import clave_solicitud, contenido_solicitud
from app.repositorio import conexion_sqlite
from app.schemas import CasoExterno, ResultadoSolicitud, SolicitudEntrada


def crear_caso_simulado(
    solicitud: SolicitudEntrada,
    decision: ResultadoSolicitud,
    directorio: Path,
) -> CasoExterno:
    contenido = json.dumps(
        {
            **contenido_solicitud(solicitud),
            "solicitud_tipo": decision.solicitud_tipo,
            "solicitud_prioridad": decision.solicitud_prioridad,
            "justificacion": decision.justificacion,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    huella = hashlib.sha256(contenido.encode("utf-8")).hexdigest()
    clave = clave_solicitud(solicitud)
    with conexion_sqlite(directorio / "plataforma.sqlite3") as conexion:
        conexion.execute("""
            CREATE TABLE IF NOT EXISTS casos (
                clave TEXT PRIMARY KEY,
                huella TEXT NOT NULL,
                id_caso TEXT NOT NULL UNIQUE,
                contenido TEXT NOT NULL
            )
        """)
        conexion.execute(
            """INSERT INTO casos (clave, huella, id_caso, contenido)
               VALUES (?, ?, ?, ?) ON CONFLICT(clave) DO NOTHING""",
            (clave, huella, "EXT-" + uuid4().hex, contenido),
        )
        fila = conexion.execute(
            "SELECT huella, id_caso FROM casos WHERE clave = ?", (clave,)
        ).fetchone()
        if fila[0] != huella:
            raise ErrorServicio(
                "CONFLICTO_CASO_EXTERNO", "La clave ya fue usada con otro contenido.", 409
            )
    return CasoExterno(id_caso=fila[1], estado="pendiente")


ADAPTADORES_PLATAFORMA = {"simulada": crear_caso_simulado}


def crear_caso_externo(
    solicitud: SolicitudEntrada,
    compania: ConfigCompania,
    decision: ResultadoSolicitud,
    directorio: Path,
) -> CasoExterno:
    adaptador = ADAPTADORES_PLATAFORMA[compania.plataforma]
    return adaptador(solicitud, decision, directorio)
