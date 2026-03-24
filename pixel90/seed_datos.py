"""
seed_datos.py — Carga datos de simulación para PIXEL90
Ejecutar: py seed_datos.py
"""
import sqlite3, os, random
from datetime import date, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), 'db', 'pixel90.db')

random.seed(42)

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA foreign_keys = ON")

# ── helpers ──────────────────────────────────────────────────────────────────
def rnd_fecha(dias_atras_max=180, dias_atras_min=0):
    delta = random.randint(dias_atras_min, dias_atras_max)
    return (date.today() - timedelta(days=delta)).isoformat()

def rnd_fecha_rango(desde, hasta):
    d0 = date.fromisoformat(desde)
    d1 = date.fromisoformat(hasta)
    delta = (d1 - d0).days
    return (d0 + timedelta(days=random.randint(0, delta))).isoformat()

# ── 1. EQUIPOS ────────────────────────────────────────────────────────────────
print("→ Cargando equipos...")
equipos = [
    ("Impresora Sublimación Epson L1800",  "2023-03-15", 2_800_000,  48, 250_000),
    ("Prensa de Calor Plana 38x38cm",      "2023-03-15", 1_600_000,  60,  80_000),
    ("Plotter de Corte Silhouette Cameo",  "2023-08-01", 3_200_000,  60, 200_000),
    ("Impresora DTF A3",                   "2024-01-10", 9_500_000,  60, 500_000),
    ("Prensa DTF + Curado",                "2024-01-10", 2_200_000,  60, 100_000),
    ("PC Diseño (Ryzen 5 + 16GB)",         "2023-03-15", 5_800_000,  48, 600_000),
    ("Monitor 27\" Color Calibrado",       "2023-03-15", 2_100_000,  60, 150_000),
    ("Secadora de Polvo DTF",              "2024-01-10", 1_800_000,  60,  80_000),
]
conn.execute("DELETE FROM equipos")
for e in equipos:
    conn.execute("""INSERT INTO equipos (nombre,fecha_compra,costo_total,vida_util_meses,valor_residual)
                    VALUES (?,?,?,?,?)""", e)
print(f"   {len(equipos)} equipos cargados")

# ── 2. COMPRAS DE INSUMOS ─────────────────────────────────────────────────────
print("→ Cargando compras de insumos...")
conn.execute("DELETE FROM compras")

insumos = conn.execute("SELECT id, nombre, precio_pack, uds_por_pack FROM insumos").fetchall()
insumo_map = {i['nombre']: i for i in insumos}

