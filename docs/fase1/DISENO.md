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

| Componente | Problema que resuelve | Alternativa considerada | Costo |
|---|---|---|---|
| Gateway | Centraliza el ingreso de solicitudes, aplica API Key y permite controlar el límite de peticiones. | Permitir el acceso directo a las aplicaciones, reduciendo la centralización de estos controles. | No informado en los archivos revisados; pendiente de estimación. |
| Balanceador de carga | Distribuye las solicitudes entre las dos instancias de aplicación y evita depender de una sola instancia. | Mantener una sola instancia, con menor complejidad pero sin la tolerancia requerida ante su falla. | No informado en los archivos revisados; pendiente de estimación. |
| Dos instancias de aplicación | Permiten continuar respondiendo si una instancia deja de funcionar y distribuir las consultas simultáneas. | Una única instancia de aplicación. | No informado en los archivos revisados; pendiente de estimación. |
| Base de datos primaria | Registra los productos y las modificaciones del inventario, incluyendo entradas y salidas. | Usar una única base sin réplica, con menor complejidad pero sin separar lecturas y escrituras. | No informado en los archivos revisados; pendiente de estimación. |
| Base de datos réplica | Atiende las consultas de productos y stock, evitando que las lecturas interfieran directamente con las escrituras. | Ejecutar las lecturas en la primaria, con menor infraestructura pero mayor concentración de carga. | No informado en los archivos revisados; pendiente de estimación. |
| Replicación primaria-réplica | Mantiene una copia para las consultas y apoya la continuidad ante problemas de la primaria, considerando que puede existir retraso de replicación. | No utilizar réplica, reduciendo componentes pero perdiendo la separación de cargas. | No informado en los archivos revisados; pendiente de estimación. |
| Docker Compose y contenedores | Representan la distribución física de los componentes dentro de un servidor y una red interna Docker. | Ejecutar los componentes directamente en el servidor, sin la organización en contenedores mostrada en el diseño físico. | No informado en los archivos revisados; pendiente de estimación. |

La tecnología de base de datos inicialmente considerada es SQL Server. La alternativa tecnológica concreta es PostgreSQL 16 con replicación, porque es la exigida por la pauta. La autorización de SQL Server está pendiente de confirmación con la profesora, por lo que la decisión definitiva debe tomarse después de esa confirmación. No se asigna un costo a ninguna alternativa porque el repositorio no contiene precios ni información de licenciamiento.

## 5. Riesgos y mitigaciones

### Riesgo 1: puntos únicos de falla en la infraestructura física

El diagrama físico identifica el servidor físico, el gateway, el balanceador y la base primaria como puntos únicos de falla.

**Mitigación:** probar la continuidad ante la caída de una instancia de aplicación y evaluar posteriormente medidas para reducir los puntos únicos de falla identificados. La disponibilidad final de redundancia adicional queda pendiente de definición.

### Riesgo 2: retraso de replicación

La réplica podría entregar información desactualizada durante una falla o una interrupción de comunicación.

**Mitigación:** medir el comportamiento de la replicación y considerar este retraso al dirigir las consultas. La réplica por sí sola no garantiza una recuperación automática: para recuperar el servicio de escritura se requiere un mecanismo de promoción o failover de la réplica, cuya implementación queda pendiente de definición. Los valores definitivos deben comprobarse mediante los experimentos de la fase 3.

### Riesgo 3: elección de tecnología de base de datos no confirmada

La solución inicialmente considera SQL Server, pero la pauta exige PostgreSQL 16 con replicación y la autorización de la tecnología aún está pendiente.

**Mitigación:** confirmar la tecnología con la profesora antes de cerrar la implementación y validar que la alternativa aprobada soporte la replicación y la separación entre lecturas y escrituras requeridas.

## 6. Referencia a la presentación PowerPoint de la entrega

La presentación PowerPoint de la entrega deberá referenciar este diseño, los requisitos y los diagramas lógico y físico. El archivo o enlace de la presentación no está incluido en los archivos revisados, por lo que su referencia concreta queda pendiente de incorporación.
