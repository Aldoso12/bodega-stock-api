# Evidencias de la Fase 3

Las siguientes evidencias corresponden a las pruebas de integración de Bodega Express realizadas mediante Docker Compose en el entorno local.

## 0. Validación reciente del 20 de noviembre de 2026

Esta validación es posterior a las pruebas históricas y al failover documentado. No reemplaza
los resultados anteriores.

- `docker compose config --quiet` validó correctamente la configuración.
- Los seis contenedores principales (`db-primary`, `db-replica`, `app1`, `app2`,
  `load-balancer` y `gateway`) aparecieron en estado `healthy`.
- El Gateway respondió HTTP `200` en `/health` con el cuerpo `gateway-ok`.
- Se realizaron seis solicitudes autenticadas a través del Gateway; se alternaron correctamente
  entre `app-1` y `app-2`.
- `/health/db` respondió HTTP `200`, indicando que la conexión con la primaria estaba disponible.
- Las cuatro solicitudes a `/health/db` devolvieron HTTP `200`.
- Se consultó un producto de prueba con ID `39` y código `TEST-20261120-000854`.
- El producto permanece registrado en la base de datos.
- La consulta del producto ID `39` respondió HTTP `200` con `X-DB: replica`.
- La escritura respondió HTTP `201` con `X-DB: primary`.
- La lectura posterior respondió HTTP `200` con `X-DB: replica`.

### Escritura y lectura posterior del producto ID 42

Como parte de esta validación se creó un producto distinto mediante `POST /productos`:

- Código HTTP: `201`.
- Encabezado `X-DB`: `primary`.
- Encabezado `X-Instance`: `app-1`.
- Identificador generado: `42`.
- Código: `TEST-20261120-014500`.

La lectura posterior mediante `GET /productos/42` respondió:

- Código HTTP: `200`.
- Encabezado `X-DB`: `replica`.
- Encabezado `X-Instance`: `app-2`.
- Los datos coincidieron con los devueltos por el `POST`.

Esta comprobación confirma la separación de operaciones observada: la escritura fue atendida
por la primaria y la lectura posterior fue atendida por la réplica. No mide un tiempo exacto
de replicación ni constituye un experimento de falla. Los experimentos históricos de caída,
pérdida de disponibilidad o retraso de reproducción se documentan por separado.

En la configuración actual validada, app1 y app2 escriben en la primaria actual `db-replica` y
leen desde la réplica actual `db-primary`. Durante la recuperación del failover histórico ambos
destinos apuntaron temporalmente a `db-replica`; esa situación no debe confundirse con la
configuración actual.

La configuración efectiva utilizada en esta validación corresponde al archivo `.env` local y no
se reproduce ni se muestran sus valores. La plantilla [`.env.example`](../../.env.example)
conserva los destinos de la topología inicial (`db-primary` y `db-replica`); no representa por
sí sola la configuración actual posterior al failover.

## Prueba de rendimiento del 20 de noviembre de 2026

Las pruebas de rendimiento utilizaron únicamente solicitudes GET autenticadas a
`http://127.0.0.1:8080/productos` y no realizaron POST, SQL, cambios de datos, detenciones,
reinicios ni reconstrucciones.

La configuración activa utilizada fue `RATE_LIMIT_REQUESTS=300` con una ventana de
`RATE_LIMIT_WINDOW_SECONDS=60`. Cada prueba contó con una ventana limpia esperada de `61 segundos`
antes de comenzar.

### Prueba histórica inicial con límite 60/60

Se ejecutaron cinco solicitudes de comprobación mediante Python estándar, con timeout individual
de 5 segundos y deadline global de 30 segundos:

- Solicitudes completadas: `5`.
- HTTP `200`: `5`.
- Errores HTTP: `0`.
- Porcentaje de éxito: `100%`.
- Duración total: `0,17 segundos`.
- Latencia promedio: `34,12 ms`.
- Latencia mínima: `14,74 ms`.
- Latencia máxima: `77,68 ms`.
- Solicitudes menores de `500 ms`: `100%`.