compras_data = [
    # (nombre_insumo, fecha, packs, descuento%)
    ("Papel Sublimación A4",   "2024-09-01", 5, 0),
    ("Papel Sublimación A4",   "2024-11-15", 8, 0),
    ("Papel Sublimación A4",   "2025-01-20", 6, 0),
    ("Papel Sublimación A4",   "2025-03-05", 4, 0),
    ("Papel Sublimación A3",   "2024-09-01", 3, 0),
    ("Papel Sublimación A3",   "2025-01-20", 4, 0),
    ("Tinta Sublimación CMYK", "2024-09-01", 2, 0),
    ("Tinta Sublimación CMYK", "2024-12-10", 2, 0),
    ("Tinta Sublimación CMYK", "2025-02-18", 1, 0),
    ("Remera Blanca Adulto",   "2024-09-01", 30,0),
    ("Remera Blanca Adulto",   "2024-10-15", 20,0),
    ("Remera Blanca Adulto",   "2024-12-01", 25,0),
    ("Remera Blanca Adulto",   "2025-01-10", 15,0),
    ("Remera Blanca Adulto",   "2025-02-20", 20,0),
    ("Remera Blanca Niño",     "2024-09-01", 15,0),
    ("Remera Blanca Niño",     "2025-01-10", 10,0),
    ("Film DTF A4",            "2024-09-01", 4, 0),
    ("Film DTF A4",            "2024-12-01", 5, 0),
    ("Film DTF A3",            "2024-09-01", 3, 0),
    ("Film DTF A3",            "2025-01-15", 4, 0),
    ("Polvo Adhesivo DTF",     "2024-09-01", 2, 0),
    ("Polvo Adhesivo DTF",     "2025-01-15", 2, 0),
    ("Tinta DTF CMYK+W",       "2024-09-01", 1, 0),
    ("Tinta DTF CMYK+W",       "2024-12-01", 1, 0),
    ("Vinil Imprimible A4",    "2024-09-01", 5, 0),
    ("Vinil Imprimible A4",    "2025-01-20", 5, 0),
    ("Laminado Mate A4",       "2024-09-01", 4, 0),
    ("Laminado Mate A4",       "2025-01-20", 4, 0),
    ("Laminado Brillante A4",  "2024-10-01", 3, 0),
    ("Lienzo Tela 30x40cm",    "2024-09-01", 10,0),
    ("Lienzo Tela 30x40cm",    "2025-01-10", 8, 0),
    ("Lienzo Tela 40x60cm",    "2024-09-01", 6, 0),
    ("Lienzo Tela 60x80cm",    "2024-11-01", 4, 0),
    ("Cinta Sublimación",      "2024-09-01", 4, 0),
    ("Cinta Sublimación",      "2025-02-01", 3, 0),
    ("Papel tissue",           "2024-09-01", 3, 0),
    ("Papel tissue",           "2025-01-01", 3, 0),
    ("Bolsas OPP 30x40",       "2024-09-01", 3, 0),
    ("Bolsas OPP 30x40",       "2025-01-01", 3, 0),
]

for nombre, fecha, packs, desc in compras_data:
    ins = insumo_map.get(nombre)
    if not ins: continue
    uds = packs * ins['uds_por_pack']
    costo = packs * ins['precio_pack'] * (1 - desc/100)
    conn.execute("""INSERT INTO compras (fecha,insumo_id,cantidad_uds,costo_total,proveedor,notas)
                    VALUES (?,?,?,?,?,?)""",
        (fecha, ins['id'], uds, costo, '', f'{packs} pack(s)'))
print(f"   {len(compras_data)} compras de insumos cargadas")

# ── 3. PEDIDOS + ITEMS + CONSUMOS ─────────────────────────────────────────────
print("→ Generando 100 pedidos con ítems y consumos...")
conn.execute("DELETE FROM pedido_items")
conn.execute("DELETE FROM pedidos")
conn.execute("DELETE FROM consumos")

productos = conn.execute("SELECT * FROM productos WHERE activo=1").fetchall()
prod_recetas = {}
for p in productos:
    receta = conn.execute("""SELECT r.insumo_id, r.cantidad FROM recetas r WHERE r.producto_id=?""",
                           (p['id'],)).fetchall()
    prod_recetas[p['id']] = [(r['insumo_id'], r['cantidad']) for r in receta]

# Precios sugeridos aproximados por producto
PRECIOS = {
    "Remera Sublimada Adulto (diseño simple)":  95_000,
    "Remera Sublimada Full Print":             130_000,
    "Sticker Vinil A6 laminado":               18_000,
    "Plancha Stickers A4":                     45_000,
    "Cuadro Sublimado 30x40cm":               165_000,
    "Cuadro Sublimado 40x60cm":               220_000,
    "Transfer DTF A4":                         55_000,
    "Transfer DTF A3 + Aplicado":              80_000,
}

CLIENTES = [
    ("Laura Gómez",     "0981-111001"),("Diego Martínez",  "0982-222002"),
    ("Sofía Benítez",   "0983-333003"),("Carlos Duarte",   "0984-444004"),
    ("Ana Villalba",    "0985-555005"),("Marcos López",    "0986-666006"),
    ("Valentina Ríos",  "0987-777007"),("Fernando Ávalos", "0988-888008"),
    ("Natalia Ortiz",   "0989-999009"),("Rodrigo Sosa",    "0991-101010"),
    ("Camila Torres",   "0992-111111"),("Pablo Zárate",    "0993-222222"),
    ("Lucía Fleitas",   "0994-333333"),("Andrés Rojas",    "0995-444444"),
    ("María Cabrera",   "0996-555555"),("Julio Pereira",   "0997-666666"),
    ("Carla Mendoza",   "0998-777777"),("Héctor Núñez",    "0999-888888"),
]

