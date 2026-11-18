from fastapi import FastAPI

from app.schemas import DecisionPrioridad, PrioridadEntrada

app = FastAPI(title="Servicio de prioridad simulado de Mensajería del Valle")


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/prioridad", response_model=DecisionPrioridad)
def consultar_prioridad(datos: PrioridadEntrada) -> DecisionPrioridad:
    prioritario = (
        datos.tipo_documento.upper() == "CC"
        and datos.numero_documento_cliente == "000123"
        and datos.tipo_solicitud == "NOVEDAD_ENTREGA"
    )
    return DecisionPrioridad(
        prioridad="Alta" if prioritario else "Media",
        justificacion=(
            "Regla ficticia: cliente de demostración prioritario."
            if prioritario
            else "Regla ficticia: prioridad estándar de mensajería."
        ),
    )
