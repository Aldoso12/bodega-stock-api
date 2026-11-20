# Prueba controlada de failover y recuperación de PostgreSQL 16

## Objetivo

Preparar una prueba manual de failover en la que `db-replica` pase a ser la base primaria y `db-primary`, después de detenerse y reconciliarse cuando exista divergencia, vuelva como réplica del nuevo primario.

Este documento es solamente operativo. No contiene credenciales ni debe ejecutarse sin autorización expresa. La promoción, el cambio de destinos y el reinicio de servicios son acciones que interrumpen o pueden modificar datos.

## Estado inicial conocido antes de la prueba

- Motor: PostgreSQL 16.15.
- Primario inicial: `db-primary`.
- Réplica inicial: `db-replica`.
- Replicación streaming asíncrona.
- Usuario administrador confirmado: `bodega_admin`, con superusuario y replicación.
- Usuario de replicación confirmado: `bodega_replicator`.
- Base confirmada: `bodega`.
- `wal_log_hints=on` en ambos servidores.
- `full_page_writes=on` en ambos servidores.
- `pg_rewind` disponible en ambos servidores.
- Las aplicaciones leen de `DB_REPLICA_URL` y escriben en `DB_PRIMARY_URL`.
- Los productos y movimientos coincidentes confirmados inicialmente: 6 productos y 3 movimientos.

Valores sensibles como contraseñas y API Keys no se registran en este documento. Los comandos deben obtenerlos del archivo `.env` sin imprimirlos.

## Arquitectura antes de la prueba

```text
Aplicaciones app1/app2
    |
    | escrituras
    v
db-primary (primario; pg_is_in_recovery=false)
    | streaming WAL async
    v
db-replica (standby; pg_is_in_recovery=true)

app1/app2 usan lecturas -> db-replica
app1/app2 usan escrituras -> db-primary
```

## Arquitectura prevista después de la recuperación

```text
app1/app2
    | escrituras
    v
db-replica (nuevo primario; pg_is_in_recovery=false)
    | streaming WAL async
    v
db-primary (antiguo primario convertido en standby)
```

No se considera completo el failover hasta que:

1. `db-replica` acepta escritura.
2. `db-primary` está detenido o en recovery.
3. Las aplicaciones y el Gateway están recreados con `DB_PRIMARY_HOST=db-replica` y el servicio responde.
4. El antiguo primario fue reincorporado como standby; se usa `pg_rewind` solo si existe divergencia que requiera reconciliación.
5. El receptor de la nueva topología informa `streaming`, como criterio de reincorporación completa.

## Resultado real de la prueba realizada el 18 de noviembre de 2026

- Inicio de la interrupción: `18:10:38.0610504 -03:00`.
- Sincronización previa: diferencia WAL observada de `0 bytes`.
- Detención confirmada de `db-primary`: `18:13:24.2667926 -03:00`.
- Promoción de `db-replica`: iniciada a las `18:14:31.4471380 -03:00` y completada correctamente.
- Topología final:
  - `db-replica`: primario activo, `pg_is_in_recovery=false`, timeline 2.
  - `db-primary`: standby activo, `pg_is_in_recovery=true`.
- Aplicaciones y Gateway recreados temporalmente con ambos destinos hacia `db-replica` y confirmados saludables.
- GET autenticado al Gateway: HTTP `200`; lectura atendida por `app-2`.
- No se realizaron escrituras de prueba ni POST durante el failover.
- Reincorporación: `.pgpass` con modo `600`, propietario PostgreSQL, `standby.signal` presente y una única configuración `primary_conninfo` apuntando a `db-replica`.
- Streaming final:
  - `db-replica` informó `pg_stat_replication.state=streaming`.
  - `db-primary` informó `pg_stat_wal_receiver.status=streaming`.
  - Origen confirmado: `db-replica`.
- Posición WAL observada en ambos nodos: `0/30CA8D0`.
- Comparación completa:
  - Todos los registros de `productos` coinciden.
  - Todos los registros de `movimientos` coinciden.

## Recursos reales

### Servicios Docker Compose

| Servicio | Contenedor | Uso |
|---|---|---|
| `db-primary` | `bodega-db-primary` | Antiguo primario, actualmente standby |
| `db-replica` | `bodega-db-replica` | Nuevo primario, actualmente activo |
| `app1` | `bodega-app-1` | Aplicación instancia 1 |
| `app2` | `bodega-app-2` | Aplicación instancia 2 |
| `load-balancer` | `bodega-load-balancer` | Nginx |
| `gateway` | `bodega-gateway` | Gateway con API Key y limitación |

### Volúmenes Docker

Los nombres reales creados por el proyecto son:

- `bodega-stock-api_db_primary_data` para `/var/lib/postgresql/data` de `db-primary`.
- `bodega-stock-api_db_replica_data` para `/var/lib/postgresql/data` de `db-replica`.

No se deben eliminar ni renombrar estos volúmenes.

### Dependencias

