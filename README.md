# Servicio de solicitudes BPO

Microservicio para recibir solicitudes de distintas compañías, verificar la información mínima, clasificarlas, asignar prioridad y definir el siguiente paso. Cubre los pasos 1 al 6 del caso técnico. Para el paso 6, una función interna simula la creación del caso, genera un identificador ficticio y lo guarda en SQLite.

Groq interpreta el texto y devuelve datos estructurados. Las reglas de cada compañía determinan la prioridad, los datos necesarios y la delegación del caso.

## Requisitos e instalación

Se necesita Python 3.12 o superior, una clave de Groq y conexión a Internet para consultar el modelo. Ejecutar desde la carpeta del proyecto en PowerShell:

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path -LiteralPath ".env")) { Copy-Item -LiteralPath ".env.example" -Destination ".env" }
notepad .env
```

Si el entorno ya existe, se puede omitir su creación. Completar `GROQ_API_KEY` y las variables faltantes en `.env`, tomando `.env.example` como referencia. No publicar la clave ni el archivo `.env`.

| Variable | Valor local o uso |
| --- | --- |
| `GROQ_API_KEY` | Clave del proveedor. |
| `GROQ_MODEL` | `openai/gpt-oss-20b` |
| `PRIORIDAD_MENSAJERIA_URL` | `http://127.0.0.1:8001/prioridad` |
| `BPO_DATA_DIR` | Opcional. Por defecto, `data` dentro del proyecto. |

Iniciar el microservicio:

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

Para solicitudes de Mensajería del Valle, iniciar también el simulador de prioridad en otra terminal:

```powershell
.\.venv\Scripts\python.exe -m uvicorn simulador:app --host 127.0.0.1 --port 8001 --reload
```

Gases y las compañías de demostración funcionan sin ese segundo proceso. El análisis de solicitudes nuevas sí necesita conexión a Groq. El simulador expone únicamente `/prioridad` y `/health`; no crea casos.

En Linux o macOS, crear el entorno con `python3 -m venv .venv`, instalar con `.venv/bin/python -m pip install -r requirements.txt` y copiar la configuración con `[ -f .env ] || cp .env.example .env`. Después de completar la clave, usar estos comandos; el segundo va en otra terminal y solo se necesita para Mensajería:

```bash
.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
.venv/bin/python -m uvicorn simulador:app --host 127.0.0.1 --port 8001 --reload
```

## Uso de la API

