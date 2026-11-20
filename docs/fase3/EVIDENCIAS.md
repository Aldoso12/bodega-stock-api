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

Durante la validación inicial de la arquitectura, antes de ejecutar el failover, los seis servicios (`gateway`, `load-balancer`, `app1`, `app2`, `db-primary` y `db-replica`) finalizaron en estado `healthy`.

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

## 9. Prueba real de failover

### Inicio y sincronización

- Inicio de interrupción: `18:10:38.0610504 -03:00`.
- Antes de detener la primaria, la diferencia WAL observada fue `0 bytes`.
- `db-primary` fue detenido y el estado fue confirmado como contenedor detenido a las `18:13:24.2667926 -03:00`.

### Promoción

- Promoción de `db-replica` iniciada a las `18:14:31.4471380 -03:00`.
- El proceso informó `server promoted`.
- `db-replica` finalizó con `pg_is_in_recovery=false` y timeline 2.
- No se hizo ninguna escritura de prueba ni POST durante el failover.

### Recuperación del servicio

- app1, app2 y Gateway fueron recreados con ambos destinos apuntando temporalmente a `db-replica`.
- Las tres instancias quedaron saludables.
- GET autenticado al Gateway: HTTP `200`.
- Lectura atendida por app2.
- Un `Date: 21:15:54 GMT` observado en la respuesta HTTP corresponde a `18:15:54 -03:00`.
- Desde el inicio de la interrupción hasta esa respuesta confirmada transcurrieron `315.94 segundos`, aproximadamente `5 minutos 16 segundos`.

No existe una hora exacta independiente registrada para la recuperación de cada aplicación; por ello, no se asignan tiempos adicionales inventados.

## 10. Reincorporación de db-primary

- `pg_rewind` informó `no rewind required`; no se ejecutaron nuevas operaciones de rewind.
- Se corrigió la autenticación de `bodega_replicator` usando la contraseña de la configuración existente.
- `.pgpass` quedó con permisos `600` y propietario PostgreSQL.
- `standby.signal` permanece presente.
- `primary_conninfo` apunta de forma única a `db-replica`.
- `db-replica` confirma `pg_is_in_recovery=false`.
- `db-primary` confirma `pg_is_in_recovery=true`.
- `pg_stat_replication` en `db-replica`: estado `streaming`.
- `pg_stat_wal_receiver` en `db-primary`: estado `streaming`, origen `db-replica`.
- Posición WAL observada en ambos nodos: `0/30CA8D0`.
- Comparación completa sin modificar datos:
  - Todos los registros de `productos` coinciden.
  - Todos los registros de `movimientos` coinciden.

## 11. Resumen de RPO y RTO

- RPO objetivo de Fase 1: máximo 1 minuto de datos potencialmente perdidos.
- RPO observado: `0 bytes` pendientes de sincronización en la comprobación previa a la interrupción. Este resultado corresponde a esta ejecución y no garantiza pérdida cero ante cualquier fallo.
- RTO objetivo de Fase 1: recuperar la capacidad de escritura en un máximo de `300 segundos` (5 minutos).
- RTO observado: `315.94 segundos` desde el inicio de la interrupción hasta una respuesta HTTP 200 del Gateway.
- El RTO observado supera el objetivo de `300 segundos` por `15.94 segundos`; el objetivo RTO no se cumplió en esta ejecución.
- La hora exacta de promoción completada no fue registrada y no se presenta como RTO completo.

## Conclusión

Las pruebas funcionales y la prueba real de failover fueron comprobadas. La reincorporación terminó correctamente y la topología final quedó formada por `db-replica` como único primario y `db-primary` como standby con replicación `streaming`.