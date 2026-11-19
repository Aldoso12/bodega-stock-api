# Bodega Express - Fase 3

Bodega Express dispone de una aplicación real de inventario conectada a PostgreSQL 16, una réplica física mediante streaming replication, dos instancias de aplicación, un balanceador Nginx y un API Gateway protegido mediante API Key. El Gateway es el único punto de entrada publicado y también aplica limitación de solicitudes.

## Requisitos previos

- Docker Engine con Docker Compose.
- PowerShell, Bash u otra terminal para ejecutar los comandos.
- Puertos `8080` disponibles en el equipo anfitrión.

## Configuración del entorno

Crear el archivo `.env` copiando `.env.example`:

```powershell
Copy-Item .env.example .env
```

El archivo `.env` contiene las variables necesarias para levantar la arquitectura y está excluido de Git mediante `.gitignore`. No se deben mostrar ni versionar contraseñas o API Keys reales.

La configuración del Gateway incluye estos valores predeterminados:

```env
RATE_LIMIT_REQUESTS=60
RATE_LIMIT_WINDOW_SECONDS=60
GATEWAY_MAX_BODY_BYTES=1048576
GATEWAY_UPSTREAM_TIMEOUT_SECONDS=8
```

El límite predeterminado permite 60 solicitudes por IP durante una ventana de 60 segundos y acepta cuerpos de hasta 1 MB.

Para las pruebas, la API Key se lee desde `.env` y se mantiene en la variable `$apiKey`, sin mostrar su valor:

```powershell
$apiKey = (Get-Content .env |
  Where-Object { $_ -match '^API_KEY=' } |
  Select-Object -First 1) -replace '^API_KEY=', ''
$apiKey = $apiKey.Trim().Trim('"').Trim("'")
if ([string]::IsNullOrWhiteSpace($apiKey)) {
  throw 'API_KEY no está definida en .env'
}
```

No se deben guardar credenciales reales en archivos versionados.

## Levantar la arquitectura

```powershell
docker compose up -d --build
docker compose ps
```

El comando construye las imágenes y levanta `db-primary`, `db-replica`, `app1`, `app2`, `load-balancer` y `gateway`. En la topología inicial, `db-primary` es el primario y `db-replica` es el standby. Las bases utilizan volúmenes separados. La réplica espera que la primaria esté saludable, ejecuta `pg_basebackup` en su primer inicio y después arranca PostgreSQL en modo recuperación. Al iniciar cada aplicación se crean las tablas `productos` y `movimientos` de forma idempotente en la primaria. El gateway es la única entrada publicada en `http://localhost:8080`; Nginx y las aplicaciones solo son accesibles dentro de la red Docker.

Si las imágenes ya están construidas y actualizadas, puede utilizarse:

```powershell
docker compose up -d
```

## Aplicación de inventario

Las instancias reciben `DB_PRIMARY_URL`, `DB_REPLICA_URL` e `INSTANCE_ID`. En la topología inicial, las escrituras utilizan `db-primary` y las lecturas utilizan `db-replica`. La réplica es asíncrona, por lo que una consulta inmediatamente posterior a una escritura puede tardar en reflejar el cambio.

Las respuestas incluyen `X-Instance`. Las lecturas incluyen `X-DB: replica` y las escrituras incluyen `X-DB: primary`.

| Método | Ruta | Resultado |
| --- | --- | --- |
| GET | `/health` | Estado e identificador de instancia |
| GET | `/productos?buscar=texto` | Productos filtrados opcionalmente por nombre o código |
| GET | `/productos/{id}` | Producto específico |
| GET | `/movimientos` | Historial de movimientos |
| POST | `/productos` | Crea un producto en la primaria |
| POST | `/movimientos` | Registra una entrada o salida en la primaria |

El registro de movimientos actualiza el stock y crea el movimiento en una misma transacción. El bloqueo `FOR UPDATE` evita que solicitudes simultáneas de salida produzcan stock negativo.

## API Gateway

El Gateway escucha en `http://localhost:8080` y reenvía GET y POST al balanceador. Las solicitudes protegidas deben incluir `X-API-Key`; `/health` del Gateway no requiere autenticación.

Comportamiento:

- `401` si falta la API Key o es inválida.
- `429` al superar `RATE_LIMIT_REQUESTS` dentro de `RATE_LIMIT_WINDOW_SECONDS`, con `Retry-After`.
- `413` si el cuerpo supera `GATEWAY_MAX_BODY_BYTES`.
- `405` para métodos no permitidos, indicando `Allow: GET, POST`.
- `502` si el balanceador no está disponible.
- Conserva las cabeceras `X-Instance` y `X-DB` de la aplicación.
- No reenvía cabeceras hop-by-hop, `Server`, `Date` ni la API Key.

## Pruebas mediante el Gateway

Leer la API Key desde `.env` sin imprimirla:

