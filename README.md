# Bodega Express - Fase 2: PostgreSQL 16

Esta etapa de la Fase 2 levanta una base PostgreSQL 16 primaria, una réplica física mediante streaming replication, dos instancias de prueba, un balanceador Nginx y un gateway protegido con API Key. La aplicación real de inventario se incorporará posteriormente.

## Requisitos previos

- Docker Engine con Docker Compose.
- PowerShell, Bash u otra terminal para ejecutar los comandos.
- Puertos `8080` disponibles en el equipo anfitrión.

## Configuración del entorno

Crear el archivo `.env` copiando `.env.example`:

```powershell
Copy-Item .env.example .env
```

El archivo `.env` contiene las variables necesarias para levantar la arquitectura y está excluido de Git mediante `.gitignore`. Las contraseñas y la API Key del ejemplo son únicamente valores locales de desarrollo y deben reemplazarse en un entorno real.

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
docker compose up -d
docker compose ps
```

El comando inicia `db-primary`, `db-replica`, `app1`, `app2`, `load-balancer` y `gateway`. Las bases utilizan volúmenes separados. La réplica espera que la primaria esté saludable, ejecuta `pg_basebackup` en su primer inicio y luego arranca PostgreSQL en modo recuperación. El gateway es la única entrada publicada en `http://localhost:8080`; Nginx y las aplicaciones solo son accesibles dentro de la red Docker.

Para forzar la reconstrucción de las imágenes de las aplicaciones y del gateway:

```powershell
docker compose up -d --build
```

## Comprobar los seis servicios

```powershell
docker compose ps
```

Los servicios esperados son `db-primary`, `db-replica`, `app1`, `app2`, `load-balancer` y `gateway`. Los seis deben aparecer activos y saludables.

## Pruebas del gateway y balanceador

Comprobar el estado de todos los servicios:

```powershell
docker compose ps
```

Una petición sin API Key debe devolver `401`:

```powershell
curl.exe --max-time 5 -i http://localhost:8080/
```

Una petición con API Key válida debe pasar al balanceador y conservar `X-Instance`:

```powershell
curl.exe --max-time 5 -i -H "X-API-Key: $apiKey" http://localhost:8080/
```

Realizar varias peticiones autorizadas y observar la alternancia round-robin:

```powershell
1..6 | ForEach-Object { curl.exe --max-time 5 -sS -D - -o NUL -H "X-API-Key: $apiKey" http://localhost:8080/ | Select-String '^X-Instance:' }
```

Una petición con una clave incorrecta también debe devolver `401`:

```powershell
curl.exe --max-time 5 -i -H "X-API-Key: clave-no-valida" http://localhost:8080/
```

El gateway es el único servicio publicado al equipo anfitrión. El balanceador conserva `expose` implícito dentro de la red Docker y no tiene un puerto publicado directamente.

## Prueba de caída de una instancia

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

## Pruebas SQL de replicación

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

## Tolerancia a fallos con `app2`

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
