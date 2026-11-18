import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
from filelock import Timeout

from app.configuracion import ConfigCompania, Configuracion
from app.errores import ErrorServicio
from app.identidad import normalizar_compania
from app.plataforma import crear_caso_externo
from app.prioridades import calcular_prioridad, requisitos_prioridad
from app.repositorio import RepositorioSolicitudes
from app.schemas import AnalisisSolicitud, ResultadoSolicitud, SolicitudEntrada

logger = logging.getLogger(__name__)


def evaluar_solicitud(
    solicitud: SolicitudEntrada,
    compania: ConfigCompania,
    analisis: AnalisisSolicitud,
    cliente: httpx.Client,
) -> ResultadoSolicitud:
    categoria_id = analisis.categoria or compania.categoria_respaldo
    categoria = compania.categorias[categoria_id]
    requeridos = list(
        dict.fromkeys(
            [
                *compania.campos_minimos,
                *categoria.campos_minimos,
                *requisitos_prioridad(compania),
            ]
        )
    )
    faltantes = [campo for campo in requeridos if not getattr(analisis, campo)]
    datos = {
        "compania": normalizar_compania(solicitud.compania),
        "solicitud_id": solicitud.solicitud_id,
        "solicitud_fecha": datetime.now(UTC),
        "solicitud_tipo": analisis.categoria if faltantes else categoria_id,
        "tipo_documento": analisis.tipo_documento,
        "numero_documento_cliente": analisis.numero_documento_cliente,
    }
    if faltantes:
        return ResultadoSolicitud(
            **datos,
            solicitud_prioridad=None,
            proximo_paso="CIERRE_POR_INFORMACION_INSUFICIENTE",
            justificacion="Información incompleta o faltante. Faltan: "
            + ", ".join(faltantes)
            + ".",
            estado="cerrado",
            campos_faltantes=faltantes,
        )
    # Si el modelo no eligió categoría, la estrategia externa recibe el respaldo configurado.
    analisis_prioridad = analisis.model_copy(update={"categoria": categoria_id})
    decision = calcular_prioridad(compania, categoria, analisis_prioridad, cliente)
    evidencia = analisis.que_paso or analisis.que_necesita
    respaldo = (
        " Requiere revisión especializada." if categoria_id == compania.categoria_respaldo else ""
    )
    return ResultadoSolicitud(
        **datos,
        solicitud_prioridad=decision.prioridad,
        proximo_paso=categoria.proximo_paso,
        justificacion=(
            f"Prioridad {decision.prioridad}. {decision.justificacion} "
            f"Solicitud: {evidencia}. Delegación: {categoria.proximo_paso}.{respaldo}"
        ),
        estado=(
            "pendiente_creacion"
            if categoria.proximo_paso == "GESTION_EXTERNA"
            else "pendiente_respuesta"
        ),
    )


def registrar_evento(
    evento: str, solicitud: SolicitudEntrada, etapa: str, codigo: str | None = None
) -> None:
    datos = {
        "evento": evento,
        "compania": normalizar_compania(solicitud.compania),
        "solicitud_id": solicitud.solicitud_id,
        "etapa": etapa,
    }
    if codigo:
        datos["codigo"] = codigo
    logger.log(logging.WARNING if codigo else logging.INFO, json.dumps(datos, ensure_ascii=False))


class ServicioSolicitudes:
    def __init__(
        self,
        configuracion: Configuracion,
        repositorio: RepositorioSolicitudes,
        analizar: Callable[[str, ConfigCompania], AnalisisSolicitud],
        cliente_prioridad: httpx.Client,
    ):
        self.configuracion = configuracion
        self.repositorio = repositorio
        self.analizar = analizar
        self.cliente_prioridad = cliente_prioridad

    def procesar(self, solicitud: SolicitudEntrada) -> ResultadoSolicitud:
        compania = self.configuracion.companias.get(normalizar_compania(solicitud.compania))
        if compania is None:
            raise ErrorServicio(
                "COMPANIA_NO_CONFIGURADA", "La compañía no está parametrizada.", 404
            )
        etapa = "registro"
        try:
            with self.repositorio.bloquear(solicitud):
                registro = self.repositorio.obtener_o_crear(solicitud, compania)
                if registro.resultado is not None:
                    registrar_evento("resultado_reutilizado", solicitud, "resultado")
                    return registro.resultado
                compania = registro.compania
                try:
                    etapa = "analisis"
                    analisis = registro.analisis
                    if analisis is None:
                        analisis = self.analizar(solicitud.solicitud_descripcion, compania)
                        self.repositorio.guardar_etapa(solicitud, "analisis", analisis)

                    etapa = "decision"
                    resultado = registro.decision
                    if resultado is None:
                        resultado = evaluar_solicitud(
                            solicitud, compania, analisis, self.cliente_prioridad
                        )
                        self.repositorio.guardar_etapa(solicitud, "decision", resultado)

                    if resultado.proximo_paso == "GESTION_EXTERNA":
                        etapa = "plataforma"
                        externo = crear_caso_externo(
                            solicitud, compania, resultado, self.repositorio.ruta.parent
                        )
                        resultado = ResultadoSolicitud.model_validate(
                            {
                                **resultado.model_dump(),
                                "solicitud_id_plataforma_externa": externo.id_caso,
                                "estado": externo.estado,
                            }
                        )
                    etapa = "resultado"
                    self.repositorio.guardar_etapa(solicitud, "resultado", resultado)
                    registrar_evento("solicitud_procesada", solicitud, etapa)
                    return resultado
                except Exception as exc:
                    codigo = exc.codigo if isinstance(exc, ErrorServicio) else type(exc).__name__
                    registrar_evento("solicitud_fallida", solicitud, etapa, codigo)
                    try:
                        self.repositorio.registrar_error(solicitud, codigo)
                    except ErrorServicio:
                        registrar_evento("registro_fallido", solicitud, "persistencia")
                    raise
        except Timeout as exc:
            raise ErrorServicio(
                "SOLICITUD_EN_PROCESO", "La solicitud está siendo procesada. Reintenta.", 409, 2
            ) from exc
        except OSError as exc:
            raise ErrorServicio(
                "PERSISTENCIA_NO_DISPONIBLE", "No se pudo adquirir el bloqueo local.", 503
            ) from exc