```powershell
$apiKey = (Get-Content .env |
  Where-Object { $_ -match '^API_KEY=' } |
  Select-Object -First 1) -replace '^API_KEY=', ''
$apiKey = $apiKey.Trim().Trim('"').Trim("'")
if ([string]::IsNullOrWhiteSpace($apiKey)) {
  throw 'API_KEY no está definida en .env'
}
```

Consulta autenticada; la respuesta debe incluir `X-Instance` y `X-DB: replica`:

```powershell
curl.exe --max-time 5 -i `
  -H "X-API-Key: $apiKey" `
  http://localhost:8080/productos
```

Crear un producto mediante POST. El archivo temporal evita problemas de interpretación del JSON por PowerShell:

```powershell
$producto = @{
  codigo = "GW-TEST-001"
  nombre = "Producto Gateway"
  descripcion = "Prueba de integración"
  precio = 99.90
  stock = 4
} | ConvertTo-Json -Compress
$payloadFile = Join-Path $env:TEMP 'bodega-producto.json'
[System.IO.File]::WriteAllText(
  $payloadFile,
  $producto,
  [System.Text.UTF8Encoding]::new($false)
)
curl.exe --max-time 5 -i `
  -X POST `
  -H "X-API-Key: $apiKey" `
  -H "Content-Type: application/json" `
  -H "Accept: application/json" `
  --data-binary "@$payloadFile" `
  http://localhost:8080/productos
Remove-Item -LiteralPath $payloadFile
```

La respuesta esperada es `201`, con `X-DB: primary` y `X-Instance`.

Registrar un movimiento usando el identificador de un producto existente:

```powershell
$movimiento = @{
  producto_id = 1
  tipo = "entrada"
  cantidad = 10
  motivo = "Reposición"
} | ConvertTo-Json -Compress
$payloadFile = Join-Path $env:TEMP 'bodega-movimiento.json'
[System.IO.File]::WriteAllText(
  $payloadFile,
  $movimiento,
  [System.Text.UTF8Encoding]::new($false)
)
curl.exe --max-time 5 -i `
  -X POST `
  -H "X-API-Key: $apiKey" `
  -H "Content-Type: application/json" `
  --data-binary "@$payloadFile" `
  http://localhost:8080/movimientos
Remove-Item -LiteralPath $payloadFile
```

Una solicitud sin API Key debe devolver JSON con HTTP 401:

```powershell
curl.exe --max-time 5 -i http://localhost:8080/productos
```

## Comprobar los seis servicios

```powershell
docker compose ps
```

Los servicios esperados son `db-primary`, `db-replica`, `app1`, `app2`, `load-balancer` y `gateway`. Durante la validación inicial, antes del failover, los seis estuvieron activos y saludables.

Después de promover `db-replica`, su healthcheck puede mostrar `unhealthy` porque comprueba que `pg_is_in_recovery() = true`, una condición propia de un standby. Esto no significa necesariamente que PostgreSQL no esté disponible: el nodo promovido puede aceptar conexiones como primario. Esta limitación del healthcheck no modifica la topología ni se corrige en Compose.

## Pruebas de integración de Fase 3

Estas son las pruebas realizadas para validar la integración del Gateway y la aplicación real:

- Los seis servicios estuvieron activos y saludables durante la validación inicial, antes del failover.
- GET sin API Key: HTTP 401.
- GET autenticado: HTTP 200, con lectura desde la réplica.
- Balanceador: ocho solicitudes distribuidas, cuatro a `app-1` y cuatro a `app-2`.
- POST autenticado mediante el Gateway: HTTP 201, con escritura en la primaria.
- GET posterior del producto creado: HTTP 200 desde la réplica.
- Rate Limiting: 60 respuestas HTTP 200 y cinco respuestas HTTP 429 en 65 solicitudes.
- DELETE: HTTP 405 con `Allow: GET, POST`.
- Cuerpo de 1.048.588 bytes: HTTP 413.
- No se realizaron escrituras de prueba durante el failover controlado.
- `pg_rewind` informó `no rewind required`.
- La replicación final quedó en estado `streaming`, con `db-replica` como emisor y `db-primary` como receptor.
- La posición WAL observada en ambos nodos fue `0/30CA8D0`.
- Todos los registros de `productos` y `movimientos` coincidieron después de la reincorporación.

El 18 de noviembre de 2026 se ejecutó un failover controlado. La interrupción comenzó a las `18:10:38.0610504 -03:00`; antes de detener la primaria se observó una diferencia WAL de `0 bytes`. Este RPO corresponde únicamente a esta ejecución y no es una garantía universal de pérdida cero.

La promoción de `db-replica` comenzó a las `18:14:31.4471380 -03:00` y finalizó correctamente, pero la hora exacta de finalización no quedó registrada. Durante la recuperación, app1, app2 y Gateway apuntaron temporalmente a `db-replica`.

El RTO confirmado fue de `315.94 segundos` (aproximadamente `5 minutos 16 segundos`), medido desde el inicio de la interrupción hasta una respuesta HTTP `200` del Gateway a las `18:15:54 -03:00`. Este valor representa la recuperación confirmada del Gateway y no una hora independiente de recuperación para cada aplicación.

### Topología final después del failover

```text
Gateway
   |
   v