### Carga histórica con límite 60/60

Se completaron `100` solicitudes espaciadas aproximadamente cada `200 ms` durante `19,8 segundos`,
lo que representa una carga objetivo de `5 solicitudes por segundo`.

- HTTP `200`: `60`.
- HTTP `429`: `40`.
- Errores totales: `40`.
- Porcentaje de éxito: `60%`.
- Latencia promedio: `17,57 ms`.
- Latencia mínima: `2,97 ms`.
- Latencia máxima: `64,37 ms`.
- Solicitudes menores de `500 ms`: `100%`.
- La prueba terminó completa: se calcularon los resultados con las `100` solicitudes completadas.

Los HTTP `429` fueron producidos por el límite configurado del Gateway. Esta prueba no demuestra
cumplimiento sostenido de `5 solicitudes por segundo`, aunque las respuestas completadas estuvieron
por debajo de `500 ms`.

### Concurrencia histórica con límite 60/60

Se realizaron `20` solicitudes GET simultáneas, una por usuario, mediante un pool de 20 trabajos,
con timeout individual de `5 segundos` y deadline global de `30 segundos`.

- Solicitudes completadas: `20`.
- HTTP `200`: `0`.
- HTTP `429`: `20`.
- Porcentaje de éxito: `0%`.
- Latencia promedio: `42,84 ms`.
- Latencia mínima: `10,09 ms`.
- Latencia máxima: `125,36 ms`.
- Solicitudes menores de `500 ms`: `100%`.

Las respuestas HTTP `429` ocurrieron dentro del límite vigente del Gateway. Por tanto, la prueba
no demuestra cumplimiento de 20 usuarios concurrentes.

### Validación posterior con límite 300/60

Después de recrear únicamente el Gateway y confirmar `RATE_LIMIT_REQUESTS=300` con una ventana
de `60 segundos`, se realizó una segunda validación separada por una espera de `61 segundos`
antes de cada prueba.

#### Autenticación

- Sin API Key: HTTP `401`.
- API Key inválida: HTTP `401`.
- API Key válida: HTTP `200`.

#### Carga nominal de cinco solicitudes por segundo

Se ejecutaron `100` solicitudes GET espaciadas aproximadamente cada `200 ms` durante
`19,82 segundos`:

- HTTP `200`: `100`.
- HTTP `429`: `0`.
- Errores totales: `0`.
- Porcentaje de éxito: `100%`.
- Latencia promedio: `21,91 ms`.
- Latencia mínima: `15,69 ms`.
- Latencia máxima: `48,14 ms`.
- Solicitudes menores de `500 ms`: `100%`.
- Resultado: la carga nominal de `5 solicitudes por segundo` quedó comprobada en esta ejecución
  de `100 solicitudes durante aproximadamente 20 segundos`.

#### Concurrencia con veinte usuarios

Se ejecutaron `20` solicitudes GET simultáneas con timeout individual de `5 segundos` y deadline
global de `30 segundos`:

- HTTP `200`: `20`.
- HTTP `429`: `0`.
- Porcentaje de éxito: `100%`.
- Latencia promedio: `84,26 ms`.
- Latencia mínima: `28,63 ms`.
- Latencia máxima: `192,94 ms`.
- Solicitudes menores de `500 ms`: `100%`.
- Resultado: esta ejecución comprobó la continuidad de `20 solicitudes concurrentes` bajo el
  límite configurado de `300/60`; no representa una prueba prolongada de carga continua.

### Comandos utilizados

Las pruebas se ejecutaron con Python estándar disponible en el equipo, sin instalar paquetes.
La clave de API se obtuvo exclusivamente en memoria desde `.env` y no se mostró.

