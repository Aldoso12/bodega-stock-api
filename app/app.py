import json
import os
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import psycopg
from psycopg.rows import dict_row


INSTANCE_ID = os.environ.get("INSTANCE_ID", "unknown")
PRIMARY_URL = os.environ["DB_PRIMARY_URL"]
REPLICA_URL = os.environ["DB_REPLICA_URL"]


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS productos (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo VARCHAR(100) NOT NULL UNIQUE,
    nombre VARCHAR(200) NOT NULL,
    descripcion TEXT,
    precio NUMERIC(12, 2) NOT NULL CHECK (precio >= 0),
    stock INTEGER NOT NULL CHECK (stock >= 0),
    activo BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS movimientos (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    producto_id BIGINT NOT NULL REFERENCES productos(id),
    tipo VARCHAR(10) NOT NULL CHECK (tipo IN ('entrada', 'salida')),
    cantidad INTEGER NOT NULL CHECK (cantidad > 0),
    motivo TEXT,
    fecha TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_productos_nombre ON productos (nombre);
CREATE INDEX IF NOT EXISTS idx_movimientos_producto_fecha
    ON movimientos (producto_id, fecha DESC);
"""


class APIError(Exception):
    def __init__(self, status, message):
        self.status = status
        self.message = message


def json_default(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError("Unsupported JSON value")


def product_json(product):
    return {
        "id": product["id"],
        "codigo": product["codigo"],
        "nombre": product["nombre"],
        "descripcion": product["descripcion"],
        "precio": product["precio"],
        "stock": product["stock"],
        "activo": product["activo"],
    }


def require_object(payload):
    if not isinstance(payload, dict):
        raise APIError(400, "El cuerpo debe ser un objeto JSON")
    return payload


def required_text(payload, field):
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise APIError(400, f"{field} es obligatorio")
    return value.strip()


def non_negative_decimal(payload, field):
    value = payload.get(field)
    if isinstance(value, bool) or value is None:
        raise APIError(400, f"{field} debe ser un número no negativo")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise APIError(400, f"{field} debe ser un número no negativo")
    if not result.is_finite() or result < 0:
        raise APIError(400, f"{field} debe ser un número no negativo")
    return result


def non_negative_integer(payload, field):
    value = payload.get(field)
    if isinstance(value, bool) or value is None:
        raise APIError(400, f"{field} debe ser un entero no negativo")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise APIError(400, f"{field} debe ser un entero no negativo")
    if not result.is_finite() or result < 0 or result != result.to_integral_value():
        raise APIError(400, f"{field} debe ser un entero no negativo")
    return int(result)


def positive_integer(payload, field):
    value = non_negative_integer(payload, field)
    if value == 0:
        raise APIError(400, f"{field} debe ser mayor que cero")
    return value


def read_products(path):
    query = "SELECT id, codigo, nombre, descripcion, precio, stock, activo FROM productos"
    params = []
    search = parse_qs(urlparse(path).query).get("buscar", [None])[0]
    if search:
        query += " WHERE nombre ILIKE %s OR codigo ILIKE %s"
        term = f"%{search}%"
        params.extend([term, term])
    query += " ORDER BY id"
    with psycopg.connect(REPLICA_URL, row_factory=dict_row) as connection:
        return [product_json(row) for row in connection.execute(query, params).fetchall()]


def read_product(product_id):
    with psycopg.connect(REPLICA_URL, row_factory=dict_row) as connection:
        row = connection.execute(
            "SELECT id, codigo, nombre, descripcion, precio, stock, activo "
            "FROM productos WHERE id = %s",
            (product_id,),
        ).fetchone()
    if row is None:
        raise APIError(404, "Producto no encontrado")
    return product_json(row)


def read_movements():
    with psycopg.connect(REPLICA_URL, row_factory=dict_row) as connection:
        rows = connection.execute(
            "SELECT m.id, m.producto_id, p.codigo, m.tipo, m.cantidad, "
            "m.motivo, m.fecha FROM movimientos m "
            "JOIN productos p ON p.id = m.producto_id "
            "ORDER BY m.fecha DESC, m.id DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def create_product(payload):
    codigo = required_text(payload, "codigo")
    nombre = required_text(payload, "nombre")
    descripcion = payload.get("descripcion")
    if descripcion is not None and not isinstance(descripcion, str):
        raise APIError(400, "descripcion debe ser texto")
    precio = non_negative_decimal(payload, "precio")
    stock = non_negative_integer(payload, "stock")
    try:
        with psycopg.connect(PRIMARY_URL, row_factory=dict_row) as connection:
            row = connection.execute(
                "INSERT INTO productos (codigo, nombre, descripcion, precio, stock) "
                "VALUES (%s, %s, %s, %s, %s) "
                "RETURNING id, codigo, nombre, descripcion, precio, stock, activo",
                (codigo, nombre, descripcion, precio, stock),
            ).fetchone()
        return product_json(row)
    except psycopg.errors.UniqueViolation:
        raise APIError(409, "El código del producto ya existe")


def create_movement(payload):
    producto_id = positive_integer(payload, "producto_id")
    tipo = required_text(payload, "tipo").lower()
    if tipo not in ("entrada", "salida"):
        raise APIError(400, "tipo debe ser entrada o salida")
    cantidad = positive_integer(payload, "cantidad")
    motivo = payload.get("motivo")
    if motivo is not None and not isinstance(motivo, str):
        raise APIError(400, "motivo debe ser texto")

    try:
        with psycopg.connect(PRIMARY_URL, row_factory=dict_row) as connection:
            product = connection.execute(
                "SELECT id, stock FROM productos WHERE id = %s AND activo = TRUE FOR UPDATE",
                (producto_id,),
            ).fetchone()
            if product is None:
                raise APIError(404, "Producto inexistente o inactivo")

            new_stock = product["stock"] + cantidad if tipo == "entrada" else product["stock"] - cantidad
            if new_stock < 0:
                raise APIError(409, "La salida supera el stock disponible")

            connection.execute(
                "UPDATE productos SET stock = %s WHERE id = %s",
                (new_stock, producto_id),
            )
            movement = connection.execute(
                "INSERT INTO movimientos (producto_id, tipo, cantidad, motivo) "
                "VALUES (%s, %s, %s, %s) "
                "RETURNING id, producto_id, tipo, cantidad, motivo, fecha",
                (producto_id, tipo, cantidad, motivo),
            ).fetchone()
        return dict(movement)
    except APIError:
        raise


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, payload, database=None):
        body = json.dumps(payload, default=json_default).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Instance", INSTANCE_ID)
        if database is not None:
            self.send_header("X-DB", database)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            self.send_json(200, {"status": "ok", "instance": INSTANCE_ID})
            return
        try:
            if path == "/":
                self.send_json(200, {"status": "ok", "instance": INSTANCE_ID})
            elif path == "/productos":
                self.send_json(200, {"productos": read_products(self.path)}, "replica")
            elif path.startswith("/productos/"):
                product_id = parse_id(path[len("/productos/"):])
                self.send_json(200, read_product(product_id), "replica")
            elif path == "/movimientos":
                self.send_json(200, {"movimientos": read_movements()}, "replica")
            else:
                raise APIError(404, "Recurso no encontrado")
        except APIError as error:
            self.send_json(error.status, {"error": error.message}, "replica")
        except psycopg.OperationalError:
            self.send_json(500, {"error": "La réplica no está disponible"}, "replica")
        except psycopg.Error:
            self.send_json(500, {"error": "Error interno de base de datos"}, "replica")

    def do_POST(self):
        try:
            payload = self.read_json()
            path = urlparse(self.path).path
            if path == "/productos":
                result = create_product(payload)
            elif path == "/movimientos":
                result = create_movement(payload)
            else:
                raise APIError(404, "Recurso no encontrado")
            self.send_json(201, result, "primary")
        except APIError as error:
            self.send_json(error.status, {"error": error.message}, "primary")
        except psycopg.OperationalError:
            self.send_json(500, {"error": "La base primaria no está disponible"}, "primary")
        except psycopg.Error:
            self.send_json(500, {"error": "Error interno de base de datos"}, "primary")

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError):
            raise APIError(400, "El cuerpo debe ser JSON válido")
        return require_object(payload)

    def log_message(self, format, *args):
        return


def parse_id(raw_id):
    try:
        product_id = int(raw_id)
    except ValueError:
        raise APIError(400, "El identificador debe ser un entero positivo")
    if product_id <= 0:
        raise APIError(400, "El identificador debe ser un entero positivo")
    return product_id


def initialize_schema():
    with psycopg.connect(PRIMARY_URL) as connection:
        connection.execute(SCHEMA_SQL)


initialize_schema()
ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
