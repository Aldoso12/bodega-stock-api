# Evidencias de la Fase 3

Las siguientes evidencias corresponden a las pruebas de integración de Bodega Express realizadas mediante Docker Compose en el entorno local.

## 1. Estado de los servicios

### Objetivo

Comprobar que los seis servicios de la arquitectura se encuentran funcionando correctamente.

### Comando utilizado

```powershell
docker compose ps
```

### Resultado

Los seis servicios (`gateway`, `load-balancer`, `app1`, `app2`, `db-primary` y `db-replica`) finalizaron en estado `healthy`.

## 2. Autenticación mediante API Key

### Objetivo

Comprobar que el Gateway rechaza las solicitudes sin una API Key válida.

### Resultado obtenido

| Solicitud | Código HTTP |
|---|---:|
| Sin API Key | 401 |
| Con API Key válida | 200 |

La clave se obtuvo desde el archivo `.env` y no se incluye su valor en este documento.

## 3. Balanceo entre instancias

### Objetivo

Comprobar que las solicitudes autorizadas se distribuyen entre las dos instancias de la aplicación.

### Resultado obtenido

Se realizaron ocho solicitudes GET a través del Gateway:

| Instancia | Solicitudes |
|---|---:|
| app-1 | 4 |
| app-2 | 4 |

Todas respondieron HTTP 200 y fueron identificadas mediante el encabezado `X-Instance`.

## 4. Escritura en la base de datos primaria

### Objetivo

Comprobar que las operaciones POST se procesan mediante la base de datos primaria.

### Resultado obtenido

Se registró un producto de prueba a través del Gateway.

- Código HTTP: `201 Created`.
- Encabezado `X-DB`: `primary`.
- Identificador generado: `6`.
- Producto: `FASE3-GATEWAY-001`.

## 5. Lectura desde la réplica

### Objetivo

Comprobar que los registros escritos en la primaria pueden consultarse desde la réplica.

### Resultado obtenido

Se consultó el producto registrado anteriormente.

- Código HTTP: `200 OK`.
- Encabezado `X-DB`: `replica`.
- Producto encontrado: `FASE3-GATEWAY-001`.
- Stock consultado: `5`.

La consulta confirmó que el registro estaba disponible en la réplica.

## 6. Control de solicitudes (Rate Limiting)

### Objetivo

Comprobar que el Gateway limita la cantidad de solicitudes permitidas durante una ventana de tiempo.

### Resultado obtenido

Se realizaron 65 solicitudes consecutivas:

| Respuesta | Cantidad |
|---|---:|
| HTTP 200 | 60 |
| HTTP 429 | 5 |

El resultado coincide con el límite configurado de 60 solicitudes por minuto.

## 7. Restricción de métodos HTTP

### Objetivo

Comprobar que el Gateway rechaza métodos HTTP que no están permitidos.

### Resultado obtenido

Se realizó una solicitud DELETE:

- Código HTTP: `405 Method Not Allowed`.
- Encabezado `Allow`: `GET, POST`.

La solicitud fue rechazada y el producto de prueba no fue eliminado.

## 8. Restricción del tamaño de las solicitudes

### Objetivo

Comprobar que el Gateway rechaza solicitudes cuyo cuerpo supera el tamaño máximo permitido.

### Resultado obtenido

Se envió una solicitud de 1.048.588 bytes.

- Código HTTP: `413 Content Too Large`.
- La solicitud fue rechazada por superar el límite de 1 MiB.

## Conclusión

Las pruebas realizadas permitieron comprobar el funcionamiento del Gateway, la autenticación mediante API Key, el balanceo entre instancias, el control de solicitudes y la separación entre lecturas y escrituras de las bases de datos.

Las pruebas de tolerancia a fallos de las bases de datos y las mediciones de RPO/RTO quedan pendientes para la siguiente jornada de trabajo.