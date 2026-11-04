# Problemática: Sistema de Consulta de Inventario y Stock (Bodega Express)

## 1. ¿Quién la usa?
* **Clientes / Vendedores en terreno**: Utilizan una interfaz web pública o móvil para consultar de forma rápida la disponibilidad, ubicación en pasillos y precios de los productos en bodega.
* **Operarios de Bodega / Encargados de Logística**: Utilizan un panel de administración (app interna) para registrar el ingreso de nueva mercancía, mermas o la salida de productos por despachos.

## 2. ¿Qué problema resuelve?
Resuelve el problema de la congestión y desincronización en el stock de una bodega de alta rotación. Evita que los vendedores pierdan tiempo físico yendo a pasillos a revisar si hay productos, centralizando la información en línea y permitiendo registrar las transacciones de entrada de manera ordenada.

## 3. ¿Por qué hay muchas más lecturas que escrituras (10:1)?
* **Lecturas (GET)**: Cada vez que un cliente pregunta por un producto, un vendedor consulta el stock, o el sistema actualiza la vista general de la vitrina digital, se generan cientos de consultas concurrentes a la base de datos.
* **Escrituras (POST)**: Las transacciones de escritura ocurren únicamente cuando se compran lotes grandes, se realiza una reposición de inventario o se ajusta una merma, lo cual sucede con una frecuencia mucho menor (estimado en una relación superior a 10 consultas de lectura por cada modificación de stock).

## 4. Tipos de clientes que consumen la API
1. **Cliente Web / Móvil (Usuarios generales/vendedores)**: Consumen endpoints de lectura rápida (`GET /api/v1/productos/...`).
2. **Sistema Externo / Panel de Administración (Logística)**: Consume endpoints de escritura (`POST /api/v1/inventario/movimientos`) para registrar entradas o salidas de stock con validación de API Key.