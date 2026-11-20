# Bitácora de Proyecto - ISI601

## Miércoles 4 de Noviembre
* **Qué hice hoy:** Creación del repositorio en GitHub, configuración de la estructura inicial de carpetas y redacción de la problemática de la bodega en `docs/fase1/PROBLEMA.md`.
* **Dónde me trabé:** Ninguna traba con la estructura inicial.
* **Qué haré la próxima clase:** Avanzar con los requisitos funcionales, no funcionales y la estimación de carga a 5 años.
* **Uso de IA:** Se utilizó IA para estructurar los puntos clave de la problemática de la bodega según los requisitos del taller.

## Jueves 5 de Noviembre
- **Qué hice hoy:** Elaboración de los requisitos funcionales y no funcionales, junto con la estimación de carga del sistema Bodega Express a cinco años.
- **Dónde me trabé:** Sin dificultades importantes durante la elaboración de los requisitos y cálculos.
- **Qué haré la próxima clase:** Elaborar y revisar los diagramas lógico y físico de la arquitectura.
- **Uso de IA:** Se utilizó IA para estructurar los requisitos y apoyar los cálculos de estimación. Se revisó el contenido y se adaptó al proyecto.

## Viernes 6 de Noviembre de 2026
- **Qué hice hoy:** Elaboración de los diagramas lógico y físico de la arquitectura y exportación de ambos a formato PNG.
- **Archivos y organización:** Se conservaron los archivos editables en formato Draw.io y se organizaron los cuatro archivos dentro de `docs/fase1/`, quedando posteriormente visibles en el repositorio de GitHub.

## Miércoles 11 de Noviembre de 2026
- **Qué hice hoy:** Cierre y entrega de la Fase 1, con la finalización de `docs/fase1/REQUISITOS.md` —incluyendo la estimación de carga y almacenamiento— y la creación y revisión de `docs/fase1/DISENO.md`.
- **Archivos y organización:** Se revisaron los diagramas lógico y físico en PNG y Draw.io, se creó `PRESENTACION BODEGA EXPRESS.pptx` y se prepararon los entregables de la Fase 1 para su publicación en GitHub.

## Jueves 12 de Noviembre de 2026
- **Qué hice hoy:** Verificación del funcionamiento de la arquitectura distribuida de Bodega Express, realizando pruebas del Gateway, autenticación mediante API Key, balanceo entre dos instancias y replicación de PostgreSQL.
- **Pruebas realizadas:** Se comprobó la continuidad del servicio al detener y reiniciar ambas instancias de aplicación.
- **Documentación:** Actualización del README y de las evidencias de la Fase 2.

## Viernes 13 de Noviembre de 2026
- **Qué hice hoy:** Entrega de la Fase 2, incluyendo la arquitectura completa en Docker Compose, la validación del Gateway y la API Key, el balanceador con dos instancias, la replicación de PostgreSQL y la documentación de evidencias.
- **Dónde me trabé:** No hubo bloqueos técnicos importantes durante la validación final.
- **Qué haré la próxima clase:** Comenzar la implementación de la aplicación real en las instancias, incorporando las operaciones de escritura en la base primaria y lectura desde la réplica.
- **Uso de IA:** Se utilizó IA para revisar la documentación y apoyar la validación. Las decisiones y comprobaciones finales fueron revisadas.

## Miércoles 18 de Noviembre de 2026
- **Qué hice hoy:** Integración de la aplicación Bodega Express con PostgreSQL, configurando las operaciones de escritura en la base primaria y lectura desde la réplica. También se completó la configuración del Gateway con API Key y Rate Limiting.
- **Pruebas realizadas:** Se verificó la autenticación, el balanceo entre las dos instancias, la escritura y lectura de productos, el límite de solicitudes y el rechazo de métodos y cuerpos HTTP no permitidos.
- **Failover realizado:** A las `18:10:38.0610504 -03:00` inició la interrupción controlada. La sincronización previa mostró `0 bytes` pendientes. `db-primary` fue detenido a las `18:13:24.2667926 -03:00`; la promoción de `db-replica` inició a las `18:14:31.4471380 -03:00` y se completó correctamente con timeline 2 y `pg_is_in_recovery=false`. No se realizaron escrituras de prueba.
- **Recuperación del servicio:** app1, app2 y Gateway quedaron saludables y se verificó un GET autenticado con HTTP 200. La recuperación confirmada del Gateway ocurrió a las `18:15:54 -03:00`; desde el inicio de la interrupción correspondió a aproximadamente `315.94 segundos` o `5 minutos 16 segundos`.
- **Reincorporación:** Se corrigió la autenticación de `bodega_replicator`, se conservó `standby.signal` y se confirmó `.pgpass` con permisos 600. `db-primary` quedó en recovery como réplica de `db-replica`, con `pg_stat_wal_receiver` y `pg_stat_replication` en `streaming`. Ambos nodos observaron la posición WAL `0/30CA8D0`, y todos los registros de `productos` y `movimientos` coincidieron.
- **RPO observado:** La diferencia WAL previa fue `0 bytes`; este resultado no garantiza pérdida cero ante cualquier incidente futuro.
- **Documentación:** Actualización y revisión del README y elaboración de `docs/fase3/EVIDENCIAS.md` y `docs/fase3/PRUEBAS_DE_FALLA.md` con los resultados reales de la prueba.
- **Uso de IA:** Se utilizó IA como apoyo en la implementación, revisión del código y documentación. Las pruebas y resultados fueron comprobados en el entorno local.
- **Qué haré la próxima clase:** Conservar la topología final, revisar las evidencias documentadas y preparar la entrega sin realizar nuevas pruebas ni modificar la configuración.

