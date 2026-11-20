# Diseño del sistema - Bodega Express

## 1. Problemática y requisitos

Bodega Express aborda la congestión y la desincronización del stock en una bodega de alta rotación. Los clientes y vendedores necesitan consultar productos, precios y disponibilidad sin desplazarse físicamente por la bodega. Los operarios y encargados de logística necesitan registrar entradas, salidas, mermas y otros movimientos de inventario de forma ordenada.

El sistema debe permitir consultar productos por nombre o código, consultar precio y cantidad disponible, registrar productos y movimientos, validar que las salidas no superen el stock disponible y consultar los movimientos de inventario. Las consultas públicas y las operaciones internas deben diferenciarse, utilizando API Key para proteger las operaciones internas.

Como requisitos principales de arquitectura, todas las solicitudes externas ingresan mediante un gateway, se distribuyen a través de un balanceador de carga y son atendidas por dos instancias de aplicación. Las consultas de productos y stock se dirigen a una base de datos réplica, mientras que las escrituras se realizan en la base primaria. La solución debe seguir respondiendo si una instancia de aplicación deja de funcionar, mantener las consultas habituales bajo 500 ms en la carga objetivo y evitar el almacenamiento de claves en el repositorio.

## 2. Estimación de carga y almacenamiento a cinco años

La proyección considera un inventario inicial de 5.000 productos, un crecimiento anual del inventario de 8%, 1.500 consultas GET diarias y 150 escrituras POST diarias inicialmente. También considera un crecimiento anual del tráfico de 20%, una relación aproximada de 10 consultas de lectura por cada escritura y una jornada de mayor actividad de 8 horas.

Al quinto año se estiman 6.802 productos, 3.110 consultas GET diarias, 311 escrituras POST diarias y 3.421 solicitudes totales diarias. En una jornada de 28.800 segundos, esto equivale a 0,108 solicitudes GET por segundo, 0,011 solicitudes POST por segundo y 0,119 solicitudes totales por segundo.

Se supone que el 30% del tráfico diario se concentra en una hora. En ese período se estiman 933 solicitudes GET, 93 solicitudes POST y 1.026 solicitudes totales, equivalentes a 0,259, 0,026 y 0,285 solicitudes por segundo, respectivamente. Se contemplan ráfagas de hasta cinco veces el tráfico de hora punta, aproximadamente 1,43 solicitudes por segundo. El objetivo de capacidad se mantiene en al menos 5 solicitudes por segundo y 20 usuarios concurrentes.

Para el almacenamiento se consideran aproximadamente 3 KB por producto, 1 KB por movimiento de inventario, conservación de los movimientos durante cinco años y un 30% adicional por índices y estructura de la base de datos. El resultado aproximado es:

| Concepto | Cantidad | Almacenamiento aproximado |
|---|---:|---:|
| Productos | 6.802 | 20 MB |
| Movimientos de inventario | 407.340 | 398 MB |
| Índices y estructura adicional | - | 125 MB |
| **Total estimado** | - | **543 MB** |

Se recomienda reservar una capacidad de 1,1 GB. Estas cifras son estimaciones académicas y no mediciones reales.

## 3. Diagramas lógico y físico

El [Diagrama-lógico.png](./Diagrama-lógico.png) muestra el flujo entre los clientes, el gateway, el balanceador, las dos instancias de aplicación y las bases de datos. Representa la separación entre las operaciones POST dirigidas a la base primaria y las consultas GET atendidas por la réplica, además de la replicación desde la primaria.

El [Diagrama-físico.png](./Diagrama-físico.png) muestra la distribución en un servidor o computador mediante Docker Compose y contenedores Docker. Incluye el gateway, el balanceador, las dos aplicaciones y los contenedores de la base primaria y la réplica dentro de la red interna Docker. También deja visibles los puntos únicos de falla identificados para el servidor físico, el gateway, el balanceador y la base primaria.

Se conservan también las versiones editables de los diagramas: [Diagrama-lógico.drawio](./Diagrama-lógico.drawio) y [Diagrama-físico.drawio](./Diagrama-físico.drawio).

## 4. Justificación de los componentes, alternativas y costo