CANALES = ["Instagram","WhatsApp","Presencial","Instagram","WhatsApp","Instagram"]
TIPOS_CONSUMO_EXTRA = ["PRUEBA","MERMA","CALIBRACIÓN"]

# Distribución mensual realista (crecimiento gradual)
MESES = [
    ("2024-09-01","2024-09-30",  6),
    ("2024-10-01","2024-10-31",  8),
    ("2024-11-01","2024-11-30", 10),
    ("2024-12-01","2024-12-31", 18),  # diciembre pico
    ("2025-01-01","2025-01-31", 14),
    ("2025-02-01","2025-02-28", 16),
    ("2025-03-01","2025-03-20", 14),  # mes actual parcial
]

pedido_n = 1
total_pedidos = 0
total_consumos = 0

for fecha_ini, fecha_fin, cantidad in MESES:
    for _ in range(cantidad):
        cliente, tel = random.choice(CLIENTES)
        canal = random.choice(CANALES)
        fecha_pedido = rnd_fecha_rango(fecha_ini, fecha_fin)

        # 1-3 productos por pedido
        n_prods = random.choices([1,2,3], weights=[60,30,10])[0]
        prods_sel = random.sample(list(productos), min(n_prods, len(productos)))

        items = []
        for p in prods_sel:
            precio_base = PRECIOS.get(p['nombre'], 80_000)
            # Variación ±10% en precio
            precio = round(precio_base * random.uniform(0.90, 1.15) / 1000) * 1000
            cant = random.choices([1,2,3,4], weights=[55,30,10,5])[0]
            items.append((p['id'], p['nombre'], cant, precio))

        total = sum(c * pr for _, _, c, pr in items)
        # Adelanto 50-100%
        adelanto = round(total * random.choice([0.5, 0.6, 0.7, 1.0]) / 1000) * 1000
        adelanto = min(adelanto, total)

        dias_entrega = random.randint(2, 10)
        fecha_entrega = (date.fromisoformat(fecha_pedido) + timedelta(days=dias_entrega)).isoformat()

        # Estado: todos los del pasado > 14 días = Entregado
        dias_desde = (date.today() - date.fromisoformat(fecha_pedido)).days
        if dias_desde > 14:
            estado = "Entregado"
        elif dias_desde > 5:
            estado = random.choice(["En Producción","Listo","Entregado"])
        else:
            estado = random.choice(["Pendiente","En Producción"])

        numero = f"P-{pedido_n:04d}"
        pedido_n += 1

        cur = conn.execute("""INSERT INTO pedidos
            (numero,fecha,cliente,telefono,total,adelanto,fecha_entrega,estado,canal,notas)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (numero, fecha_pedido, cliente, tel, total, adelanto,
             fecha_entrega, estado, canal, ''))
        pid = cur.lastrowid

        for prod_id, prod_nombre, cant, precio in items:
            conn.execute("""INSERT INTO pedido_items (pedido_id,producto_id,descripcion,cantidad,precio_unit)
                            VALUES (?,?,?,?,?)""", (pid, prod_id, prod_nombre, cant, precio))

        # Consumos automáticos si fue entregado
        if estado == "Entregado":
            for prod_id, prod_nombre, cant, precio in items:
                for insumo_id, qty_base in prod_recetas.get(prod_id, []):
                    # Desperdicio aleatorio (80% sin desperdicio, 20% con 1-3 uds extra)
                    extra = 0
                    if random.random() < 0.20:
                        extra = random.randint(1, 3)
                    qty_real = qty_base * cant + extra
                    conn.execute("""INSERT INTO consumos
                        (fecha,tipo,descripcion,pedido_ref,insumo_id,cantidad_base,cantidad_real,notas)
                        VALUES (?,?,?,?,?,?,?,?)""",
                        (fecha_pedido, 'VENTA',
                         f"{prod_nombre} × {cant}", numero,
                         insumo_id, qty_base * cant, qty_real,
                         'Desperdicio incluido' if extra > 0 else ''))
                    total_consumos += 1

        total_pedidos += 1

# ── 4. CONSUMOS NO-VENTA (pruebas, mermas, calibraciones) ─────────────────────
print("→ Generando consumos de pruebas y mermas...")
CONSUMOS_EXTRA = [
    ("2024-09-05", "CALIBRACIÓN", "Ajuste temperatura prensa sublimación", "", 1, 5, 5),
    ("2024-09-05", "CALIBRACIÓN", "Ajuste temperatura prensa sublimación", "", 18, 2, 2),
    ("2024-09-10", "PRUEBA",      "Test papel A4 nuevo proveedor",          "", 1, 10, 10),
    ("2024-10-02", "CALIBRACIÓN", "Calibración impresora DTF nueva",        "", 6, 8, 8),
    ("2024-10-02", "CALIBRACIÓN", "Calibración impresora DTF nueva",        "", 9, 3, 3),
    ("2024-10-15", "PRUEBA",      "Diseño halloween test",                  "", 1, 4, 4),
    ("2024-11-01", "PRUEBA",      "Diseño navidad prueba",                  "", 2, 3, 3),
    ("2024-11-20", "MERMA",       "Lienzo dañado en transporte",            "", 14, 0, 2),
    ("2024-12-01", "PRUEBA",      "Test full print nueva técnica",          "", 2, 6, 6),
    ("2024-12-05", "CALIBRACIÓN", "Recalibración tras cambio tinta DTF",    "", 6, 5, 5),
    ("2024-12-05", "CALIBRACIÓN", "Recalibración tras cambio tinta DTF",    "", 9, 2, 2),
    ("2024-12-10", "MERMA",       "Remeras manchadas por falla prensa",     "", 4, 0, 3),
    ("2025-01-08", "PRUEBA",      "Test vinilo nuevo proveedor",            "", 10, 8, 8),
    ("2025-01-15", "CALIBRACIÓN", "Ajuste corte plotter",                   "", 10, 4, 4),
    ("2025-01-20", "PRUEBA",      "Diseño San Valentín test",               "", 1, 5, 5),
    ("2025-02-01", "MERMA",       "Film DTF defectuoso lote",               "", 7, 0, 10),
    ("2025-02-10", "PRUEBA",      "Test cuadro nuevo formato",              "", 2, 3, 3),
    ("2025-02-14", "MUESTRA",     "Muestra cliente corporativo",            "", 4, 1, 1),
    ("2025-02-14", "MUESTRA",     "Muestra cliente corporativo",            "", 10, 2, 2),
    ("2025-03-01", "CALIBRACIÓN", "Calibración inicio de mes",              "", 1, 3, 3),
    ("2025-03-05", "PRUEBA",      "Diseño nuevo catálogo PIXEL90",          "", 1, 6, 6),
    ("2025-03-10", "MERMA",       "Papel sublimación húmedo",               "", 1, 0, 15),
]

for fecha, tipo, desc, pedido_ref, insumo_idx, base, real in CONSUMOS_EXTRA:
    # insumo_idx es posición en lista de insumos (1-based)
    insumo_id = insumos[insumo_idx - 1]['id'] if insumo_idx <= len(insumos) else insumos[0]['id']
    conn.execute("""INSERT INTO consumos
        (fecha,tipo,descripcion,pedido_ref,insumo_id,cantidad_base,cantidad_real,notas)
        VALUES (?,?,?,?,?,?,?,?)""",
        (fecha, tipo, desc, pedido_ref, insumo_id, base, real, ''))

# ── 5. GASTOS OPERATIVOS ──────────────────────────────────────────────────────
print("→ Generando gastos operativos...")
conn.execute("DELETE FROM gastos")

GASTOS_MENSUALES = [
    # (categoría, descripción, proveedor, forma_pago, monto_base, variación%)
    ("Servicios (luz/internet)", "Electricidad",       "ANDE",         "Débito Auto", 180_000, 10),
    ("Servicios (luz/internet)", "Internet Tigo",      "Tigo",         "Débito Auto",  95_000,  0),
    ("Marketing/Publicidad",     "Pauta Meta Ads",     "Meta",         "Tarjeta",     150_000, 50),
    ("Software/Diseño",          "Adobe CC",           "Adobe",        "Tarjeta",      85_000,  0),
    ("Packaging/Envíos",         "Bolsas + embalaje",  "EmpaquePY",    "Efectivo",     45_000, 20),
]

meses_gastos = [
    "2024-09","2024-10","2024-11","2024-12",
    "2025-01","2025-02","2025-03"
]

for mes in meses_gastos:
    year, month = map(int, mes.split('-'))
    dias_en_mes = [28,29,30,31]
    for cat, desc, prov, pago, monto_base, var_pct in GASTOS_MENSUALES:
        monto = round(monto_base * random.uniform(1 - var_pct/100, 1 + var_pct/100) / 1000) * 1000
        dia = random.randint(1, 28)
        fecha = f"{year}-{month:02d}-{dia:02d}"
        conn.execute("""INSERT INTO gastos (fecha,categoria,descripcion,proveedor,comprobante,forma_pago,monto,notas)
                        VALUES (?,?,?,?,?,?,?,?)""",
            (fecha, cat, f"{desc} — {mes}", prov, '', pago, monto, ''))

# Compras de insumos también como gasto
GASTOS_INSUMOS_EXTRA = [
    ("2024-09-01","Insumos Sublimación","Resma papel A4 × 5",     "PrintShop PY","Efectivo",  425_000),
    ("2024-09-01","Insumos DTF",        "Tinta DTF + Film",        "DTF Paraguay","Transferencia",1_255_000),
    ("2024-09-01","Insumos Sublimación","Remeras adulto × 30",     "TextilPY",    "Efectivo",1_050_000),
    ("2024-10-15","Insumos Sublimación","Remeras adulto × 20",     "TextilPY",    "Efectivo",  700_000),
    ("2024-11-01","Insumos Cuadros",    "Lienzos surtidos",        "ArtStore PY", "Efectivo",  490_000),
    ("2024-11-15","Insumos Sublimación","Resma papel A4 × 8",      "PrintShop PY","Transferencia",680_000),
    ("2024-12-01","Insumos Sublimación","Remeras adulto × 25",     "TextilPY",    "Efectivo",  875_000),
    ("2024-12-01","Insumos DTF",        "Film DTF A3 × 5",         "DTF Paraguay","Transferencia",825_000),
    ("2024-12-10","Insumos Sublimación","Tinta sublimación × 2",   "InkPro",      "Transferencia",360_000),
    ("2025-01-10","Insumos Sublimación","Remeras adulto × 15",     "TextilPY",    "Efectivo",  525_000),
    ("2025-01-15","Insumos DTF",        "Tinta DTF completo",      "DTF Paraguay","Transferencia",350_000),
    ("2025-01-20","Insumos Sublimación","Papel A4 × 6 + A3 × 4",  "PrintShop PY","Efectivo",  800_000),
    ("2025-02-01","Insumos Stickers",   "Vinil + laminado",        "VinilStore",  "Efectivo",  332_000),
    ("2025-02-20","Insumos Sublimación","Remeras adulto × 20",     "TextilPY",    "Efectivo",  700_000),
    ("2025-03-05","Insumos DTF",        "Film DTF A4 × 5 packs",   "DTF Paraguay","Transferencia",475_000),
    ("2025-03-10","Insumos Sublimación","Papel A4 × 4",            "PrintShop PY","Efectivo",  340_000),
    ("2024-10-01","Mantenimiento Equipos","Limpieza cabezal impresora","TecnoService","Efectivo",120_000),
    ("2025-01-05","Mantenimiento Equipos","Repuesto prensa calor", "TecnoService","Efectivo",  85_000),
    ("2025-02-15","Mantenimiento Equipos","Mantenimiento preventivo DTF","TecnoService","Transferencia",200_000),
]

for row in GASTOS_INSUMOS_EXTRA:
    conn.execute("""INSERT INTO gastos (fecha,categoria,descripcion,proveedor,comprobante,forma_pago,monto,notas)
                    VALUES (?,?,?,?,?,?,?,?)""",
        (row[0],row[1],row[2],row[3],'',row[4],row[5],''))

# ── 6. MARKETING ──────────────────────────────────────────────────────────────
print("→ Generando registros de marketing...")
conn.execute("DELETE FROM marketing")

mkt_data = [
    ("2024-09","Instagram", "Posts orgánicos lanzamiento",  0,      0, 850,  210,  6,   570_000),
    ("2024-09","Meta Ads",  "Pauta remeras sublimadas",     100_000, 98_000, 3200, 95, 8,   760_000),
    ("2024-10","Instagram", "Posts + Reel diseños geek",    0,      0,1450,  380, 12,   960_000),
    ("2024-10","Meta Ads",  "Pauta stickers anime",         120_000,115_000,4800, 140, 14, 1_100_000),
    ("2024-10","WhatsApp",  "Difusión catálogo clientes",   0,      0,   0,   95,  8,   640_000),
    ("2024-11","Instagram", "Posts navidad + stories",      0,      0,2100,  520, 18, 1_800_000),
    ("2024-11","Meta Ads",  "Pauta cuadros personalizados", 150_000,148_000,6200,210, 20, 2_100_000),
    ("2024-12","Instagram", "Campaña navidad full",         0,      0,4800, 1200, 35, 4_200_000),
    ("2024-12","Meta Ads",  "Pauta navidad + regalos",      300_000,295_000,12000,380, 42, 5_600_000),
    ("2024-12","WhatsApp",  "Difusión especial navidad",    0,      0,   0,  180, 22, 2_900_000),
    ("2025-01","Instagram", "Posts año nuevo",              0,      0,1800,  420, 15, 1_500_000),
    ("2025-01","Meta Ads",  "Pauta enero remeras",          150_000,142_000,5400,160, 18, 1_800_000),
    ("2025-02","Instagram", "Posts San Valentín",           0,      0,3200,  840, 28, 3_200_000),
    ("2025-02","Meta Ads",  "Pauta San Valentín",           200_000,198_000,8800,260, 30, 3_800_000),
    ("2025-02","WhatsApp",  "Difusión San Valentín",        0,      0,   0,  145, 18, 2_100_000),
    ("2025-03","Instagram", "Posts marzo contenido",        0,      0,2400,  580, 20, 2_400_000),
    ("2025-03","Meta Ads",  "Pauta marzo general",          200_000, 95_000,4200,120, 14, 1_680_000),
]

for row in mkt_data:
    conn.execute("""INSERT INTO marketing
        (mes,plataforma,tipo_campana,presupuesto,gasto_real,alcance,interacciones,
         pedidos_generados,venta_generada,notas)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (row[0],row[1],row[2],row[3],row[4],row[5],row[6],row[7],row[8],''))

conn.commit()
conn.close()

print(f"""
✅ Simulación cargada exitosamente
   ─────────────────────────────
   Equipos:       {len(equipos)}
   Compras:       {len(compras_data)}
   Pedidos:       {total_pedidos}
   Consumos VENTA:{total_consumos}
   Consumos extra:{len(CONSUMOS_EXTRA)}
   Gastos:        {len(GASTOS_MENSUALES)*len(meses_gastos) + len(GASTOS_INSUMOS_EXTRA)}
   Marketing:     {len(mkt_data)}
   ─────────────────────────────
   Período: Sep 2024 → Mar 2025
   Reiniciá la app y abrí el Dashboard
""")