Abrir [Swagger del microservicio](http://127.0.0.1:8000/docs), seleccionar `POST /solicitudes`, pulsar **Try it out** y elegir un ejemplo del selector. Los seis ejemplos están en `examples/solicitudes.json`:

- `BPO-GAS-001`: incidente técnico con gestión externa.
- `BPO-INFO-001`: consulta con respuesta directa.
- `BPO-INCOMPLETA-001`: incidente sin referencia temporal.
- `BPO-MSJ-001`: prioridad obtenida del servicio de Mensajería.
- `BPO-ENERGIA-001`: compañía adicional de demostración.
- `BPO-REVISION-001`: categoría de respaldo para revisión especializada.

También están disponibles [Swagger del simulador](http://127.0.0.1:8001/docs) y [el estado básico del servicio](http://127.0.0.1:8000/health).

La entrada requiere tres campos de texto. Ejemplo:

```json
{
  "compania": "GASES DEL ORINOCO",
  "solicitud_id": "BPO-GAS-001",
  "solicitud_descripcion": "Desde ayer mi estufa no enciende. Solicito una revisión técnica."
}
```

La respuesta incluye `compania`, `solicitud_id`, `solicitud_fecha` en UTC, `solicitud_tipo`, `solicitud_prioridad`, `justificacion`, `proximo_paso` y `estado`. También contiene:

- `tipo_documento` y `numero_documento_cliente`: datos extraídos del texto, o `null` si no aparecen.
- `solicitud_id_plataforma_externa`: identificador generado para un caso externo, o `null` cuando no corresponde.
- `campos_faltantes`: información necesaria que no se encontró; queda vacío si la solicitud es gestionable.

Los tres resultados posibles son:

- `CIERRE_POR_INFORMACION_INSUFICIENTE`: estado `cerrado`, prioridad `null` y justificación con los datos faltantes.
- `RESPUESTA_DIRECTA`: estado `pendiente_respuesta`. El servicio no redacta ni envía la respuesta.
- `GESTION_EXTERNA`: estado `pendiente` e identificador externo después de confirmar la creación.

El seguimiento y el cierre posterior de los casos delegados siguen a cargo del BPO. Una fecha relativa como «ayer» o «hace dos semanas» aporta información temporal válida. El número de documento se conserva como texto para mantener sus ceros iniciales.

## Compañías y configuración

`config/companias.json` incluye cuatro compañías:

- `GASES DEL ORINOCO`: prioridad por categoría.
- `MENSAJERIA DEL VALLE`: prioridad mediante el servicio HTTP `/prioridad`.
- `ENERGIA DEL NORTE (DEMO)`: prioridad por categoría.
- `AGUAS DE LA SABANA (DEMO)`: prioridad por categoría.

Las dos últimas compañías son ejemplos. Todas usan `plataforma: "simulada"`. Las categorías, prioridades y delegaciones son supuestos del ejercicio; no representan políticas reales de esas empresas.

El JSON define los mínimos por compañía y categoría, la prioridad base, el próximo paso y la estrategia seleccionada. Para agregar una compañía, crear su configuración. Si utiliza prioridad externa, configurar también la URL de ese servicio. Para agregar una categoría o modificar su prioridad y delegación, editar esa compañía y reiniciar el microservicio.

La categoría de respaldo `OTRA_SOLICITUD` deriva a revisión especializada los casos que no encajan en las demás categorías, siempre que tengan la información mínima. La creación ficticia está separada en `app/plataforma.py`, donde se puede incorporar un adaptador para una plataforma real.

El simulador de Mensajería recibe tipo de documento, número de documento y tipo de solicitud. Su regla ficticia asigna prioridad alta a `CC 000123` para `NOVEDAD_ENTREGA`, y media en los demás casos. Para comparar ambas prioridades, usar identificadores de solicitud distintos y otro documento ficticio, por ejemplo `CC 000456`.

## Errores y solicitudes repetidas

- `422`: la entrada no cumple el contrato; por ejemplo, falta `solicitud_descripcion`.
- `404`: la compañía no está configurada. No se consulta al modelo.
- `409`: el identificador ya se usó con otro contenido, o la misma solicitud sigue en procesamiento. En este último caso se devuelve `Retry-After: 2`.
- `502`: una respuesta externa no cumple el contrato esperado.
- `503`: el proveedor, el servicio de prioridad o la persistencia no están disponibles.
- `504`: se agotó el tiempo de espera de Groq o del servicio HTTP de prioridad.

La información insuficiente es un resultado de negocio, no un error `422`. Los fallos se registran indicando compañía, solicitud, etapa y código de error.

La identidad de una solicitud es su compañía normalizada junto con `solicitud_id`. SQLite guarda la entrada, la configuración utilizada, el análisis, la decisión y el resultado:

- Repetir una solicitud terminada con el mismo contenido devuelve su resultado y fecha originales, sin consultar Groq otra vez.
- Cambiar el contenido conservando el identificador produce un `409`. Una solicitud nueva necesita otro identificador.
- Después de un fallo, el reintento reutiliza las etapas guardadas.
- La simulación interna de creación utiliza una clave estable, guarda el caso ficticio y devuelve el mismo identificador al repetirla.

Los datos se guardan en `data/bpo.sqlite3`, `data/plataforma.sqlite3` y `data/bloqueos`, o en el directorio indicado por `BPO_DATA_DIR`. Los bloqueos coordinan procesos del mismo equipo. Ante un fallo, reintentar con la misma identidad conserva el avance. Una integración futura con una plataforma real deberá mantener la prevención de duplicados.
