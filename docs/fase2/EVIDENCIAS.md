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
    -H "X-API-Key: $env:BODEGA_API_KEY" `
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
  -H "X-API-Key: $env:BODEGA_API_KEY" `
  http://127.0.0.1:8080/

curl.exe --max-time 3 -sS -o NUL -w "missing_status=%{http_code}`n" `
  http://127.0.0.1:8080/

curl.exe --max-time 3 -sS -o NUL -w "wrong_status=%{http_code}`n" `
  -H "X-API-Key: clave-no-valida" `
  http://127.0.0.1:8080/
```

### Salida obtenida

```text
valid_status=200
missing_status=401
wrong_status=401
```

La solicitud con la clave correcta utilizó la clave configurada mediante la variable de entorno
`BODEGA_API_KEY`; su valor no se documenta. La solicitud con `clave-no-valida` utilizó un
valor deliberadamente incorrecto y no corresponde a ninguna credencial real.

Además, la respuesta autorizada incluyó un encabezado `X-Instance`, por ejemplo:

```text
HTTP/1.0 200 OK
X-Instance: app-2
```

### Resultado

La prueba fue satisfactoria. El gateway protege la entrada pública con la API Key y conserva el encabezado de identificación enviado por el balanceador.

## 4. Replicación de PostgreSQL (12 de noviembre de 2026)

### Objetivo

Comprobar que la primaria acepta una escritura y que el registro se replica correctamente en la
réplica. La prueba se realizó en la base de datos `bodega` con el usuario `bodega_admin`.

### Comandos utilizados

```powershell
docker compose --env-file .env.example exec -T db-primary `
  psql -U bodega_admin -d bodega -c `
  "CREATE TABLE prueba_replicacion (id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY, mensaje text NOT NULL); INSERT INTO prueba_replicacion (mensaje) VALUES ('Prueba de replicacion Bodega Express');"

docker compose --env-file .env.example exec -T db-replica `
  psql -U bodega_admin -d bodega -tAc `
  "SELECT id, mensaje FROM prueba_replicacion;"
```

### Salida obtenida

```text
CREATE TABLE
INSERT 0 1
1 | Prueba de replicacion Bodega Express
```

### Resultado

La prueba fue satisfactoria. La primaria creó la tabla `prueba_replicacion` e insertó un registro.
El mismo registro apareció correctamente en la réplica con ID 1. Esto demuestra que la réplica
recibe las escrituras realizadas en la primaria.

## 5. Prueba de caída de una instancia

### Objetivo

Comprobar que, al detener temporalmente `app1`, el balanceador continúa atendiendo las peticiones mediante `app2`.

### Comandos utilizados

```powershell
docker compose --env-file .env.example stop app1

1..6 | ForEach-Object {
  curl.exe --max-time 5 -sS -D - -o NUL `
    -H "X-API-Key: $env:BODEGA_API_KEY" `
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

## 6. Tolerancia a fallos con `app2` (12 de noviembre de 2026)

### Objetivo

Comprobar que, al detener temporalmente `app2`, el balanceador continúa atendiendo las
peticiones mediante `app-1` y que todos los servicios vuelven a quedar saludables después de
restaurarla.

### Comandos utilizados

```powershell
docker compose stop app2

1..5 | ForEach-Object {
  curl.exe --max-time 5 -sS -D - -o NUL `
    -H "X-API-Key: $env:BODEGA_API_KEY" `
    http://127.0.0.1:8080/ |
    Select-String -Pattern "^HTTP/|^X-Instance:"
}

docker compose start app2
docker compose ps
```

### Salida obtenida

Las cinco solicitudes respondieron HTTP 200 y mostraron el encabezado:

```text
HTTP/1.0 200 OK
X-Instance: app-1
```

Posteriormente, `app2` se inició con `docker compose start app2`. Se comprobó que los seis
servicios terminaron en estado `healthy`.

### Resultado

La prueba fue satisfactoria. Mientras `app2` estaba detenida, el Gateway continuó atendiendo
las cinco solicitudes mediante `app-1`, sin errores HTTP. Tras iniciar `app2`, los seis servicios
quedaron en estado `healthy`.
