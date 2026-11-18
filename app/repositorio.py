import hashlib
import json
import sqlite3
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from filelock import FileLock
from pydantic import BaseModel, ValidationError

from app.configuracion import ConfigCompania
from app.errores import ErrorServicio
from app.identidad import clave_solicitud, contenido_solicitud, normalizar_compania
from app.schemas import AnalisisSolicitud, ResultadoSolicitud, SolicitudEntrada


@contextmanager
def conexion_sqlite(ruta: Path):
    try:
        with closing(sqlite3.connect(ruta, timeout=5.0)) as conexion, conexion:
            yield conexion
    except sqlite3.Error as exc:
        raise ErrorServicio(
            "PERSISTENCIA_NO_DISPONIBLE", "No fue posible acceder al registro de solicitudes.", 503
        ) from exc


@dataclass
class RegistroSolicitud:
    compania: ConfigCompania
    analisis: AnalisisSolicitud | None
    decision: ResultadoSolicitud | None
    resultado: ResultadoSolicitud | None


class RepositorioSolicitudes:
    def __init__(self, directorio: Path):
        directorio.mkdir(parents=True, exist_ok=True)
        self.ruta = directorio / "bpo.sqlite3"
        self.bloqueos = directorio / "bloqueos"
        self.bloqueos.mkdir(exist_ok=True)
        with conexion_sqlite(self.ruta) as conexion:
            conexion.execute("""
                CREATE TABLE IF NOT EXISTS solicitudes (
                    compania TEXT NOT NULL,
                    solicitud_id TEXT NOT NULL,
                    huella TEXT NOT NULL,
                    entrada_json TEXT NOT NULL,
                    configuracion_json TEXT NOT NULL,
                    analisis_json TEXT,
                    decision_json TEXT,
                    resultado_json TEXT,
                    ultimo_error TEXT,
                    PRIMARY KEY (compania, solicitud_id)
                )
            """)

    def bloquear(self, solicitud: SolicitudEntrada) -> FileLock:
        return FileLock(str(self.bloqueos / f"{clave_solicitud(solicitud)}.lock"), timeout=0)

    def obtener_o_crear(
        self, solicitud: SolicitudEntrada, compania: ConfigCompania
    ) -> RegistroSolicitud:
        contenido = contenido_solicitud(solicitud)
        entrada = json.dumps(contenido, sort_keys=True, ensure_ascii=False)
        huella = hashlib.sha256(entrada.encode("utf-8")).hexdigest()
        identidad = (contenido["compania"], solicitud.solicitud_id)
        with conexion_sqlite(self.ruta) as conexion:
            conexion.execute(
                """INSERT INTO solicitudes
                   (compania, solicitud_id, huella, entrada_json, configuracion_json)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(compania, solicitud_id) DO NOTHING""",
                (*identidad, huella, entrada, compania.model_dump_json()),
            )
            fila = conexion.execute(
                """SELECT huella, configuracion_json, analisis_json, decision_json, resultado_json
                   FROM solicitudes WHERE compania = ? AND solicitud_id = ?""",
                identidad,
            ).fetchone()
            if fila[0] != huella:
                raise ErrorServicio(
                    "SOLICITUD_ID_REUTILIZADO",
                    "El identificador ya fue usado con otro contenido.",
                    409,
                )
        try:
            return RegistroSolicitud(
                compania=ConfigCompania.model_validate_json(fila[1]),
                analisis=AnalisisSolicitud.model_validate_json(fila[2]) if fila[2] else None,
                decision=ResultadoSolicitud.model_validate_json(fila[3]) if fila[3] else None,
                resultado=ResultadoSolicitud.model_validate_json(fila[4]) if fila[4] else None,
            )
        except ValidationError as exc:
            raise ErrorServicio(
                "REGISTRO_INVALIDO", "El registro guardado no cumple el contrato.", 503
            ) from exc

    def guardar_etapa(
        self,
        solicitud: SolicitudEntrada,
        etapa: Literal["analisis", "decision", "resultado"],
        datos: BaseModel,
    ) -> None:
        columnas = {
            "analisis": "analisis_json",
            "decision": "decision_json",
            "resultado": "resultado_json",
        }
        columna = columnas[etapa]
        # El identificador SQL sale del mapa interno; todos los valores se parametrizan.
        with conexion_sqlite(self.ruta) as conexion:
            conexion.execute(
                f"""UPDATE solicitudes
                    SET {columna} = COALESCE({columna}, ?), ultimo_error = NULL
                    WHERE compania = ? AND solicitud_id = ?""",
                (
                    datos.model_dump_json(),
                    normalizar_compania(solicitud.compania),
                    solicitud.solicitud_id,
                ),
            )

    def registrar_error(self, solicitud: SolicitudEntrada, codigo: str) -> None:
        with conexion_sqlite(self.ruta) as conexion:
            conexion.execute(
                """UPDATE solicitudes SET ultimo_error = ?
                   WHERE compania = ? AND solicitud_id = ?""",
                (codigo, normalizar_compania(solicitud.compania), solicitud.solicitud_id),
            )
