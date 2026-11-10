# Evidencias de la Fase 2

Las siguientes evidencias corresponden a las pruebas ejecutadas con Docker Compose en el entorno local.

## 1. Entrada por el gateway

### Objetivo

Comprobar que el gateway es la única entrada publicada y que las aplicaciones y el balanceador no exponen puertos directamente al equipo anfitrión.

### Comando utilizado

```powershell
docker compose --env-file .env.example ps
docker port bodega-gateway
docker port bodega-load-balancer
docker port bodega-app-1
docker port bodega-app-2
```

### Salida obtenida

```text
bodega-gateway ... Up ... 0.0.0.0:8080->8080/tcp
bodega-load-balancer ... Up ... 80/tcp
bodega-app-1 ... Up ... 8000/tcp
bodega-app-2 ... Up ... 8000/tcp

8080/tcp -> 0.0.0.0:8080
8080/tcp -> [::]:8080
```

`docker port` no devolvió líneas para `bodega-load-balancer`, `bodega-app-1` ni `bodega-app-2`.

### Resultado

La prueba fue satisfactoria. Solo el gateway publica el puerto del equipo anfitrión. El balanceador y las instancias permanecen accesibles dentro de la red Docker.

## 2. Balanceo entre instancias mediante `X-Instance`

### Objetivo

Comprobar que las peticiones autorizadas que llegan al gateway se reenvían al balanceador y se distribuyen entre `app-1` y `app-2`.

### Comando utilizado

```powershell
for ($i=1; $i -le 6; $i++) {
  Write-Output "--- request $i ---"
  curl.exe --max-time 5 -sS -D - -o NUL `
    -H "X-API-Key: change_me_gateway" `
    http://127.0.0.1:8080/ |
    Select-String -Pattern "^HTTP/|^X-Instance:"
}
```

### Salida obtenida

```text
--- request 1 ---
HTTP/1.0 200 OK
X-Instance: app-2
--- request 2 ---
HTTP/1.0 200 OK
X-Instance: app-1
--- request 3 ---
HTTP/1.0 200 OK
X-Instance: app-2
--- request 4 ---
HTTP/1.0 200 OK
X-Instance: app-1
--- request 5 ---
HTTP/1.0 200 OK
X-Instance: app-2
--- request 6 ---
HTTP/1.0 200 OK
X-Instance: app-1
```

### Resultado

La prueba fue satisfactoria. Nginx alternó las respuestas entre ambas instancias y el encabezado `X-Instance` identificó correctamente cada una.

## 3. Autenticación mediante API Key

### Objetivo

Comprobar que el gateway permite una petición con la API Key configurada y rechaza peticiones sin clave o con una clave incorrecta.

### Comandos utilizados

```powershell
curl.exe --max-time 3 -sS -o NUL -w "valid_status=%{http_code}`n" `
  -H "X-API-Key: change_me_gateway" `
  http://127.0.0.1:8080/

curl.exe --max-time 3 -sS -o NUL -w "missing_status=%{http_code}`n" `
  http://127.0.0.1:8080/

curl.exe --max-time 3 -sS -o NUL -w "wrong_status=%{http_code}`n" `
  -H "X-API-Key: wrong-key" `
  http://127.0.0.1:8080/
```

### Salida obtenida

```text
valid_status=200
missing_status=401
wrong_status=401
```

Además, la respuesta autorizada incluyó un encabezado `X-Instance`, por ejemplo:

```text
HTTP/1.0 200 OK
X-Instance: app-2
```

### Resultado

La prueba fue satisfactoria. El gateway protege la entrada pública con la API Key y conserva el encabezado de identificación enviado por el balanceador.

## 4. Replicación de PostgreSQL

### Objetivo

Comprobar mediante consultas SQL que la primaria acepta una escritura, que la réplica está en recuperación y que el dato escrito aparece en ella.

### Comandos utilizados

```powershell
docker compose --env-file .env.example exec -T db-primary `
  psql -U bodega_admin -d bodega -c `
  "CREATE TABLE IF NOT EXISTS replication_check (id integer PRIMARY KEY, message text NOT NULL); INSERT INTO replication_check (id, message) VALUES (1, 'streaming-ok') ON CONFLICT (id) DO UPDATE SET message = EXCLUDED.message;"

docker compose --env-file .env.example exec -T db-replica `
  psql -U bodega_admin -d bodega -tAc `
  "SELECT pg_is_in_recovery();"

docker compose --env-file .env.example exec -T db-replica `
  psql -U bodega_admin -d bodega -tAc `
  "SELECT id || ':' || message FROM replication_check WHERE id = 1;"

docker compose --env-file .env.example exec -T db-primary `
  psql -U bodega_admin -d bodega -tAc `
  "SELECT state FROM pg_stat_replication LIMIT 1;"
```

### Salida obtenida

```text
CREATE TABLE
INSERT 0 1
t
1:streaming-ok
streaming
```

### Resultado

La prueba fue satisfactoria. La primaria aceptó la escritura, la réplica reportó `pg_is_in_recovery() = t`, el dato apareció en la réplica y la primaria reportó el estado `streaming`.

## 5. Prueba de caída de una instancia

### Objetivo

Comprobar que, al detener temporalmente `app1`, el balanceador continúa atendiendo las peticiones mediante `app2`.

### Comandos utilizados

```powershell
docker compose --env-file .env.example stop app1

1..6 | ForEach-Object {
  curl.exe --max-time 5 -sS -D - -o NUL `
    -H "X-API-Key: change_me_gateway" `
    http://127.0.0.1:8080/ |
    Select-String -Pattern "^HTTP/|^X-Instance:"
}

docker compose --env-file .env.example start app1
docker compose --env-file .env.example ps
```

### Salida obtenida

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

Posteriormente, `app1` fue restaurada mediante `docker compose start app1`.

### Resultado

La prueba fue satisfactoria. Las seis peticiones respondieron HTTP 200 y fueron atendidas por `app-2`, identificado mediante el encabezado `X-Instance`, mientras `app1` estaba detenida. Luego `app1` volvió a levantarse correctamente.