## Jueves 19 de noviembre de 2026 – Revisión y preparación del avance

- Se revisó el estado del repositorio y los archivos modificados antes de preparar la actualización en GitHub.
- Se revisaron cambios en `.env.example`, `.gitignore`, `README.md`, `docker-compose.yml` y `docs/fase3/EVIDENCIAS.md`.
- Se preparó la documentación de `docs/fase3/PRUEBAS_DE_FALLA.md`.
- Se identificaron archivos locales que debían mantenerse fuera del repositorio, especialmente `_archivo_local/`, y se consideró la protección de credenciales y configuraciones sensibles.
- Se revisaron los cambios pendientes para evitar publicar archivos innecesarios.

## Viernes 20 de noviembre de 2026 – Validación y mejoras de la Fase 3

- Se revisó la topología posterior al failover y se confirmó que `db-replica` era la primaria actual y `db-primary` funcionaba como réplica.
- Se validó correctamente `docker compose config --quiet`.
- Se comprobó que los seis contenedores principales (`app1`, `app2`, `db-primary`, `db-replica`, `gateway` y `load-balancer`) estuvieran en estado `healthy`.
- El Gateway respondió HTTP 200 en `/health` con el cuerpo `gateway-ok`.
- Se realizaron seis solicitudes al Gateway; todas devolvieron HTTP 200 y alternaron entre `app-1` y `app-2`.
- `/health/db` respondió HTTP 200, indicando disponibilidad de la conexión con la primaria.
- Las cuatro solicitudes a `/health/db` devolvieron HTTP 200.
- Se consultó el producto ID 39 y respondió HTTP 200 con `X-DB: replica`.
- Se realizó una escritura mediante `POST /productos`: respondió HTTP 201 con `X-DB: primary` y `X-Instance: app-1`.
- Se creó el producto ID 42 con código `TEST-20261120-014500`.
- La lectura posterior de `GET /productos/42` respondió HTTP 200 con `X-DB: replica` y `X-Instance: app-2`; los datos coincidieron con los devueltos por el POST.
- Esta validación confirma escritura en la primaria y lectura posterior desde la réplica. No constituye un experimento de falla ni mide un tiempo exacto de replicación.
- Se realizó un experimento de retraso de replicación mediante la pausa de reproducción WAL en `db-primary`. El producto ID 41 fue creado correctamente en la primaria, pero la lectura desde la réplica devolvió HTTP 404 mientras permanecía desactualizada. Después de reanudar la reproducción WAL, la consulta respondió HTTP 200.
- Se documentaron los resultados, tiempos y limitaciones del experimento, aclarando que se simuló un retraso de replicación y no un corte de red.
- Se mejoró `app/app.py` incorporando un tiempo de espera configurable para las conexiones PostgreSQL y el endpoint `/health/db`.
- Se ajustaron los healthchecks de `docker-compose.yml` para comprobar la disponibilidad de la base de datos primaria.
- Se revisó la configuración de Nginx y se documentaron sus limitaciones de detección pasiva y el tratamiento de respuestas HTTP 503.
- Se actualizaron `README.md`, `docs/fase3/EVIDENCIAS.md` y `docs/fase3/PRUEBAS_DE_FALLA.md`.
- Se revisaron los resultados históricos del failover, conservando el RPO observado de 0 bytes pendientes y el RTO de 315,94 segundos.
- Se ejecutaron validaciones estáticas de Python y `git diff --check`, sin errores.

**Observación:** Los cambios quedaron en el entorno local. No se realizó un nuevo failover ni se registró un nuevo commit o push durante estas actividades.