```powershell
python -c "import pathlib,time,urllib.request,urllib.error; env=dict(line.split('=',1) for line in pathlib.Path('.env').read_text().splitlines() if '=' in line and not line.startswith('#')); key=env['API_KEY'].strip().strip(chr(34)).strip(chr(39))"
```

La prueba de cinco solicitudes cerró con cinco respuestas completas. La carga de cinco solicitudes
por segundo utilizó un bucle de `100` intentos separados por `0,2 segundos` y timeout de `5 segundos`
por solicitud. La prueba concurrente utilizó `ThreadPoolExecutor(max_workers=20)` y una espera
máxima global de `30 segundos`.

## 1. Estado de los servicios

### Objetivo

Comprobar que los seis servicios de la arquitectura se encuentran funcionando correctamente.

### Comando utilizado

```powershell
docker compose ps
```

### Resultado

Durante la validación inicial de la arquitectura, antes de ejecutar el failover, los seis servicios (`gateway`, `load-balancer`, `app1`, `app2`, `db-primary` y `db-replica`) finalizaron en estado `healthy`.

Solo `gateway` publica el puerto `8080` hacia el equipo anfitrión. `load-balancer` y las dos
instancias de aplicación permanecen dentro de la red Docker y no publican puertos al host.
Nginx configura un upstream separado con `app1` y `app2`, por lo que ambas instancias quedan
detrás del balanceador.

## 2. Autenticación mediante API Key

### Objetivo

Comprobar que el Gateway protege las rutas reenviadas con API Key y que acepta o rechaza
solicitudes según su autenticación.

### Resultado obtenido

| Solicitud | Código HTTP |
|---|---:|
| Sin API Key | 401 |
| Con API Key válida | 200 |

La clave se obtuvo desde el archivo `.env` y no se incluye su valor en este documento.
Una solicitud sin clave o con clave inválida fue rechazada por el Gateway antes de reenviarla al
balanceador. Una solicitud protegida con la API Key válida fue aceptada y continuó hacia la
arquitectura de aplicación.

Esta comprobación separa la autenticación del enrutamiento: el Gateway valida primero la clave
y, cuando la solicitud es aceptada, reenvía el método y la ruta original al balanceador.

## 3. Balanceo entre instancias

### Objetivo

Comprobar el enrutamiento de solicitudes autorizadas por el Gateway hacia el balanceador y
su distribución entre las dos instancias de la aplicación.

### Resultado obtenido

Se realizaron ocho solicitudes GET a través del Gateway:

| Instancia | Solicitudes |
|---|---:|
| app-1 | 4 |
| app-2 | 4 |

Todas respondieron HTTP 200 y fueron identificadas mediante el encabezado `X-Instance`.

El Gateway reenvía las rutas protegidas al componente `load-balancer`; las solicitudes
observadas llegaron a `/productos` o al producto relacionado y conservaron el encabezado
`X-Instance` generado por la aplicación atendida. Los resultados confirman el enrutamiento
completo `Gateway -> load-balancer -> app1/app2`.

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

## 9. Segundo experimento: retraso de actualización de la réplica

### Objetivo

Comprobar cómo responde la aplicación cuando la réplica de lectura deja de reproducir
temporalmente las nuevas escrituras.

### Ejecución del 20 de noviembre de 2026

La primaria actual era `db-replica` y la réplica de lectura era `db-primary`. Se comprobó que
la réplica estaba sincronizada antes de iniciar el experimento.

No se realizó un corte de red entre las bases de datos. Se pausó temporalmente la reproducción
WAL en `db-primary` mediante `pg_wal_replay_pause()` y se confirmó que la pausa estaba activa.

Durante la pausa se creó el siguiente producto en la primaria:

| Campo | Resultado |
|---|---|
| ID | `41` |
| Código | `EXP-STALE-20261120-004232` |
| POST | HTTP `201` |
| Base informada | `X-DB: primary` |

Una consulta posterior desde la aplicación devolvió:

