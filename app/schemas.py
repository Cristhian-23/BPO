from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Prioridad = Literal["Alta", "Media", "Baja"]
CampoMinimo = Literal[
    "que_paso", "cuando", "que_necesita", "tipo_documento", "numero_documento_cliente"
]
ProximoPaso = Literal["GESTION_EXTERNA", "RESPUESTA_DIRECTA", "CIERRE_POR_INFORMACION_INSUFICIENTE"]


class Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, strict=True)


class SolicitudEntrada(Modelo):
    compania: str = Field(min_length=1, max_length=120)
    solicitud_id: str = Field(min_length=1, max_length=100)
    solicitud_descripcion: str = Field(min_length=1, max_length=10000)


class AnalisisSolicitud(Modelo):
    categoria: str | None
    que_paso: str | None
    cuando: str | None = Field(
        description=(
            "Referencia temporal literal del relato. Puede ser relativa: hoy, ayer, "
            "esta mañana, hace dos semanas. Usa null solamente si no se menciona ninguna."
        )
    )
    que_necesita: str | None
    tipo_documento: str | None
    numero_documento_cliente: str | None


class DecisionPrioridad(Modelo):
    prioridad: Prioridad
    justificacion: str = Field(min_length=1)


class ResultadoSolicitud(Modelo):
    compania: str
    solicitud_id: str
    solicitud_fecha: datetime
    solicitud_tipo: str | None
    solicitud_prioridad: Prioridad | None
    tipo_documento: str | None
    numero_documento_cliente: str | None
    proximo_paso: ProximoPaso
    justificacion: str
    estado: Literal["cerrado", "pendiente_respuesta", "pendiente_creacion", "pendiente"]
    solicitud_id_plataforma_externa: str | None = None
    campos_faltantes: list[CampoMinimo] = Field(default_factory=list)

    @model_validator(mode="after")
    def validar_estado(self):
        if self.proximo_paso == "CIERRE_POR_INFORMACION_INSUFICIENTE":
            if self.estado != "cerrado" or self.solicitud_prioridad is not None:
                raise ValueError("El cierre por datos faltantes no tiene prioridad.")
            if not self.campos_faltantes:
                raise ValueError("El cierre debe indicar los campos faltantes.")
        elif self.solicitud_prioridad is None or self.campos_faltantes:
            raise ValueError("Una solicitud gestionable requiere prioridad y datos completos.")
        if self.proximo_paso == "GESTION_EXTERNA":
            if self.estado not in {"pendiente_creacion", "pendiente"}:
                raise ValueError("Estado incompatible con gestión externa.")
            if (self.estado == "pendiente") != bool(self.solicitud_id_plataforma_externa):
                raise ValueError("Un caso pendiente requiere un identificador externo.")
        elif self.solicitud_id_plataforma_externa is not None:
            raise ValueError("Solo gestión externa tiene identificador externo.")
        if self.proximo_paso == "RESPUESTA_DIRECTA" and self.estado != "pendiente_respuesta":
            raise ValueError("La respuesta directa queda pendiente de respuesta.")
        return self


class CasoExterno(Modelo):
    id_caso: str = Field(min_length=1)
    estado: Literal["pendiente"]


class PrioridadEntrada(Modelo):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "tipo_documento": "CC",
                    "numero_documento_cliente": "000123",
                    "tipo_solicitud": "NOVEDAD_ENTREGA",
                }
            ]
        }
    )
    tipo_documento: str = Field(min_length=1)
    numero_documento_cliente: str = Field(min_length=1)
    tipo_solicitud: str = Field(min_length=1)
