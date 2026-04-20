import os
import psycopg2
import psycopg2.extras

def get_db():
    conn = psycopg2.connect(os.environ.get("DATABASE_URL"))
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    # ── TABLAS ────────────────────────────────────────────────────────────────

    c.execute("""
    CREATE TABLE IF NOT EXISTS parametros (
        clave   TEXT PRIMARY KEY,
        valor   TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS equipos (
        id               SERIAL PRIMARY KEY,
        nombre           TEXT NOT NULL,
        cantidad         INTEGER DEFAULT 1,
        fecha_compra     TEXT,
        costo_total      REAL DEFAULT 0,
        vida_util_meses  INTEGER DEFAULT 48,
        valor_residual   REAL DEFAULT 0,
        activo           INTEGER DEFAULT 1
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS insumos (
        id            SERIAL PRIMARY KEY,
        nombre        TEXT NOT NULL UNIQUE,
        categoria     TEXT NOT NULL,
        proveedor     TEXT,
        unidad_compra TEXT,
        uds_por_pack  REAL DEFAULT 1,
        precio_pack   REAL DEFAULT 0,
        unidad_consum TEXT,
        stock_inicial REAL DEFAULT 0,
        stock_minimo  REAL DEFAULT 0,
        activo        INTEGER DEFAULT 1
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS productos (
        id        SERIAL PRIMARY KEY,
        nombre    TEXT NOT NULL UNIQUE,
        categoria TEXT NOT NULL,
        activo    INTEGER DEFAULT 1
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS recetas (
        id          SERIAL PRIMARY KEY,
        producto_id INTEGER NOT NULL REFERENCES productos(id),
        insumo_id   INTEGER NOT NULL REFERENCES insumos(id),
        cantidad    REAL DEFAULT 0,
        UNIQUE(producto_id, insumo_id)
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS compras (
        id           SERIAL PRIMARY KEY,
        fecha        TEXT NOT NULL,
        insumo_id    INTEGER NOT NULL REFERENCES insumos(id),
        cantidad_uds REAL NOT NULL,
        costo_total  REAL DEFAULT 0,
        proveedor    TEXT,
        notas        TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS consumos (
        id            SERIAL PRIMARY KEY,
        fecha         TEXT NOT NULL,
        tipo          TEXT NOT NULL,
        descripcion   TEXT,
        pedido_ref    TEXT,
        insumo_id     INTEGER REFERENCES insumos(id),
        cantidad_base REAL DEFAULT 0,
        cantidad_real REAL DEFAULT 0,
        notas         TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS clientes (
        id               SERIAL PRIMARY KEY,
        nombre           TEXT NOT NULL,
        apellido         TEXT,
        tipo_documento   TEXT DEFAULT 'CI',
        numero_documento TEXT,
        telefono         TEXT,
        email            TEXT,
        direccion        TEXT,
        ciudad           TEXT,
        fecha_creacion   TEXT,
        activo           INTEGER DEFAULT 1
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS pedidos (
        id               SERIAL PRIMARY KEY,
        numero           TEXT UNIQUE,
        fecha            TEXT NOT NULL,
        cliente_id       INTEGER REFERENCES clientes(id),
        cliente          TEXT,
        telefono         TEXT,
        total            REAL DEFAULT 0,
        adelanto         REAL DEFAULT 0,
        cuotas           INTEGER DEFAULT 1,
        fecha_entrega    TEXT,
        estado           TEXT DEFAULT 'Pendiente',
        canal            TEXT,
        modelo_seguir    TEXT,
        notas            TEXT,
        solicita_factura INTEGER DEFAULT 0,
        factura_razon    TEXT,
        factura_ruc      TEXT,
        factura_email    TEXT,
        factura_tel      TEXT,
        factura_dir      TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS pedido_items (
        id          SERIAL PRIMARY KEY,
        pedido_id   INTEGER NOT NULL REFERENCES pedidos(id),
        producto_id INTEGER REFERENCES productos(id),
        descripcion TEXT,
        cantidad    REAL DEFAULT 1,
        precio_unit REAL DEFAULT 0
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS pedido_cuotas (
        id             SERIAL PRIMARY KEY,
        pedido_id      INTEGER NOT NULL REFERENCES pedidos(id),
        numero_cuota   INTEGER NOT NULL,
        monto_esperado REAL DEFAULT 0,
        monto_pagado   REAL DEFAULT 0,
        pagada         INTEGER DEFAULT 0,
        fecha_pago     TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS pedido_estado_historial (
        id        SERIAL PRIMARY KEY,
        pedido_id INTEGER NOT NULL REFERENCES pedidos(id),
        estado    TEXT NOT NULL,
        fecha_hora TEXT NOT NULL
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS stock_reingreso (
        id            SERIAL PRIMARY KEY,
        pedido_id     INTEGER REFERENCES pedidos(id),
        pedido_numero TEXT,
        producto_id   INTEGER REFERENCES productos(id),
        descripcion   TEXT,
        cantidad      REAL DEFAULT 1,
        valor_unit    REAL DEFAULT 0,
        motivo        TEXT,
        fecha         TEXT NOT NULL,
        estado        TEXT DEFAULT 'Disponible'
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS gastos (
        id               SERIAL PRIMARY KEY,
        fecha            TEXT NOT NULL,
        categoria        TEXT NOT NULL,
        descripcion      TEXT,
        proveedor        TEXT,
        comprobante      TEXT,
        forma_pago       TEXT,
        monto            REAL DEFAULT 0,
        tipo_recurrencia TEXT DEFAULT 'Único',
        notas            TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS prestamos (
        id               SERIAL PRIMARY KEY,
        descripcion      TEXT NOT NULL,
        monto_total      REAL DEFAULT 0,
        monto_adjudicado REAL DEFAULT 0,
        cuotas           INTEGER DEFAULT 12,
        cuotas_pagadas   INTEGER DEFAULT 0,
        plazo_meses      INTEGER DEFAULT 12,
        fecha_inicio     TEXT,
        fecha_fin        TEXT,
        cuota_mensual    REAL DEFAULT 0,
        entidad          TEXT,
        notas            TEXT,
        activo           INTEGER DEFAULT 1
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS marketing (
        id                SERIAL PRIMARY KEY,
        mes               TEXT NOT NULL,
        plataforma        TEXT,
        tipo_campana      TEXT,
        presupuesto       REAL DEFAULT 0,
        gasto_real        REAL DEFAULT 0,
        alcance           INTEGER DEFAULT 0,
        interacciones     INTEGER DEFAULT 0,
        pedidos_generados INTEGER DEFAULT 0,
        venta_generada    REAL DEFAULT 0,
        notas             TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS categorias (
        id     SERIAL PRIMARY KEY,
        valor  TEXT UNIQUE,
        orden  INTEGER DEFAULT 0
    )""")

    # Commit todas las tablas antes de continuar
    conn.commit()

    # ── MIGRACIONES (columnas que pueden faltar en DBs existentes) ────────────
    migrations = [
        ("equipos",   "cantidad",         "INTEGER DEFAULT 1"),
        ("gastos",    "tipo_recurrencia",  "TEXT DEFAULT 'Único'"),
        ("prestamos", "cuotas_pagadas",    "INTEGER DEFAULT 0"),
        ("pedidos",   "cliente_id",        "INTEGER"),
        ("pedidos",   "cuotas",            "INTEGER DEFAULT 1"),
        ("pedidos",   "modelo_seguir",     "TEXT"),
        ("pedidos",   "solicita_factura",  "INTEGER DEFAULT 0"),
        ("pedidos",   "factura_razon",     "TEXT"),
        ("pedidos",   "factura_ruc",       "TEXT"),
        ("pedidos",   "factura_email",     "TEXT"),
        ("pedidos",   "factura_tel",       "TEXT"),
        ("pedidos",   "factura_dir",       "TEXT"),
    ]
    for tabla, col, tipo in migrations:
        try:
            c.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {tipo}")
            conn.commit()
        except psycopg2.errors.DuplicateColumn:
            conn.rollback()
        except Exception:
            conn.rollback()

    # ── SEED: parámetros ──────────────────────────────────────────────────────
    defaults = [
        ('horas_mes', '160'),
        ('sueldo_mensual', '3500000'),
        ('gastos_fijos', '800000'),
        ('ventas_estimadas_mes', '80'),
        ('margen_deseado', '0.35'),
        ('impuestos', '0.10'),
    ]
    for k, v in defaults:
        c.execute("""
            INSERT INTO parametros (clave, valor) VALUES (%s, %s)
            ON CONFLICT (clave) DO NOTHING
        """, (k, v))

    # ── SEED: insumos ─────────────────────────────────────────────────────────
    insumos = [
        ("Papel Sublimación A4","Sublimación","PrintShop PY","Pack 100 uds",100,85000,"Hoja",500,50),
        ("Papel Sublimación A3","Sublimación","PrintShop PY","Pack 100 uds",100,140000,"Hoja",300,40),
        ("Tinta Sublimación CMYK","Sublimación","InkPro","Set 4 tintas",1,180000,"Set",2,1),
        ("Remera Blanca Adulto","Sublimación","TextilPY","Unidad",1,35000,"Unidad",30,10),
        ("Remera Blanca Niño","Sublimación","TextilPY","Unidad",1,22000,"Unidad",20,8),
        ("Film DTF A4","DTF","DTF Paraguay","Pack 100 uds",100,95000,"Hoja",400,50),
        ("Film DTF A3","DTF","DTF Paraguay","Pack 100 uds",100,165000,"Hoja",200,30),
        ("Polvo Adhesivo DTF","DTF","DTF Paraguay","Kg",1,120000,"Gramo",3000,500),
        ("Tinta DTF CMYK+W","DTF","DTF Paraguay","Set 5 tintas",1,350000,"Set",1,1),
        ("Vinil Imprimible A4","Stickers","VinilStore","Pack 10 uds",10,45000,"Hoja",80,15),
        ("Vinil Imprimible A3","Stickers","VinilStore","Pack 10 uds",10,70000,"Hoja",50,10),
        ("Laminado Mate A4","Stickers","VinilStore","Pack 10 uds",10,38000,"Hoja",60,15),
        ("Laminado Brillante A4","Stickers","VinilStore","Pack 10 uds",10,38000,"Hoja",60,15),
        ("Lienzo Tela 30x40cm","Cuadros","ArtStore PY","Unidad",1,28000,"Unidad",10,4),
        ("Lienzo Tela 40x60cm","Cuadros","ArtStore PY","Unidad",1,45000,"Unidad",8,3),
        ("Lienzo Tela 60x80cm","Cuadros","ArtStore PY","Unidad",1,75000,"Unidad",5,2),
        ("Marco MDF 30x40","Cuadros","ArtStore PY","Unidad",1,35000,"Unidad",6,2),
        ("Cinta Sublimación","General","PrintShop PY","Rollo",1,25000,"Rollo",4,2),
        ("Papel tissue","General","PrintShop PY","Rollo",1,18000,"Rollo",3,1),
        ("Bolsas OPP 30x40","General","EmpaquePY","Pack 100 uds",100,22000,"Unidad",500,50),
    ]
    for row in insumos:
        c.execute("""
            INSERT INTO insumos
                (nombre,categoria,proveedor,unidad_compra,uds_por_pack,
                 precio_pack,unidad_consum,stock_inicial,stock_minimo)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (nombre) DO NOTHING
        """, row)

    # ── SEED: productos ───────────────────────────────────────────────────────
    productos = [
        ("Remera Sublimada Adulto (diseño simple)", "Sublimación"),
        ("Remera Sublimada Full Print",             "Sublimación"),
        ("Sticker Vinil A6 laminado",               "Stickers"),
        ("Plancha Stickers A4",                     "Stickers"),
        ("Cuadro Sublimado 30x40cm",                "Cuadros"),
        ("Cuadro Sublimado 40x60cm",                "Cuadros"),
        ("Transfer DTF A4",                         "DTF"),
        ("Transfer DTF A3 + Aplicado",              "DTF"),
    ]
    for row in productos:
        c.execute("""
            INSERT INTO productos (nombre, categoria) VALUES (%s, %s)
            ON CONFLICT (nombre) DO NOTHING
        """, row)

    # ── SEED: recetas (usando subqueries para ids seguros) ────────────────────
    recetas = [
        (1,1,2),(1,4,1),(1,18,1),(1,19,1),
        (2,2,2),(2,4,1),(2,18,1),(2,19,1),
        (3,10,1),(3,12,1),(4,10,1),(4,12,1),
        (5,2,1),(5,14,1),(5,18,1),(5,19,1),
        (6,2,2),(6,15,1),(6,18,1),(6,19,1),
        (7,6,1),(7,9,1),(7,8,1),
        (8,7,1),(8,9,1),(8,8,1),(8,4,1),
    ]
    for producto_id, insumo_id, cantidad in recetas:
        c.execute("""
            INSERT INTO recetas (producto_id, insumo_id, cantidad)
            SELECT p.id, i.id, %s
            FROM (SELECT id FROM productos ORDER BY id LIMIT 1 OFFSET %s) p,
                 (SELECT id FROM insumos   ORDER BY id LIMIT 1 OFFSET %s) i
            ON CONFLICT (producto_id, insumo_id) DO NOTHING
        """, (cantidad, producto_id - 1, insumo_id - 1))

    conn.commit()
    conn.close()