| Campo | Resultado |
|---|---|
| GET | HTTP `404` |
| Base informada | `X-DB: replica` |
| Mensaje | `{"error":"Producto no encontrado"}` |

El resultado demuestra que la aplicación consultó una réplica disponible, pero todavía
desactualizada respecto de la primaria. El producto ya existía en `db-replica`, pero aún no
estaba visible en `db-primary`.

Posteriormente se reanudó la reproducción WAL mediante `pg_wal_replay_resume()`. Se confirmó
que la pausa había terminado y que la conexión de replicación continuaba en estado `streaming`.
Una nueva consulta `GET` respondió HTTP `200` desde la réplica y mostró correctamente el
producto ID `41`.

### Duración registrada y limitaciones

- Tiempo total desde el inicio de la preparación hasta la consulta recuperada:
  `188,84 segundos`.
- Este tiempo no representa la duración exacta de la pausa.
- Tampoco representa el tiempo exacto de recuperación o catch-up de la réplica.
- La pausa superó el límite recomendado de `60 segundos`, pero su duración exacta no fue medida.
- La aplicación no resolvió automáticamente la lectura desactualizada: durante el retraso
  devolvió HTTP `404`, y solo después de la reproducción WAL el mismo `GET` devolvió HTTP `200`.

### Aprendizaje

La replicación asíncrona permite que una escritura confirmada en la primaria no esté disponible
inmediatamente en la réplica. Pausar la reproducción WAL permitió observar esta ventana de
inconsistencia de lectura sin detener PostgreSQL ni ejecutar una promoción. Este resultado no
debe describirse como una desconexión de red.

## 10. Prueba real de failover

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

## 11. Reincorporación de db-primary

- `pg_rewind` informó `no rewind required`; no se ejecutaron nuevas operaciones de rewind.
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

## 12. Resumen de RPO y RTO

- RPO objetivo de Fase 1: máximo 1 minuto de datos potencialmente perdidos.
- RPO observado: `0 bytes` pendientes de sincronización en la comprobación previa a la interrupción. Este resultado corresponde a esta ejecución y no garantiza pérdida cero ante cualquier fallo.
- RTO objetivo de Fase 1: recuperar la capacidad de escritura en un máximo de `300 segundos` (5 minutos).
- RTO observado: `315.94 segundos` desde el inicio de la interrupción hasta una respuesta HTTP 200 del Gateway.
- El RTO observado supera el objetivo de `300 segundos` por `15.94 segundos`; el objetivo RTO no se cumplió en esta ejecución.
- La hora exacta de promoción completada no fue registrada y no se presenta como RTO completo.

## 13. Aprendizajes, limitaciones y pendientes

- El RPO observado fue de `0 bytes` pendientes en el punto comprobado. Es un resultado de esa
  ejecución y no una garantía universal de pérdida cero.
- El RTO observado fue de `315,94 segundos`, superando el objetivo de `300 segundos` por
  `15,94 segundos`. El objetivo RTO no se cumplió en esa ejecución.
- La replicación es asíncrona; una lectura inmediatamente posterior a una escritura puede
  consultar una réplica que todavía no haya reproducido el cambio.
- La recuperación confirmada corresponde a una respuesta HTTP `200` del Gateway. No se registró
  una hora independiente de recuperación para cada aplicación.
- El segundo experimento ejecutado el 20 de noviembre comprobó un retraso de reproducción WAL,
  no una pérdida de comunicación de red con la réplica.
- La pausa superó el límite recomendado de `60 segundos` y no se midió su duración exacta.
- El tiempo total registrado fue de `188,84 segundos`, pero no representa el tiempo exacto de
  recuperación o catch-up de la réplica.

## Conclusión

Las pruebas funcionales y la prueba real de failover fueron comprobadas. La reincorporación terminó correctamente y la topología final quedó formada por `db-replica` como único primario y `db-primary` como standby con replicación `streaming`.