- `app1` depende de `db-primary` y `db-replica`.
- `app2` depende de `db-primary` y `db-replica`.
- `load-balancer` depende de `app1` y `app2`.
- `gateway` depende de `load-balancer`.
- `db-replica` depende de que `db-primary` tenga healthcheck exitoso.
- Los archivos de inicialización se montan de forma ro desde `scripts/`.

## Preparación

Antes de autorizar la prueba, ejecutar los siguientes comandos desde `C:\Users\aldos\Desktop\bodega-stock-api`.

### Abrir PowerShell en el proyecto y registrar tiempos

```powershell
Set-Location 'C:\Users\aldos\Desktop\bodega-stock-api'
$global:FailoverStart = Get-Date
"Preparación iniciada: $($global:FailoverStart.ToString('o'))"

docker compose ps
docker volume ls --format '{{.Name}}' | Select-String 'db_(primary|replica)_data'
```

No imprimir valores sensibles del `.env`.

### Confirmar estado base

```powershell
docker compose exec -T db-primary pg_isready -U bodega_admin -d bodega
docker compose exec -T db-replica pg_isready -U bodega_admin -d bodega

docker compose exec -T db-primary psql -U bodega_admin -d bodega -X -v ON_ERROR_STOP=1 -c `
  "SELECT pg_is_in_recovery() AS in_recovery, pg_current_wal_lsn() AS current_lsn, pg_current_wal_flush_lsn() AS flush_lsn;"

docker compose exec -T db-replica psql -U bodega_admin -d bodega -X -v ON_ERROR_STOP=1 -c `
  "SELECT pg_is_in_recovery() AS in_recovery, pg_last_wal_receive_lsn() AS receive_lsn, pg_last_wal_replay_lsn() AS replay_lsn;"
```

Se detendrá la prueba si el primario ya está en recuperación, si la réplica no está en recuperación o si `pg_isready` falla.

### Verificar streaming y parámetros

```powershell
docker compose exec -T db-primary psql -U bodega_admin -d bodega -X -v ON_ERROR_STOP=1 -c `
  "SELECT application_name, client_addr, state, sync_state, sent_lsn, write_lsn, flush_lsn, replay_lsn FROM pg_stat_replication;"

docker compose exec -T db-replica psql -U bodega_admin -d bodega -X -v ON_ERROR_STOP=1 -c `
  "SELECT status, sender_host, written_lsn, flushed_lsn, latest_end_lsn FROM pg_stat_wal_receiver;"

docker compose exec -T db-primary psql -U bodega_admin -d bodega -X -v ON_ERROR_STOP=1 -tAc `
  "SELECT current_setting('wal_log_hints'), current_setting('full_page_writes');"

docker compose exec -T db-replica psql -U bodega_admin -d bodega -X -v ON_ERROR_STOP=1 -tAc `
  "SELECT current_setting('wal_log_hints'), current_setting('full_page_writes');"
```

Se requieren:

- Estado `streaming` en `pg_stat_replication`.
- Estado `streaming` en `pg_stat_wal_receiver`.
- `wal_log_hints=on`.
- `full_page_writes=on`.

### Respaldos

Con los servicios aún disponibles, crear un respaldo lógico nuevo con nombre por fecha y hora. Este comando no sobrescribe respaldos existentes.

```powershell
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backup = ".\backups\pre-failover-$stamp.sql"
$containerBackup = "/tmp/pre-failover-$stamp.sql"

if (Test-Path -LiteralPath $backup) {
  throw "El respaldo ya existe: $backup. No se sobrescribirá."
}

docker compose exec -T db-primary pg_dump --username=bodega_admin --dbname=bodega --format=plain --no-owner --no-acl --file=$containerBackup
docker cp "bodega-db-primary:$containerBackup" $backup
docker compose exec -T db-primary rm -f $containerBackup

Get-Item $backup | Select-Object Name,Length
```

También pueden conservarse los respaldos existentes:

- `backups/primary-backup.sql`
- `backups/replica-backup.sql`

No eliminarlos ni sobrescribirlos.

### Registrar integridad y última posición WAL

```powershell
docker compose exec -T db-primary psql -U bodega_admin -d bodega -X -v ON_ERROR_STOP=1 -c `
  "SELECT count(*) AS productos FROM productos;"
docker compose exec -T db-primary psql -U bodega_admin -d bodega -X -v ON_ERROR_STOP=1 -c `
  "SELECT count(*) AS movimientos FROM movimientos;"

docker compose exec -T db-primary psql -U bodega_admin -d bodega -X -v ON_ERROR_STOP=1 -c `
  "SELECT application_name, state, replay_lsn, pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS bytes_pendientes FROM pg_stat_replication;"

