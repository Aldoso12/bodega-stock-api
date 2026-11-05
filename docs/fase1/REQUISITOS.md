# Requisitos del sistema – Bodega Express

## 1. Descripción general

Bodega Express permitirá consultar productos, precios y disponibilidad de stock de una ferretería de barrio. También permitirá que los encargados registren entradas y salidas de mercadería mediante un sistema interno.

La arquitectura estará preparada para soportar múltiples consultas simultáneas, utilizando dos instancias de aplicación, un balanceador de carga, un gateway y una base de datos primaria con una réplica.

## 2. Requisitos funcionales

| Código | Requisito |
|---|---|
| RF-01 | Consultar productos por nombre o código. |
| RF-02 | Consultar precio y cantidad disponible de cada producto. |
| RF-03 | Registrar nuevos productos en el inventario. |
| RF-04 | Registrar entradas de mercadería. |
| RF-05 | Registrar salidas de stock por ventas o ajustes. |
| RF-06 | Validar que no se registre una salida superior al stock disponible. |
| RF-07 | Consultar los movimientos de inventario. |
| RF-08 | Permitir consultas públicas y operaciones internas protegidas mediante API Key. |

## 3. Requisitos no funcionales

| Código | Requisito |
|---|---|
| RNF-01 | El sistema contará con dos instancias de aplicación para distribuir las solicitudes. |
| RNF-02 | Todas las solicitudes externas ingresarán mediante el gateway. |
| RNF-03 | Las consultas de productos y stock se realizarán desde la réplica. |
| RNF-04 | Las escrituras de inventario se realizarán exclusivamente en la base primaria. |
| RNF-05 | El sistema deberá continuar respondiendo si una instancia de aplicación deja de funcionar. |
| RNF-06 | Las consultas habituales deberán responder en menos de 500 ms bajo la carga objetivo. |
| RNF-07 | Las operaciones internas deberán utilizar autenticación mediante API Key. |
| RNF-08 | Se implementará replicación entre la base primaria y la réplica. |
| RNF-09 | El sistema deberá evitar movimientos que generen cantidades negativas de stock. |
| RNF-10 | Las contraseñas y claves de acceso no deberán almacenarse en el repositorio Git. |

## 4. Estimación de carga

Para estimar el crecimiento se consideran los siguientes supuestos:

- Inventario inicial de 5.000 productos.
- Crecimiento anual del inventario del 8%.
- 1.500 consultas GET diarias inicialmente.
- 150 escrituras POST diarias inicialmente.
- Crecimiento anual del tráfico del 20%.
- Relación de 10 consultas de lectura por cada escritura.
- Jornada de mayor actividad de 8 horas diarias.

### 4.1 Proyección a cinco años

| Indicador | Año 1 | Año 2 | Año 3 | Año 4 | Año 5 |
|---|---:|---:|---:|---:|---:|
| Productos | 5.000 | 5.400 | 5.832 | 6.299 | 6.802 |
| Consultas GET/día | 1.500 | 1.800 | 2.160 | 2.592 | 3.110 |
| Escrituras POST/día | 150 | 180 | 216 | 259 | 311 |
| Total solicitudes/día | 1.650 | 1.980 | 2.376 | 2.851 | 3.421 |

### 4.2 Capacidad estimada

Al quinto año se proyectan aproximadamente:

- 3.110 consultas de lectura diarias.
- 311 operaciones de escritura diarias.
- 3.421 solicitudes totales por día.
- Una relación aproximada de 10:1 entre lecturas y escrituras.

Considerando una concentración de solicitudes en horarios de mayor actividad, se establece como objetivo inicial soportar al menos 5 solicitudes por segundo y 20 usuarios concurrentes.

### 4.3 Justificación de la arquitectura

Se utilizará una base de datos primaria para registrar las modificaciones del inventario y una réplica destinada a responder las consultas.

Esta separación permitirá distribuir el trabajo y evitar que las consultas frecuentes interfieran directamente con las operaciones de escritura.

Las dos instancias de aplicación permitirán distribuir las solicitudes mediante un balanceador de carga, mientras que el gateway centralizará el acceso y aplicará controles de seguridad y límites de peticiones.

## 5. Objetivos de recuperación

Se establecen los siguientes objetivos iniciales para evaluar la tolerancia a fallos:

- **RPO objetivo:** máximo 1 minuto de datos potencialmente perdidos ante una falla de la base primaria.
- **RTO objetivo:** recuperar la capacidad de escritura en un máximo de 5 minutos.

Estos valores son metas de diseño que deberán comprobarse mediante los experimentos de la fase 3.

## 6. Supuestos y limitaciones

Las cifras corresponden a una estimación académica para una ferretería de barrio y no a mediciones de un negocio real.

El crecimiento de productos y solicitudes podrá variar según la demanda. La replicación también podría presentar retrasos, por lo que se deberá considerar la posibilidad de consultar información desactualizada durante una falla o interrupción de comunicación.