load-balancer
   |
   v
app1/app2
   |
   v
db-replica (único primario; pg_is_in_recovery=false)
          |
          | streaming WAL asíncrono
          v
db-primary (standby; pg_is_in_recovery=true)
```

La replicación final es unidireccional, desde `db-replica` hacia `db-primary`. `db-primary` fue reincorporado como standby después de recuperar el servicio, y no es una topología bidireccional.

El Gateway es el único servicio publicado al equipo anfitrión. El balanceador no publica puertos al equipo anfitrión y solo es accesible dentro de la red interna de Docker.

## Antecedentes históricos: prueba de caída de una instancia

Esta prueba fue ejecutada satisfactoriamente. Se detuvo temporalmente `app1`; durante la prueba, las seis peticiones autorizadas respondieron HTTP 200 desde `app-2`, identificado mediante `X-Instance`. Después, `app1` fue restaurada:

```powershell
docker compose stop app1
1..6 | ForEach-Object { curl.exe --max-time 5 -sS -D - -o NUL -H "X-API-Key: $apiKey" http://localhost:8080/ | Select-String '^HTTP/|^X-Instance:' }
docker compose start app1
docker compose ps
```

Salida real de las seis peticiones:

```text
HTTP/1.0 200 OK
X-Instance: app-2
HTTP/1.0 200 OK
X-Instance: app-2
HTTP/1.0 200 OK
X-Instance: app-2
HTTP/1.0 200 OK
X-Instance: app-2
HTTP/1.0 200 OK
X-Instance: app-2
HTTP/1.0 200 OK
X-Instance: app-2
```

## Antecedentes históricos: pruebas SQL de replicación

Estas pruebas corresponden a la topología anterior al failover, con `db-primary` como primaria y `db-replica` como réplica; no describen los roles finales.

1. Comprobar que ambos servicios estén activos:

   ```powershell
   docker compose ps
   ```

2. Escribir un dato en la primaria:

   ```powershell
   docker compose exec db-primary psql -U bodega_admin -d bodega -c "CREATE TABLE IF NOT EXISTS prueba_replicacion (id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY, mensaje text NOT NULL); INSERT INTO prueba_replicacion (mensaje) VALUES ('Validacion final Bodega Express 12 noviembre');"
   ```

3. Confirmar mediante SQL que el registro insertado llegó a la réplica:

   ```powershell
   docker compose exec db-replica psql -U bodega_admin -d bodega -c "SELECT * FROM prueba_replicacion ORDER BY id DESC LIMIT 3;"
   ```

   La réplica debe mostrar entre los últimos registros el mensaje `Validacion final Bodega Express 12 noviembre`.
   El ID asignado depende de las inserciones anteriores; no se establece un ID fijo como resultado esperado.
   Esto demuestra que la réplica recibe las escrituras realizadas en la primaria.

4. Confirmar opcionalmente que la réplica está en recuperación:

   ```powershell
   docker compose exec db-replica psql -U bodega_admin -d bodega -tAc "SELECT pg_is_in_recovery();"
   ```

   El resultado esperado es `t`.

5. Consultar el estado de envío y recepción en las bases:

   ```powershell
   docker compose exec db-primary psql -U bodega_admin -d bodega -c "SELECT client_addr, state, sync_state FROM pg_stat_replication;"
   docker compose exec db-replica psql -U bodega_admin -d bodega -c "SELECT status, sender_host, slot_name FROM pg_stat_wal_receiver;"
   ```

## Antecedentes históricos: tolerancia a fallos con `app2`

El 12 de noviembre de 2026 se detuvo `app2` y se realizaron cinco peticiones autorizadas.
Todas respondieron HTTP 200 desde `app-1`, identificado mediante `X-Instance`:

```powershell
docker compose stop app2
1..5 | ForEach-Object { curl.exe --max-time 5 -sS -D - -o NUL -H "X-API-Key: $apiKey" http://localhost:8080/ | Select-String '^HTTP/|^X-Instance:' }
```

Después se restauró `app2` y se comprobó que los seis servicios quedaron saludables:

```powershell
docker compose start app2
docker compose ps
```

Para restaurar `app1` después de su prueba de caída:

```powershell
docker compose start app1
docker compose ps
```

## Detener la arquitectura

```powershell
docker compose down
```

Para eliminar también los datos persistidos y repetir la inicialización desde cero:

```powershell
docker compose down -v
```

El segundo comando es destructivo: elimina los volúmenes persistentes de PostgreSQL y no es necesario para el inicio normal. Úsalo solo cuando sea necesario reinicializar completamente los datos.

La evidencia detallada de las pruebas está en [docs/fase2/EVIDENCIAS.md](docs/fase2/EVIDENCIAS.md).

La información de este README se limita a la implementación, configuración, comandos y resultados comprobados del proyecto. No se agregan resultados, comandos, configuraciones ni funcionalidades no verificadas.
