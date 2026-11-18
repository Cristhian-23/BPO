import os
from pathlib import Path
from typing import Annotated, Literal

from dotenv import load_dotenv
from pydantic import AnyHttpUrl, Field, TypeAdapter, model_validator

from app.identidad import normalizar_compania
from app.schemas import CampoMinimo, Modelo, Prioridad

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
CodigoCategoria = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]*$", max_length=80)]


class ConfigCategoria(Modelo):
    descripcion: str = Field(min_length=1)
    campos_minimos: list[CampoMinimo] = Field(default_factory=list)
    prioridad_base: Prioridad
    proximo_paso: Literal["GESTION_EXTERNA", "RESPUESTA_DIRECTA"]


class ConfigCompania(Modelo):
    campos_minimos: list[CampoMinimo] = Field(min_length=1)
    categoria_respaldo: str
    estrategia_prioridad: str = Field(min_length=1)
    plataforma: str = Field(min_length=1)
    prioridad_url_env: str | None = None
    categorias: dict[CodigoCategoria, ConfigCategoria] = Field(min_length=1)

    @model_validator(mode="after")
    def validar_respaldo(self):
        respaldo = self.categorias.get(self.categoria_respaldo)
        if respaldo is None or respaldo.proximo_paso != "GESTION_EXTERNA":
            raise ValueError("La categoría de respaldo debe existir y delegar gestión externa.")
        return self


class Configuracion(Modelo):
    companias: dict[str, ConfigCompania] = Field(min_length=1)

    @model_validator(mode="after")
    def normalizar_nombres(self):
        normalizadas = {}
        for nombre, compania in self.companias.items():
            clave = normalizar_compania(nombre)
            if not clave or clave in normalizadas:
                raise ValueError("Hay compañías vacías o duplicadas después de normalizar.")
            normalizadas[clave] = compania
        self.companias = normalizadas
        return self


def cargar_configuracion(ruta: Path | None = None) -> Configuracion:
    ruta = ruta or RAIZ_PROYECTO / "config" / "companias.json"
    return Configuracion.model_validate_json(ruta.read_text(encoding="utf-8"))


def cargar_entorno() -> None:
    load_dotenv(RAIZ_PROYECTO / ".env")


def directorio_datos() -> Path:
    ruta = Path(os.getenv("BPO_DATA_DIR", "data"))
    return ruta if ruta.is_absolute() else RAIZ_PROYECTO / ruta


def resolver_url(variable: str | None) -> str:
    valor = os.getenv(variable or "", "").strip()
    if not valor:
        raise ValueError(f"Falta configurar la variable {variable!r}.")
    TypeAdapter(AnyHttpUrl).validate_python(valor)
    return valor


def validar_integraciones(
    configuracion: Configuracion,
    estrategias: set[str],
    plataformas: set[str],
) -> None:
    for nombre, compania in configuracion.companias.items():
        if compania.estrategia_prioridad not in estrategias:
            raise ValueError(f"Estrategia de prioridad desconocida en {nombre}.")
        if compania.plataforma not in plataformas:
            raise ValueError(f"Plataforma desconocida en {nombre}.")
        if compania.estrategia_prioridad == "servicio_externo":
            resolver_url(compania.prioridad_url_env)