| Componente | Problema que resuelve | Qué ocurriría sin él | Costo en latencia, complejidad o recursos |
|---|---|---|---|
| Gateway | Centraliza el acceso externo, aplica API Key y limita la cantidad de solicitudes. | Las aplicaciones quedarían expuestas individualmente y no existiría un único control centralizado de autenticación y límite de peticiones. | Añade una redirección HTTP y procesamiento por solicitud. Aumenta ligeramente la latencia y exige ejecutar otro contenedor. |
| Balanceador de carga | Distribuye las solicitudes entre `app1` y `app2` y permite continuar atendiendo cuando una instancia queda fuera de servicio. | Las solicitudes dependerían de una instancia específica o habría que administrar manualmente qué aplicación recibe cada solicitud. | Añade un contenedor Nginx, configuración de upstream y reintentos. Puede agregar latencia y requiere definir el comportamiento ante instancias no disponibles. |
| Dos instancias de aplicación | Permiten distribuir solicitudes y continuar respondiendo si una instancia deja de funcionar. | Una única instancia concentraría la carga y sería un único punto de falla aplicativo. | Requiere dos contenedores, balanceo y mayor coordinación. Docker Compose mantiene ambos servicios y sus healthchecks. |
| Base de datos primaria PostgreSQL 16 | Registra productos, movimientos y demás escrituras del inventario. | Las modificaciones quedarían concentradas sin una instancia definida para aceptar escrituras después de una promoción. | Agrega un contenedor y un volumen persistente. Una sola base de escritura aumenta la concentración de carga y constituye un componente crítico. |
| Base de datos réplica PostgreSQL 16 | Atiende las consultas de productos y stock separadas de las operaciones de escritura. | Las lecturas competirían directamente con las escrituras en la primaria y no habría una réplica física para distribuir consultas. | Agrega otro contenedor, volumen persistente y tráfico WAL. Introduce posible retraso de replicación y datos temporalmente desactualizados. |
| Replicación streaming primaria-réplica | Mantiene sincronizada la réplica y permite su promoción si falla la primaria. | No existiría una copia física disponible para lecturas ni un procedimiento basado en cambio de roles para continuar con las escrituras. | Agrega tráfico WAL continuo, administración de roles, credenciales de replicación y operación de failover. La replicación asíncrona puede presentar cambios pendientes. |
| Docker Compose y contenedores | Organiza los seis servicios, sus dependencias, redes internas y volúmenes dentro de un entorno reproducible. | Los componentes tendrían que iniciarse y configurarse de forma independiente, con mayor riesgo de incompatibilidad entre puertos y nombres de red. | Agrega archivos de despliegue y administración de contenedores. Facilita reconstrucción y sustitución de servicios, pero mantiene el servidor físico como recurso compartido. |

La base de datos definida para la implementación actual es PostgreSQL 16. La arquitectura utiliza una base primaria y una réplica física mediante streaming replication asíncrona. Esta decisión permite separar escrituras y lecturas y conservar una segunda copia de los datos. Su complejidad incluye administrar roles, WAL, recuperación y promoción. No se dispone en los documentos revisados de un costo monetario, tamaño de instancia ni medición comparativa de latencia entre PostgreSQL y una tecnología alternativa; por ello, no se asignan esas cifras ni se considera SQL Server como la tecnología actual.

Los objetivos de recuperación definidos en Fase 1 son un RPO máximo de 1 minuto de datos potencialmente perdidos y un RTO máximo de 300 segundos para recuperar la capacidad de escritura. En el failover ejecutado se observó un RPO de 0 bytes pendientes en el punto comprobado y un RTO de 315,94 segundos hasta una respuesta HTTP 200 confirmada del Gateway, por lo que se superó el objetivo RTO por 15,94 segundos. El RPO observado corresponde a esa ejecución y no garantiza pérdida cero ante cualquier fallo futuro.

En la topología final documentada, `db-replica` es la primaria actual y `db-primary` es la réplica actual. Las aplicaciones deben escribir en la primaria actual y leer desde la réplica actual.

## 5. Riesgos y mitigaciones

### Riesgo 1: puntos únicos de falla en la infraestructura física

El diagrama físico identifica el servidor físico, el gateway, el balanceador y las bases de datos como elementos cuya indisponibilidad puede afectar el servicio.

**Mitigación:** mantener dos instancias de aplicación, validar la continuidad ante la caída de una de ellas y conservar la separación primaria-réplica mediante streaming replication. Para reducir otros puntos únicos de falla se requeriría redundancia de infraestructura adicional, cuya implementación no está documentada.

### Riesgo 2: retraso de replicación

La réplica podría entregar información desactualizada durante una interrupción de comunicación o una pausa de reproducción WAL.

**Mitigación:** considerar el carácter asíncrono de la replicación al diseñar lecturas posteriores a escrituras y monitorear el estado de streaming y los bytes pendientes. El proyecto comprobó un retraso controlado mediante una pausa de WAL: la aplicación devolvió HTTP 404 para un registro no reproducido y HTTP 200 después de reanudar la réplica. No implementa fallback automático de lectura a la primaria ni reintentos para datos desactualizados.

### Riesgo 3: failover y cambio incorrecto de roles

Una promoción incorrecta, una configuración desactualizada en las aplicaciones o el mantenimiento simultáneo de dos primarios puede provocar escrituras divergentes o pérdida de continuidad.

**Mitigación:** confirmar `pg_is_in_recovery()` antes y después de la promoción, detener las rutas de escritura durante la ventana controlada, recrear app1 y app2 con los destinos de la topología final y verificar `streaming` en el receptor y el emisor antes de declarar la recuperación. El failover ejecutado promovió `db-replica`, reincorporó `db-primary` como standby y confirmó la replicación final; el procedimiento y sus resultados están registrados en la documentación de Fase 3.

## 6. Referencia a la presentación PowerPoint de la entrega

La presentación [PRESENTACION BODEGA EXPRESS.pptx](./PRESENTACION%20BODEGA%20EXPRESS.pptx) se incluye en la entrega de Fase 1 y debe presentar este diseño, los requisitos y los diagramas lógico y físico de forma coherente con la arquitectura documentada.