$global:PreFailoverTimestamp = Get-Date
"Marca RPO: $($global:PreFailoverTimestamp.ToString('o'))"
```

Para RPO, guardar el número de bytes pendientes y el estado de replicación inmediatamente antes de detener aplicaciones.
RPO real de bytes = diferencia entre el LSN confirmado en el primario y el LSN recibido/reproducido en la réplica en el momento observado.
RPO temporal = diferencia aproximada entre los timestamps operativos registrados. `pg_last_xact_replay_timestamp()` solo existe con significado en la réplica y corresponde al commit WAL reproducido más recientemente; no representa el momento exacto de creación de cada dato ni reemplaza una medida de LSN.
PostgreSQL no permite inferir con exactitud un RPO temporal real sin contar con una transacción o evento marcado por el propio plan de prueba.

No se inventa un objetivo RPO. Se registra lo observado y el RPO basado en timestamps se presenta únicamente como aproximación; no es una medición exacta de transacciones perdidas.

## Detención controlada de escrituras

Antes de detener `db-primary`, detenga las rutas que pueden generar escrituras. Esta operación debe ejecutarse solamente durante la ventana autorizada.

```powershell
$global:InterruptionStart = Get-Date
"Inicio de interrupción: $($global:InterruptionStart.ToString('o'))"

docker compose stop -t 30 app1 app2 gateway
```

Debe quedar `app1`, `app2` y `gateway` detenidos. `load-balancer` puede permanecer activo, pero sin instancias disponibles. La detención del gateway evita el acceso HTTP externo.

Alternativamente, si la intervención requiere mantener gateway y aplicaciones activos, se puede bloquear nuevas conexiones:

```powershell
docker compose exec -T db-primary psql -U bodega_admin -d bodega -X -v ON_ERROR_STOP=1 -c `
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity
   WHERE datname = 'bodega' AND usename = 'bodega_admin' AND pid <> pg_backend_pid();"
```

Este último método no es suficiente por sí solo: las sesiones nuevas pueden reconectar. Por ello, se recomienda detener aplicaciones y gateway durante la prueba.

## Verificación de la última posición WAL

Esperar hasta que no existan escrituras pendientes.

```powershell
$global:WalSourceTimestamp = Get-Date
"Timestamp de observacion primaria: $($global:WalSourceTimestamp.ToString('o'))"

docker compose exec -T db-primary psql -U bodega_admin -d bodega -X -v ON_ERROR_STOP=1 -c `
  "SELECT pg_current_wal_lsn() AS source_lsn,
          pg_current_wal_flush_lsn() AS source_flush_lsn;"

docker compose exec -T db-primary psql -U bodega_admin -d bodega -X -v ON_ERROR_STOP=1 -c `
  "SELECT application_name, state, replay_lsn,
          pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS bytes_pendientes
   FROM pg_stat_replication;"

docker compose exec -T db-replica psql -U bodega_admin -d bodega -X -v ON_ERROR_STOP=1 -c `
  "SELECT pg_last_wal_receive_lsn() AS receive_lsn,
          pg_last_wal_replay_lsn() AS replay_lsn,
          pg_last_xact_replay_timestamp() AS replay_timestamp;"
```

Antes de continuar, guardar en el registro:

- `source_lsn`.
- `source_flush_lsn` y su hora de observación.
- `replay_lsn`.
- `bytes_pendientes`.
- `replay_timestamp` obtenido exclusivamente de la réplica.

`pg_current_wal_flush_lsn()` mide la posición WAL enviada al búfer local que el primario confirmó como escrita y permite registrar una posición fuente. `pg_last_xact_replay_timestamp()` mide el timestamp de la última transacción replayada en la réplica, no garantiza que todos los datos tengan ese timestamp y no debe usarse como único indicador de pérdida.

### Espera limitada de sincronización

Usar como máximo 30 intentos separados por 2 segundos (timeout aproximado de 60 segundos). Ajustar el timeout solo después de una autorización técnica explícita.

```powershell
$maxAttempts = 30
$delaySeconds = 2
$deadline = [TimeSpan]::FromSeconds(60)
$stopwatch = [Diagnostics.Stopwatch]::StartNew()
$synced = $false
$attempt = 0

while ($attempt -lt $maxAttempts -and $stopwatch.Elapsed -lt $deadline) {
  $attempt++
  $pending = docker compose exec -T db-primary psql -U bodega_admin -d bodega -X -v ON_ERROR_STOP=1 -tAc `
    "SELECT COALESCE(pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn)::text, 'no-replica')
     FROM pg_stat_replication
     WHERE application_name = 'walreceiver' AND state = 'streaming';"

  $pending = ($pending | Select-Object -First 1).Trim()
  "Intento $attempt/$maxAttempts - bytes pendientes: $pending"

  if ($pending -eq '0') {
    $synced = $true
    break
  }
  $remaining = $deadline - $stopwatch.Elapsed
  if ($remaining -le [TimeSpan]::Zero) {
    break
  }
  $sleepSeconds = [Math]::Min($delaySeconds, [Math]::Ceiling($remaining.TotalSeconds))
  Start-Sleep -Seconds $sleepSeconds
}

if (-not $synced) {
  throw "Sincronización WAL no alcanzada (intentos: $attempt/$maxAttempts; tiempo: $([Math]::Round($stopwatch.Elapsed.TotalSeconds, 1)) s). Detener sin promover y mantener db-primary."
}

$global:WalSyncTimestamp = Get-Date
"Sincronización alcanzada: $($global:WalSyncTimestamp.ToString('o'))"
```

Si no se alcanza una diferencia cero dentro de los intentos permitidos, detener la prueba sin promover, sin ejecutar `pg_rewind` y manteniendo `db-primary` como primario.

## Detención segura del antiguo primario

Después de confirmar que no existen escrituras pendientes, detener el principal.

```powershell
$global:PrimaryStopStart = Get-Date
"Inicio detención primario: $($global:PrimaryStopStart.ToString('o'))"

docker compose stop -t 30 db-primary
docker compose ps db-primary db-replica
```

El contenedor antiguo no debe reiniciarse hasta completar la reconciliación requerida, con `pg_rewind` solo si existe divergencia.

No ejecutar `docker compose exec` contra un contenedor detenido. Comprobar únicamente su estado:

```powershell
docker compose ps db-primary
docker inspect --format '{{.State.Status}}' bodega-db-primary
```

El estado esperado es `exited` o `stopped`; esto confirma que el contenedor está detenido, no que un servidor PostgreSQL esté disponible. Si aparece `running`, detener la prueba y revisar split-brain. Solo se puede usar `pg_isready` después de confirmar que el contenedor está `running`.

## Promoción manual de db-replica

Confirmar una última vez que la réplica está sana y registra el modo standby.

```powershell
docker compose exec -T db-replica psql -U bodega_admin -d bodega -X -v ON_ERROR_STOP=1 -c `
  "SELECT pg_is_in_recovery() AS in_recovery,
          pg_last_wal_receive_lsn() AS receive_lsn,
          pg_last_wal_replay_lsn() AS replay_lsn;"
```

El resultado esperado antes de la promoción es `in_recovery=true`.

Promover sin ejecutar `pg_promote()`:

```powershell
$global:PromotionStart = Get-Date
"Inicio promoción: $($global:PromotionStart.ToString('o'))"

docker compose exec -u postgres db-replica pg_ctl promote -D /var/lib/postgresql/data -w -t 60

docker compose exec -T db-replica psql -U bodega_admin -d bodega -X -v ON_ERROR_STOP=1 -c `
  "SELECT pg_is_in_recovery() AS in_recovery,
          pg_current_wal_lsn() AS current_lsn,
          timeline_id
   FROM pg_control_checkpoint();"
```

El resultado esperado es `in_recovery=false`. El tiempo de promoción es una parte del RTO.
La promoción queda bloqueada si la espera WAL anterior no terminó con `$synced=$true`; no se debe continuar por haber alcanzado solo el límite de intentos o el deadline.

Si la promoción falla:

1. No ejecutar `pg_rewind`.
2. Mantener `db-primary` detenido.
3. Revisar logs:

```powershell
docker compose logs --tail=200 db-replica
docker compose logs --tail=200 db-primary
```

4. Activar el procedimiento de reversión definido en este documento.

## Cambio temporal de destinos de aplicaciones

Después de una promoción confirmada, recrear las aplicaciones con ambos destinos apuntando a `db-replica`.

Las variables se pasan en memoria y no se escriben en `.env` ni en `docker-compose.yml`.
La recuperación de app1, app2 y Gateway es posterior a la promoción y no debe esperar a que el antiguo primario haya sido reincorporado. Antes de recrearlas, esta comprobación es una condición obligatoria de bloqueo:

```powershell
$replicaRecovery = docker compose exec -T db-replica psql -U bodega_admin -d bodega -X -v ON_ERROR_STOP=1 -tAc `
  "SELECT pg_is_in_recovery();"

if ($replicaRecovery.Trim() -ne 'f') {
  throw 'Bloqueo: db-replica no está confirmado como primario. No recrear aplicaciones.'
}

$env:DB_PRIMARY_HOST = 'db-replica'
$env:DB_REPLICA_HOST = 'db-replica'

docker compose up -d --no-deps --force-recreate app1 app2 gateway
docker compose ps app1 app2 gateway load-balancer db-replica db-primary
```

El contenedor `db-primary` puede seguir detenido mientras se recuperan las aplicaciones y el Gateway. Su reincorporación como standby y la comprobación de `streaming` son una etapa posterior.

Nota sobre el healthcheck: el healthcheck de `db-replica` comprueba la disponibilidad de PostgreSQL mediante `pg_isready -U "$${POSTGRES_USER}" -d "$${POSTGRES_DB}"`. No comprueba el rol del nodo ni su estado de recuperación; el rol debe confirmarse mediante `pg_is_in_recovery()`. No se modifica Compose en esta prueba.

Verificar la configuración efectiva sin mostrar contraseñas:

```powershell
docker compose exec -T app1 python -c "import psycopg, os; p=psycopg.connect(os.environ['DB_PRIMARY_URL']); r=psycopg.connect(os.environ['DB_REPLICA_URL']); print('app1-primary-host=', p.info.host); print('app1-replica-host=', r.info.host); p.close(); r.close()"
docker compose exec -T app2 python -c "import psycopg, os; p=psycopg.connect(os.environ['DB_PRIMARY_URL']); r=psycopg.connect(os.environ['DB_REPLICA_URL']); print('app2-primary-host=', p.info.host); print('app2-replica-host=', r.info.host); p.close(); r.close()"
```

## Verificación posterior a la promoción

### Salud HTTP

```powershell
curl.exe -i --max-time 10 http://127.0.0.1:8080/health
# Después de confirmar que la respuesta del Gateway fue HTTP 200:
$global:GatewayRecoveryTimestamp = Get-Date

docker compose exec -T app1 python -c "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5); print(r.status, r.read().decode())"
docker compose exec -T app2 python -c "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5); print(r.status, r.read().decode())"
```

### Base nueva primaria

```powershell
docker compose exec -T db-replica psql -U bodega_admin -d bodega -X -v ON_ERROR_STOP=1 -c `
  "SELECT pg_is_in_recovery() AS in_recovery, pg_current_wal_lsn() AS current_lsn;"

docker compose exec -T db-replica psql -U bodega_admin -d bodega -X -v ON_ERROR_STOP=1 -c `
  "SELECT count(*) AS productos FROM productos;
   SELECT count(*) AS movimientos FROM movimientos;"

docker compose exec -T db-replica psql -U bodega_admin -d bodega -X -v ON_ERROR_STOP=1 -c `
  "SELECT application_name, client_addr, state, sync_state,
          sent_lsn, write_lsn, flush_lsn, replay_lsn
   FROM pg_stat_replication;"

```

Esta comprobación no realiza DDL ni DML. No se ejecuta escritura persistente ni temporal.
Una prueba escrita requiere autorización separada y debe realizarse con una transacción explícita que haga ROLLBACK, o con datos permanentes creados y eliminados por un procedimiento aprobado. No debe incorporarse como una prueba implícita del failover.

### Medir RTO

```powershell
$global:PromotionTimestamp = $null
$rtoFullService = $global:GatewayRecoveryTimestamp - $global:InterruptionStart
"RTO de detención a promoción: no calculable; hora exacta de promoción no registrada"
"RTO de interrupción a servicio Gateway recuperado: $($rtoFullService.TotalSeconds) segundos"
"Hora de promoción: no registrada"
"Hora de recuperación del Gateway: $($global:GatewayRecoveryTimestamp.ToString('o'))"
```

Registrar `$global:GatewayRecoveryTimestamp` inmediatamente después de confirmar el HTTP `200` del Gateway. Esta marca es la hora de recuperación del Gateway, no la hora de promoción. No registrar una hora independiente para app1 o app2 si no existe una marca temporal observada.

El objetivo RTO definido en Fase 1 debe compararse con el resultado observado y no debe declararse cumplido si el tiempo registrado lo supera.

### Resultado RTO/RPO observado en esta ejecución

- RPO objetivo de Fase 1: máximo 1 minuto de datos potencialmente perdidos.
- RPO de sincronización previa: `0 bytes` pendientes de sincronización en el punto comprobado. Este fue el resultado observado durante esta prueba; no constituye una garantía de pérdida cero en cualquier fallo futuro.
- RTO objetivo de Fase 1: recuperar la capacidad de escritura en un máximo de `300 segundos` (5 minutos).
- Recuperación efectiva confirmada del Gateway: respuesta HTTP `200` con marca `21:15:54 UTC` en el encabezado de respuesta, equivalente a `18:15:54 -03:00`.
- RTO desde el inicio de la interrupción `18:10:38.0610504 -03:00` hasta esa respuesta confirmada: `315.94 segundos` (aproximadamente `5 minutos 16 segundos`).
- El RTO observado supera el objetivo de `300 segundos` por `15.94 segundos`; el objetivo RTO no se cumplió en esta ejecución.
- La hora exacta de la promoción completada no quedó registrada en los registros disponibles y no se usarán estimaciones para calcular el RTO de promoción.
- app1 y app2 quedaron confirmadas como `healthy`; sin una marca temporal exacta independiente no se registra una hora distinta para la recuperación de cada aplicación.
- Este RTO corresponde a la recuperación confirmada del servicio Gateway y no representa una medición exacta de la recuperación interna de cada instancia.

## Recuperación del antiguo primario con pg_rewind

El antiguo `db-primary` debe permanecer detenido durante todo este proceso. La reincorporación es posterior a la recuperación de app1, app2 y Gateway.

### Confirmar que está detenido

```powershell
docker compose ps db-primary
docker inspect --format '{{.State.Status}}' bodega-db-primary
```

No ejecutar `docker compose exec` ni `pg_isready` mientras `db-primary` esté detenido. El estado del contenedor no implica que el servidor PostgreSQL esté disponible; solo después de confirmar `running` se puede comprobar su disponibilidad.

### Preparar credenciales sin mostrarlas

Extraer la contraseña necesaria en memoria desde `.env`. Las variables no se imprimen.

```powershell
$postgresPassword = (Get-Content '.env' |
  Where-Object { $_ -match '^POSTGRES_PASSWORD=' } |
  ForEach-Object { $_.Substring($_.IndexOf('=') + 1) })

$replicationPassword = (Get-Content '.env' |
  Where-Object { $_ -match '^REPLICATION_PASSWORD=' } |
  ForEach-Object { $_.Substring($_.IndexOf('=') + 1) })

if ([string]::IsNullOrWhiteSpace($postgresPassword) -or
    [string]::IsNullOrWhiteSpace($replicationPassword)) {
  throw 'POSTGRES_PASSWORD o REPLICATION_PASSWORD no están disponibles sin exponerlas.'
}
```

### Reconciliar divergencia con pg_rewind cuando corresponda

El volumen objetivo se monta de forma temporal en un contenedor PostgreSQL 16, sin detener ni borrar datos.
En esta ejecución el resultado observado fue `no rewind required`. No se exige ejecutar `pg_rewind` en todas las reincorporaciones: se utiliza cuando existe divergencia entre los timelines que requiere reconciliación. En todos los casos sí se exige que el antiguo primario vuelva correctamente como standby y que la replicación alcance `streaming`.

```powershell
docker run --rm `
  --network bodega-network `
  --user postgres `
  --env "PGPASSWORD=$postgresPassword" `
  --volume bodega-stock-api_db_primary_data:/var/lib/postgresql/data `
  postgres:16 `
  pg_rewind `
    --target-pgdata=/var/lib/postgresql/data `
    --source-server="host=db-replica port=5432 dbname=bodega user=bodega_admin" `
    --progress `
    --write-recovery-conf
```

Este comando no debe ejecutarse si `db-primary` sigue arrancado, si la fuente no aceptó la conexión o si `db-replica` no está confirmado como primario.

### Configurar el antiguo primario como réplica

El siguiente contenedor temporal escribe `standby.signal`, `.pgpass` y una única entrada `primary_conninfo` en el volumen de `db-primary`. No muestra contraseñas ni contenido de `.pgpass`.
El script POSIX se pasa desde PowerShell mediante un here-string literal, sin heredoc POSIX ni expansión local de `$REPLICATION_PASSWORD`:

```powershell
$configureReplica = @'
set -eu
touch /var/lib/postgresql/data/standby.signal
chmod 600 /var/lib/postgresql/data/standby.signal
sed -i "/^[[:space:]]*primary_conninfo[[:space:]]*=/d" /var/lib/postgresql/data/postgresql.auto.conf
escaped_password=$(printf '%s' "$REPLICATION_PASSWORD" | sed 's/\\/\\\\/g; s/:/\\:/g')
printf "db-replica:5432:*:bodega_replicator:%s\n" "$escaped_password" > /var/lib/postgresql/data/.pgpass
chmod 600 /var/lib/postgresql/data/.pgpass
printf "%s\n" "primary_conninfo = 'host=db-replica port=5432 user=bodega_replicator passfile=/var/lib/postgresql/data/.pgpass'" >> /var/lib/postgresql/data/postgresql.auto.conf
'@

docker run --rm `
  --network bodega-network `
  --user postgres `
  --env "REPLICATION_PASSWORD=$replicationPassword" `
  --volume bodega-stock-api_db_primary_data:/var/lib/postgresql/data `
  postgres:16 sh -c $configureReplica
```

Validar que exista exactamente una configuración válida de `primary_conninfo`, que no haya otra configuración adicional y que `standby.signal` exista, sin imprimir credenciales ni `.pgpass`:

```powershell
$validateReplica = @'
set -eu
file=/var/lib/postgresql/data/postgresql.auto.conf
total=$(awk '/^[[:space:]]*primary_conninfo[[:space:]]*=/ { count++ } END { print count + 0 }' "$file")
valid=$(awk '/^[[:space:]]*primary_conninfo[[:space:]]*=[[:space:]]*'\''host=db-replica[[:space:]]+port=5432[[:space:]]+user=bodega_replicator[[:space:]]+passfile=\/var\/lib\/postgresql\/data\/\.pgpass'\''[[:space:]]*$/ { count++ } END { print count + 0 }' "$file")
test "$total" -eq 1
test "$valid" -eq 1
test -f /var/lib/postgresql/data/standby.signal
echo "primary_conninfo=exactamente-una; standby.signal=presente"
'@

docker run --rm `
  --user postgres `
  --volume bodega-stock-api_db_primary_data:/var/lib/postgresql/data `
  postgres:16 sh -c $validateReplica
```

Si la validación falla por cero, por más de una entrada o por una entrada no válida, bloquear el procedimiento y no arrancar el antiguo primario.

### Arrancar el antiguo primario como standby

```powershell
docker compose ps db-primary
docker inspect --format '{{.State.Status}}' bodega-db-primary
docker compose up -d --no-deps db-primary
docker compose ps db-primary db-replica
```

### Comprobar el streaming en la nueva topología

```powershell
docker compose exec -T db-replica psql -U bodega_admin -d bodega -X -v ON_ERROR_STOP=1 -c `
  "SELECT pg_is_in_recovery() AS primary_in_recovery,
          application_name, state, sync_state, replay_lsn
   FROM pg_stat_replication;"

docker compose exec -T db-primary psql -U bodega_admin -d bodega -X -v ON_ERROR_STOP=1 -c `
  "SELECT pg_is_in_recovery() AS old_primary_in_recovery,
          status, sender_host, written_lsn, flushed_lsn, latest_end_lsn
   FROM pg_stat_wal_receiver;"
```

`pg_stat_wal_receiver` no tiene utilidad si no está en recuperación. El resultado esperado es:

- `db-replica`: `pg_is_in_recovery=false`.
- `db-primary`: `pg_is_in_recovery=true`.
- Emisor: estado `streaming`.
- Receptor: estado `streaming`.
- Host remitente del receptor: `db-replica`.

### Verificar integridad después de reunirse

```powershell
docker compose exec -T app1 python -c "import os, psycopg; from psycopg.conninfo import conninfo_to_dict; cfg=conninfo_to_dict(os.environ['DB_PRIMARY_URL']); p=psycopg.connect(**dict(cfg, host='db-primary')); r=psycopg.connect(**dict(cfg, host='db-replica')); pp=p.execute('SELECT row_to_json(t) FROM (SELECT * FROM productos ORDER BY id) AS t').fetchall(); rp=r.execute('SELECT row_to_json(t) FROM (SELECT * FROM productos ORDER BY id) AS t').fetchall(); pm=p.execute('SELECT row_to_json(t) FROM (SELECT * FROM movimientos ORDER BY id) AS t').fetchall(); rm=r.execute('SELECT row_to_json(t) FROM (SELECT * FROM movimientos ORDER BY id) AS t').fetchall(); print('productos_coinciden=', pp==rp); print('movimientos_coinciden=', pm==rm); p.close(); r.close()"
```

Esta comprobación abre conexiones explícitas a `db-primary` y `db-replica`, sin reemplazar texto dentro de una URL ni mostrar credenciales, y compara todos los registros y columnas de `productos` y `movimientos`, ordenados por `id`. No sustituye esta comparación por conteos.

## Verificaciones de split-brain y pérdida de conexión

### Detectar más de un primario

Si `db-primary` está detenido, primero verificar:

```powershell
docker compose ps db-primary db-replica
```

Si `docker compose ps` muestra `db-primary` detenido, no ejecutar SQL ni `pg_isready` dentro del contenedor.
Después de que el contenedor esté disponible, `pg_isready` será la primera comprobación:

```powershell
$primaryContainerStatus = docker inspect --format '{{.State.Status}}' bodega-db-primary
if ($primaryContainerStatus -ne 'running') {
  throw "db-primary está '$primaryContainerStatus'; no ejecutar docker compose exec."
}

docker compose exec -T db-primary pg_isready -U bodega_admin -d bodega
```

Solo si está disponible, ejecutar las consultas SQL:

```powershell
docker compose exec -T db-primary psql -U bodega_admin -d bodega -X -v ON_ERROR_STOP=1 -tAc `
  "SELECT pg_is_in_recovery();"

docker compose exec -T db-replica psql -U bodega_admin -d bodega -X -v ON_ERROR_STOP=1 -tAc `
  "SELECT pg_is_in_recovery();"
```

Split-brain confirmado si ambos servidores reportan `false`, o si ambos aceptan escrituras permanentes. Ante cualquier indicio:

- Detener de inmediato nuevas escrituras.
- Desconectar las aplicaciones de ambas bases.
- Mantener el antiguo primario detenido.
- No ejecutar `pg_rewind` sobre una base que puede haber sido escrita.
- Escalar la reversión y revisar el timeline antes de continuar.

### Detectar pérdida de replicación

Cuando `db-replica` fue promovido y `db-primary` volvió a arrancar como réplica, consultar el emisor en el nuevo primario:

```powershell
docker compose exec -T db-replica psql -U bodega_admin -d bodega -X -v ON_ERROR_STOP=1 -c `
  "SELECT application_name, client_addr, state, sync_state,
          sent_lsn, write_lsn, flush_lsn, replay_lsn
   FROM pg_stat_replication;"
```

Y consultar el receptor únicamente en el antiguo primario:

```powershell
docker compose exec -T db-primary psql -U bodega_admin -d bodega -X -v ON_ERROR_STOP=1 -c `
  "SELECT status, sender_host, sender_port,
          written_lsn, flushed_lsn, latest_end_lsn, latest_end_time
   FROM pg_stat_wal_receiver;"

docker compose exec -T db-primary psql -U bodega_admin -d bodega -X -v ON_ERROR_STOP=1 -c `
  "SELECT pg_is_in_recovery(), pg_last_wal_receive_lsn(),
          pg_last_wal_replay_lsn(), pg_last_xact_replay_timestamp(),
          pg_wal_replay_paused();"
```

Alertas inmediatas:

- `status` distinto de `streaming`.
- `sender_host` distinto de `db-replica`.
- `pg_is_in_recovery=false` en el antiguo `db-primary` después de iniciar.
- Ausencia de `pg_stat_wal_receiver`.
- Crecimiento sostenido de bytes pendientes.
- Errores de autenticación, timeline o WAL en los logs.

### Revisar logs

```powershell
docker compose logs --since 10m db-primary
docker compose logs --since 10m db-replica
docker compose logs --since 10m app1 app2 gateway load-balancer
```

## Criterios de seguridad y reversión

Detener la prueba si ocurre cualquiera de los siguientes casos:

- El respaldo pre-failover falla o no puede verificarse.
- La réplica no está en `streaming`.
- Los bytes pendientes no llegan a cero dentro de la ventana aprobada.
- `db-primary` no puede detenerse de forma limpia.
- `db-replica` no promueve o sigue en recovery.
- Se detectan dos servidores aceptando escritura.
- Se pierde el enlace a la réplica o a las aplicaciones.
- Falla el cambio de destinos de las aplicaciones.
- El antiguo primario no se reincorpora correctamente como standby.
- El antiguo primario vuelve a arrancar sin `standby.signal`.
- El receptor no pasa a `streaming`.
- Hay divergencia de datos o timeline que no pueda explicarse.

### Reversión antes de la promoción

Si la prueba falla antes de promover:

1. Mantener `db-primary`.
2. Verificar con `docker compose ps` que `db-primary` está disponible.
3. Consultar `pg_is_in_recovery()` en ambos servidores y exigir exactamente un servidor activo con `false` y otro con `true`.
4. Confirmar `pg_stat_replication` con estado `streaming` en `db-primary`.
5. Detener cualquier intento de promoción en `db-replica`.
6. Restaurar variables temporales `DB_PRIMARY_HOST=db-primary` y `DB_REPLICA_HOST=db-replica`.
7. Recrear aplicaciones y gateway sin iniciar dependencias:

```powershell
$env:DB_PRIMARY_HOST = 'db-primary'
$env:DB_REPLICA_HOST = 'db-replica'

docker compose up -d --no-deps --force-recreate app1 app2 gateway
docker compose ps app1 app2 gateway load-balancer db-primary db-replica
```

8. Verificar salud e integridad completa.

### Reversión después de la promoción

No reiniciar ni promocionar el antiguo primario sin completar la reconciliación requerida; ejecutar `pg_rewind` si existe divergencia. La reversión posterior requiere un procedimiento de failback aprobado, con decisión explícita sobre qué datos siguen existiendo en el nuevo primario.
Antes de autorizar una reversión, confirmar mediante `pg_is_in_recovery()` y `pg_stat_replication` que existe exactamente un único primario activo y ningún segundo servidor aceptando escrituras.

Una reversión segura debe definir primero:

- Qué servidor conservará datos adicionales.
- Si los cambios posteriores a la promoción deben estar presentes en el servidor restaurado.
- Cómo se repromoverá el servidor elegido.
- Si es necesario otro paso de `pg_rewind`.

No ejecutar ese failback reversible sin autorización.

### Comandos prohibidos

No ejecutar durante esta prueba:

- `docker compose down`
- `docker compose down -v`
- `docker compose rm -v`
- Cualquier `rm -rf`
- Eliminación de volúmenes o directorios.
- `pg_promote()`
- Escrituras permanentes no autorizadas.
- Modificación de `.env`.
- Modificación manual de destinos sin recrear aplicaciones.
- `pg_rewind` sobre un antiguo primario que sigue ejecutándose.

## Registro de resultados RPO/RTO

Completar en el momento real de la autorización y ejecución.

| Campo | Resultado observado |
|---|---|
| Fecha y hora de preparación | 18 de noviembre de 2026, antes de `18:10:38 -03:00` |
| LSN de fuente antes de detener escrituras | Observado inicialmente en `0/30C8678` y sincronizado al ejecutar la promoción |
| LSN de réplica antes de detener escrituras | `0/30C8678` |
| Diferencia en bytes | `0 bytes` |
| Timestamp de último replay observado | No quedó registrado con precisión temporal adicional |
| Hora de inicio de detención de escrituras | `18:10:38.0610504 -03:00` |
| Hora de detención de `db-primary` | `18:13:24.2667926 -03:00` |
| Hora de inicio de promoción | `18:14:31.4471380 -03:00` |
| Hora de promoción confirmada | Completada; hora exacta no registrada |
| Hora en que `db-replica` aceptó escritura | Confirmada por promoción; hora exacta no registrada |
| Hora en que gateway y aplicaciones respondieron | Gateway confirmado con HTTP 200 a las `18:15:54 -03:00`; apps confirmadas saludables sin hora exacta independiente |
| RPO de bytes observado | `0 bytes` |
| RPO temporal observado | Aproximado/no inferido con exactitud a partir de timestamps |
| RTO desde la parada del primario hasta la promoción | Hora exacta de promoción pendiente |
| RTO desde el inicio de la interrupción hasta el servicio recuperado | `315.94 segundos` hasta el HTTP 200 confirmado del Gateway |
| Resultado de `pg_rewind` | `no rewind required` |
| Estado final de `db-primary` | Standby activo; `pg_is_in_recovery=true`; receptor `streaming` |
| Estado final de `db-replica` | Primario activo; `pg_is_in_recovery=false`; emisor `streaming` |

Los valores anteriores son observaciones reales de esta ejecución. El RPO observado fue de `0 bytes` pendientes en el punto comprobado y el objetivo RTO no se cumplió en esta ejecución.
