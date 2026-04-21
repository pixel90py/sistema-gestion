from flask import Flask, jsonify, request, render_template, send_from_directory, Response
from db import get_db, init_db
import os, csv, io
from datetime import datetime, date
from calendar import monthrange
import psycopg2.extras

app = Flask(__name__)
app.config['JSON_ENSURE_ASCII'] = False

# ── manejador de errores global ───────────────────────────────────────────────
@app.errorhandler(Exception)
def handle_error(e):
    import psycopg2.errors as pg
    if isinstance(e, pg.UniqueViolation):
        return jsonify({'error': 'Ya existe un registro con ese nombre o dato único'}), 400
    if isinstance(e, pg.NotNullViolation):
        return jsonify({'error': 'Falta un campo obligatorio'}), 400
    if isinstance(e, pg.ForeignKeyViolation):
        return jsonify({'error': 'El registro referenciado no existe'}), 400
    if isinstance(e, pg.CheckViolation):
        return jsonify({'error': 'El valor ingresado no cumple las restricciones'}), 400
    if isinstance(e, pg.NumericValueOutOfRange):
        return jsonify({'error': 'El valor numérico está fuera de rango'}), 400
    return jsonify({'error': str(e)}), 500

# ── helpers ──────────────────────────────────────────────────────────────────
def get_cursor(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

def fetchall(conn, sql, params=()):
    cur = get_cursor(conn)
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    return rows

def fetchone(conn, sql, params=()):
    cur = get_cursor(conn)
    cur.execute(sql, params)
    row = cur.fetchone()
    cur.close()
    return row

def execute(conn, sql, params=()):
    cur = get_cursor(conn)
    try:
        cur.execute(sql, params)
    except Exception:
        conn.rollback()
        cur.close()
        raise
    lastrow = None
    try:
        lastrow = cur.fetchone()
    except Exception:
        pass
    cur.close()
    return lastrow

def rows_to_list(rows):
    return [dict(r) for r in rows] if rows else []

def stock_actual(conn, insumo_id):
    row = fetchone(conn, "SELECT stock_inicial, uds_por_pack FROM insumos WHERE id=%s", (insumo_id,))
    if not row: return 0
    compras = fetchone(conn, "SELECT COALESCE(SUM(cantidad_uds),0) as total FROM compras WHERE insumo_id=%s", (insumo_id,))['total']
    consumos = fetchone(conn, "SELECT COALESCE(SUM(cantidad_real),0) as total FROM consumos WHERE insumo_id=%s", (insumo_id,))['total']
    return (row['stock_inicial'] or 0) + (compras or 0) - (consumos or 0)

def costo_unit(conn, insumo_id):
    row = fetchone(conn, "SELECT precio_pack, uds_por_pack FROM insumos WHERE id=%s", (insumo_id,))
    if not row or not row['uds_por_pack']: return 0
    return (row['precio_pack'] or 0) / row['uds_por_pack']

def amort_mensual(conn):
    equipos = fetchall(conn, "SELECT costo_total, vida_util_meses, valor_residual FROM equipos WHERE activo=1")
    return sum((e['costo_total'] - e['valor_residual']) / max(e['vida_util_meses'], 1) for e in equipos)

def param(conn, key, default=0):
    row = fetchone(conn, "SELECT valor FROM parametros WHERE clave=%s", (key,))
    try: return float(row['valor']) if row else default
    except: return default

def now_iso():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def insert_returning_id(conn, sql, params=()):
    """Ejecuta un INSERT ... RETURNING id y devuelve el id generado."""
    cur = get_cursor(conn)
    cur.execute(sql, params)
    row = cur.fetchone()
    cur.close()
    return row['id'] if row else None

# ── static ────────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/static/img/<path:filename>')
def serve_img(filename):
    return send_from_directory(os.path.join(app.root_path, 'static', 'img'), filename)

# ── DASHBOARD ─────────────────────────────────────────────────────────────────
@app.route('/api/dashboard')
def api_dashboard():
    conn = get_db()
    hoy = date.today()

    mes_ref_row = fetchone(conn, """
    SELECT TO_CHAR(MAX(fecha::date), 'YYYY-MM') as ultimo_mes
    FROM pedidos WHERE estado != 'Cancelado'
""")

    if mes_ref_row and mes_ref_row['ultimo_mes']:
        y_ref, m_ref = map(int, mes_ref_row['ultimo_mes'].split('-'))
        ref = date(y_ref, m_ref, 1)
    else:
        ref = hoy

    mes_ini = f"{ref.year}-{ref.month:02d}-01"
    mes_fin = f"{ref.year}-{ref.month:02d}-{monthrange(ref.year, ref.month)[1]}"

    ventas_mes = fetchone(conn, """
        SELECT COALESCE(SUM(pi.cantidad * pi.precio_unit),0) as total
        FROM pedidos p
        JOIN pedido_items pi ON pi.pedido_id = p.id
        WHERE p.fecha BETWEEN %s AND %s AND p.estado != 'Cancelado'
    """, (mes_ini, mes_fin))['total']

    gastos_mes = fetchone(conn, """
        SELECT COALESCE(SUM(monto),0) as total
        FROM gastos WHERE fecha BETWEEN %s AND %s
    """, (mes_ini, mes_fin))['total']

    pedidos_mes = fetchone(conn, """
        SELECT COUNT(*) as total FROM pedidos
        WHERE fecha BETWEEN %s AND %s AND estado != 'Cancelado'
    """, (mes_ini, mes_fin))['total']

    pendientes = fetchone(conn, """
        SELECT COUNT(*) as total FROM pedidos
        WHERE estado IN ('Pendiente','En Producción')
    """)['total']

    insumos = fetchall(conn, "SELECT id, nombre, stock_minimo FROM insumos WHERE activo=1")
    alertas = []
    for ins in insumos:
        s = stock_actual(conn, ins['id'])
        if s <= ins['stock_minimo']:
            alertas.append({'nombre': ins['nombre'], 'stock': round(s, 2), 'minimo': ins['stock_minimo']})

    por_cat = fetchall(conn, """
        SELECT pr.categoria, COALESCE(SUM(pi.cantidad * pi.precio_unit),0) as total
        FROM pedidos p
        JOIN pedido_items pi ON pi.pedido_id = p.id
        JOIN productos pr ON pr.id = pi.producto_id
        WHERE p.fecha BETWEEN %s AND %s AND p.estado != 'Cancelado'
        GROUP BY pr.categoria ORDER BY total DESC
    """, (mes_ini, mes_fin))

    meses_data = []
    for i in range(5, -1, -1):
        m = ref.month - i
        y = ref.year
        while m <= 0:
            m += 12; y -= 1
        ini = f"{y}-{m:02d}-01"
        fin = f"{y}-{m:02d}-{monthrange(y, m)[1]}"
        v = fetchone(conn, """
            SELECT COALESCE(SUM(pi.cantidad * pi.precio_unit),0) as total
            FROM pedidos p JOIN pedido_items pi ON pi.pedido_id = p.id
            WHERE p.fecha BETWEEN %s AND %s AND p.estado != 'Cancelado'
        """, (ini, fin))['total']
        g = fetchone(conn, "SELECT COALESCE(SUM(monto),0) as total FROM gastos WHERE fecha BETWEEN %s AND %s", (ini, fin))['total']
        meses_data.append({'mes': f"{y}-{m:02d}", 'ventas': v, 'gastos': g})

    ganancia = ventas_mes - gastos_mes
    margen = (ganancia / ventas_mes * 100) if ventas_mes > 0 else 0
    conn.close()

    return jsonify({
        'ventas_mes': ventas_mes, 'gastos_mes': gastos_mes,
        'ganancia': ganancia, 'margen': round(margen, 1),
        'pedidos_mes': pedidos_mes, 'pendientes': pendientes,
        'alertas': alertas, 'por_categoria': rows_to_list(por_cat),
        'historico': meses_data,
        'mes_referencia': f"{ref.year}-{ref.month:02d}",
    })

# ── ALERTAS COUNT ─────────────────────────────────────────────────────────────
@app.route('/api/alertas_count')
def api_alertas_count():
    conn = get_db()
    insumos = fetchall(conn, "SELECT id, stock_minimo FROM insumos WHERE activo=1")
    count = sum(1 for ins in insumos if stock_actual(conn, ins['id']) <= ins['stock_minimo'])
    stock_count = fetchone(conn, "SELECT COUNT(*) as total FROM stock_reingreso WHERE estado='Disponible'")['total']
    conn.close()
    return jsonify({'count': count, 'stock_count': stock_count})

# ── INSUMOS ───────────────────────────────────────────────────────────────────
@app.route('/api/insumos', methods=['GET'])
def api_insumos():
    conn = get_db()
    insumos = fetchall(conn, "SELECT * FROM insumos WHERE activo=1 ORDER BY categoria, nombre")
    result = []
    for ins in insumos:
        d = dict(ins)
        d['stock_actual'] = round(stock_actual(conn, ins['id']), 2)
        d['costo_unitario'] = round(costo_unit(conn, ins['id']), 0)
        d['alerta'] = d['stock_actual'] <= (ins['stock_minimo'] or 0)
        result.append(d)
    conn.close()
    return jsonify(result)

@app.route('/api/insumos', methods=['POST'])
def api_insumos_post():
    d = request.json; conn = get_db()
    execute(conn, """INSERT INTO insumos
        (nombre,categoria,proveedor,unidad_compra,uds_por_pack,precio_pack,unidad_consum,stock_inicial,stock_minimo)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (d['nombre'], d['categoria'], d.get('proveedor',''), d.get('unidad_compra',''),
         float(d.get('uds_por_pack',1)), float(d.get('precio_pack',0)),
         d.get('unidad_consum',''), float(d.get('stock_inicial',0)), float(d.get('stock_minimo',0))))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/insumos/<int:iid>', methods=['PUT'])
def api_insumos_put(iid):
    d = request.json; conn = get_db()
    execute(conn, """UPDATE insumos SET nombre=%s,categoria=%s,proveedor=%s,unidad_compra=%s,
        uds_por_pack=%s,precio_pack=%s,unidad_consum=%s,stock_inicial=%s,stock_minimo=%s WHERE id=%s""",
        (d['nombre'], d['categoria'], d.get('proveedor',''), d.get('unidad_compra',''),
         float(d.get('uds_por_pack',1)), float(d.get('precio_pack',0)),
         d.get('unidad_consum',''), float(d.get('stock_inicial',0)), float(d.get('stock_minimo',0)), iid))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/insumos/<int:iid>', methods=['DELETE'])
def api_insumos_del(iid):
    conn = get_db()
    execute(conn, "UPDATE insumos SET activo=0 WHERE id=%s", (iid,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

# ── COMPRAS ───────────────────────────────────────────────────────────────────
@app.route('/api/compras', methods=['POST'])
def api_compras_post():
    d = request.json; conn = get_db()
    execute(conn, "INSERT INTO compras (fecha,insumo_id,cantidad_uds,costo_total,proveedor,notas) VALUES (%s,%s,%s,%s,%s,%s)",
        (d['fecha'], d['insumo_id'], float(d['cantidad_uds']),
         float(d.get('costo_total',0)), d.get('proveedor',''), d.get('notas','')))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

# ── CONSUMOS ──────────────────────────────────────────────────────────────────
@app.route('/api/consumos', methods=['GET'])
def api_consumos():
    conn = get_db()
    rows = fetchall(conn, """
        SELECT c.*, i.nombre as insumo_nombre, i.unidad_consum,
            ROUND(c.cantidad_real * (i.precio_pack / GREATEST(i.uds_por_pack,1))) as costo_total
        FROM consumos c LEFT JOIN insumos i ON i.id = c.insumo_id
        ORDER BY c.fecha DESC, c.id DESC LIMIT 200""")
    conn.close()
    return jsonify(rows_to_list(rows))

@app.route('/api/consumos', methods=['POST'])
def api_consumos_post():
    d = request.json; conn = get_db()
    execute(conn, "INSERT INTO consumos (fecha,tipo,descripcion,pedido_ref,insumo_id,cantidad_base,cantidad_real,notas) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (d['fecha'], d['tipo'], d.get('descripcion',''), d.get('pedido_ref',''),
         d.get('insumo_id'), float(d.get('cantidad_base',0)), float(d.get('cantidad_real',0)), d.get('notas','')))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/consumos/<int:cid>', methods=['DELETE'])
def api_consumos_del(cid):
    conn = get_db()
    execute(conn, "DELETE FROM consumos WHERE id=%s", (cid,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

# ── PRODUCTOS & RECETAS ───────────────────────────────────────────────────────
@app.route('/api/productos', methods=['GET'])
def api_productos():
    conn = get_db()
    prods = fetchall(conn, "SELECT * FROM productos WHERE activo=1 ORDER BY categoria,nombre")
    result = []
    for p in prods:
        d = dict(p)
        recetas = fetchall(conn, """
            SELECT r.*, i.nombre as insumo_nombre, i.unidad_consum,
                ROUND(i.precio_pack / GREATEST(i.uds_por_pack,1)) as costo_unit
            FROM recetas r JOIN insumos i ON i.id = r.insumo_id WHERE r.producto_id=%s
        """, (p['id'],))
        d['receta'] = rows_to_list(recetas)
        try:
            horas_mes = param(conn,'horas_mes',160); sueldo = param(conn,'sueldo_mensual',3500000)
            g_fijos = param(conn,'gastos_fijos',800000); ventas_e = param(conn,'ventas_estimadas_mes',80)
            margen = param(conn,'margen_deseado',0.35); impuestos = param(conn,'impuestos',0.10)
            costo_mat = sum(r['cantidad'] * r['costo_unit'] for r in recetas)
            mano_obra = 0.5 * (sueldo / max(horas_mes,1))
            gasto_unit = g_fijos / max(ventas_e,1); amort_unit = amort_mensual(conn) / max(ventas_e,1)
            costo_tot = costo_mat + mano_obra + gasto_unit + amort_unit
            precio_min = costo_tot / (1 - margen) if margen < 1 else costo_tot
            d['precio_sugerido'] = round(precio_min * (1 + impuestos))
        except:
            d['precio_sugerido'] = 0
        result.append(d)
    conn.close()
    return jsonify(result)

@app.route('/api/productos', methods=['POST'])
def api_productos_post():
    d = request.json; conn = get_db()
    pid = insert_returning_id(conn,
        "INSERT INTO productos (nombre,categoria) VALUES (%s,%s) RETURNING id",
        (d['nombre'], d['categoria']))
    for item in d.get('receta', []):
        execute(conn, """INSERT INTO recetas (producto_id,insumo_id,cantidad) VALUES (%s,%s,%s)
            ON CONFLICT (producto_id,insumo_id) DO UPDATE SET cantidad=EXCLUDED.cantidad""",
            (pid, item['insumo_id'], float(item['cantidad'])))
    conn.commit(); conn.close()
    return jsonify({'ok': True, 'id': pid})

@app.route('/api/productos/<int:pid>/receta', methods=['PUT'])
def api_receta_put(pid):
    items = request.json; conn = get_db()
    execute(conn, "DELETE FROM recetas WHERE producto_id=%s", (pid,))
    for item in items:
        if float(item.get('cantidad', 0)) > 0:
            execute(conn, "INSERT INTO recetas (producto_id,insumo_id,cantidad) VALUES (%s,%s,%s)",
                (pid, item['insumo_id'], float(item['cantidad'])))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/costo_producto/<int:pid>')
def api_costo_producto(pid):
    conn = get_db()
    horas_mes = param(conn,'horas_mes',160); sueldo = param(conn,'sueldo_mensual',3500000)
    g_fijos = param(conn,'gastos_fijos',800000); ventas_e = param(conn,'ventas_estimadas_mes',80)
    margen = param(conn,'margen_deseado',0.35); impuestos = param(conn,'impuestos',0.10)
    recetas = fetchall(conn, """
        SELECT r.cantidad, i.precio_pack, i.uds_por_pack
        FROM recetas r JOIN insumos i ON i.id = r.insumo_id WHERE r.producto_id=%s
    """, (pid,))
    costo_mat = sum(r['cantidad'] * (r['precio_pack'] / max(r['uds_por_pack'],1)) for r in recetas)
    mano_obra = 0.5 * (sueldo / max(horas_mes, 1))
    gasto_unit = g_fijos / max(ventas_e, 1)
    amort_unit = amort_mensual(conn) / max(ventas_e, 1)
    costo_total = costo_mat + mano_obra + gasto_unit + amort_unit
    precio_min = costo_total / (1 - margen) if margen < 1 else costo_total
    precio_sug = precio_min * (1 + impuestos)
    conn.close()
    return jsonify({
        'costo_materiales': round(costo_mat), 'mano_obra': round(mano_obra),
        'gasto_fijo': round(gasto_unit), 'amortizacion': round(amort_unit),
        'costo_total': round(costo_total), 'precio_minimo': round(precio_min),
        'precio_sugerido': round(precio_sug),
    })

# ── CLIENTES ─────────────────────────────────────────────────────────────────
@app.route('/api/clientes', methods=['GET'])
def api_clientes():
    conn = get_db()
    rows = fetchall(conn, "SELECT * FROM clientes WHERE activo=1 ORDER BY nombre, apellido")
    conn.close()
    return jsonify(rows_to_list(rows))

@app.route('/api/clientes', methods=['POST'])
def api_clientes_post():
    d = request.json; conn = get_db()
    cid = insert_returning_id(conn, """
        INSERT INTO clientes (nombre,apellido,tipo_documento,numero_documento,telefono,email,direccion,ciudad,fecha_creacion)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (d['nombre'], d.get('apellido',''), d.get('tipo_documento','CI'),
         d.get('numero_documento',''), d.get('telefono',''), d.get('email',''),
         d.get('direccion',''), d.get('ciudad',''), date.today().isoformat()))
    conn.commit(); conn.close()
    return jsonify({'ok': True, 'id': cid})

@app.route('/api/clientes/<int:cid>', methods=['PUT'])
def api_clientes_put(cid):
    d = request.json; conn = get_db()
    execute(conn, """UPDATE clientes SET nombre=%s,apellido=%s,tipo_documento=%s,numero_documento=%s,
        telefono=%s,email=%s,direccion=%s,ciudad=%s WHERE id=%s""",
        (d['nombre'], d.get('apellido',''), d.get('tipo_documento','CI'),
         d.get('numero_documento',''), d.get('telefono',''), d.get('email',''),
         d.get('direccion',''), d.get('ciudad',''), cid))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/clientes/<int:cid>', methods=['DELETE'])
def api_clientes_del(cid):
    conn = get_db()
    execute(conn, "UPDATE clientes SET activo=0 WHERE id=%s", (cid,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/clientes/buscar')
def api_clientes_buscar():
    q = request.args.get('q', ''); conn = get_db()
    rows = fetchall(conn, """SELECT * FROM clientes WHERE activo=1
        AND (nombre ILIKE %s OR apellido ILIKE %s OR numero_documento ILIKE %s) LIMIT 10""",
        (f'%{q}%', f'%{q}%', f'%{q}%'))
    conn.close()
    return jsonify(rows_to_list(rows))

# ── PEDIDOS ───────────────────────────────────────────────────────────────────
@app.route('/api/pedidos', methods=['GET'])
def api_pedidos():
    conn = get_db()
    estado = request.args.get('estado')
    if estado:
        pedidos = fetchall(conn, "SELECT * FROM pedidos WHERE estado=%s ORDER BY fecha DESC, id DESC LIMIT 200", (estado,))
    else:
        pedidos = fetchall(conn, "SELECT * FROM pedidos ORDER BY fecha DESC, id DESC LIMIT 200")
    result = []
    for p in pedidos:
        d = dict(p)
        items = fetchall(conn, """SELECT pi.*, pr.nombre as producto_nombre
            FROM pedido_items pi LEFT JOIN productos pr ON pr.id = pi.producto_id
            WHERE pi.pedido_id=%s""", (p['id'],))
        d['items'] = rows_to_list(items)
        cuotas = fetchall(conn, "SELECT * FROM pedido_cuotas WHERE pedido_id=%s ORDER BY numero_cuota", (p['id'],))
        if cuotas:
            total_pagado = sum(c['monto_pagado'] for c in cuotas)
            d['saldo'] = (d['total'] or 0) - total_pagado
            d['cuotas_data'] = rows_to_list(cuotas)
        else:
            d['saldo'] = (d['total'] or 0) - (d['adelanto'] or 0)
            d['cuotas_data'] = []
        if d.get('cliente_id'):
            cli = fetchone(conn, "SELECT * FROM clientes WHERE id=%s", (d['cliente_id'],))
            if cli: d['cliente_info'] = dict(cli)
        result.append(d)
    conn.close()
    return jsonify(result)

@app.route('/api/pedidos', methods=['POST'])
def api_pedidos_post():
    d = request.json; conn = get_db()
    ultimo = fetchone(conn, "SELECT numero FROM pedidos ORDER BY id DESC LIMIT 1")
    if ultimo and ultimo['numero']:
        try: n = int(ultimo['numero'].replace('P-','')) + 1
        except: n = 1
    else: n = 1
    numero = f"P-{n:04d}"
    pid = insert_returning_id(conn, """
        INSERT INTO pedidos (numero,fecha,cliente_id,cliente,telefono,total,adelanto,cuotas,
            fecha_entrega,estado,canal,modelo_seguir,notas)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (numero, d['fecha'], d.get('cliente_id'), d.get('cliente',''), d.get('telefono',''),
         float(d.get('total',0)), float(d.get('adelanto',0)), int(d.get('cuotas',1)),
         d.get('fecha_entrega',''), d.get('estado','Pendiente'),
         d.get('canal',''), d.get('modelo_seguir',''), d.get('notas','')))
    for item in d.get('items', []):
        execute(conn, "INSERT INTO pedido_items (pedido_id,producto_id,descripcion,cantidad,precio_unit) VALUES (%s,%s,%s,%s,%s)",
            (pid, item.get('producto_id'), item.get('descripcion',''),
             float(item.get('cantidad',1)), float(item.get('precio_unit',0))))
    num_cuotas = int(d.get('cuotas', 1)); total = float(d.get('total', 0))
    if num_cuotas > 1:
        monto_cuota = round(total / num_cuotas)
        for i in range(1, num_cuotas + 1):
            execute(conn, "INSERT INTO pedido_cuotas (pedido_id,numero_cuota,monto_esperado) VALUES (%s,%s,%s)",
                (pid, i, monto_cuota))
    elif num_cuotas == 1:
        adelanto = float(d.get('adelanto',0))
        execute(conn, "INSERT INTO pedido_cuotas (pedido_id,numero_cuota,monto_esperado,monto_pagado,pagada) VALUES (%s,%s,%s,%s,%s)",
            (pid, 1, total, adelanto, 1 if adelanto >= total else 0))
    execute(conn, "INSERT INTO pedido_estado_historial (pedido_id,estado,fecha_hora) VALUES (%s,%s,%s)",
        (pid, d.get('estado','Pendiente'), now_iso()))
    conn.commit(); conn.close()
    return jsonify({'ok': True, 'numero': numero, 'id': pid})

@app.route('/api/pedidos/<int:pid>/consumos_registrados')
def api_pedido_consumos_check(pid):
    conn = get_db()
    p = fetchone(conn, "SELECT numero FROM pedidos WHERE id=%s", (pid,))
    if not p: conn.close(); return jsonify({'registrados': False})
    count = fetchone(conn, "SELECT COUNT(*) as total FROM consumos WHERE pedido_ref=%s AND tipo='VENTA'", (p['numero'],))['total']
    conn.close()
    return jsonify({'registrados': count > 0, 'cantidad': count})

@app.route('/api/pedidos/<int:pid>', methods=['PUT'])
def api_pedidos_put(pid):
    d = request.json; conn = get_db()
    old = fetchone(conn, "SELECT estado FROM pedidos WHERE id=%s", (pid,))
    execute(conn, """UPDATE pedidos SET cliente=%s,cliente_id=%s,telefono=%s,total=%s,adelanto=%s,cuotas=%s,
        fecha_entrega=%s,estado=%s,canal=%s,modelo_seguir=%s,notas=%s,
        solicita_factura=%s,factura_razon=%s,factura_ruc=%s,factura_email=%s,factura_tel=%s,factura_dir=%s WHERE id=%s""",
        (d.get('cliente',''), d.get('cliente_id'), d.get('telefono',''),
         float(d.get('total',0)), float(d.get('adelanto',0)), int(d.get('cuotas',1)),
         d.get('fecha_entrega',''), d.get('estado','Pendiente'),
         d.get('canal',''), d.get('modelo_seguir',''), d.get('notas',''),
         int(d.get('solicita_factura',0)), d.get('factura_razon',''),
         d.get('factura_ruc',''), d.get('factura_email',''),
         d.get('factura_tel',''), d.get('factura_dir',''), pid))
    new_estado = d.get('estado','Pendiente')
    if old and old['estado'] != new_estado:
        execute(conn, "INSERT INTO pedido_estado_historial (pedido_id,estado,fecha_hora) VALUES (%s,%s,%s)",
            (pid, new_estado, now_iso()))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/pedidos/<int:pid>/cuotas', methods=['GET'])
def api_pedido_cuotas(pid):
    conn = get_db()
    rows = fetchall(conn, "SELECT * FROM pedido_cuotas WHERE pedido_id=%s ORDER BY numero_cuota", (pid,))
    conn.close()
    return jsonify(rows_to_list(rows))

@app.route('/api/pedidos/<int:pid>/cuotas', methods=['PUT'])
def api_pedido_cuotas_put(pid):
    data = request.json; conn = get_db()
    for c in data:
        execute(conn, "UPDATE pedido_cuotas SET monto_pagado=%s,pagada=%s,fecha_pago=%s WHERE id=%s",
            (float(c.get('monto_pagado',0)), int(c.get('pagada',0)), c.get('fecha_pago',''), c['id']))
    total_paid = sum(float(c.get('monto_pagado',0)) for c in data)
    execute(conn, "UPDATE pedidos SET adelanto=%s WHERE id=%s", (total_paid, pid))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/pedidos/<int:pid>/historial')
def api_pedido_historial(pid):
    conn = get_db()
    rows = fetchall(conn, "SELECT * FROM pedido_estado_historial WHERE pedido_id=%s ORDER BY fecha_hora", (pid,))
    conn.close()
    return jsonify(rows_to_list(rows))

@app.route('/api/pedidos/<int:pid>/reingreso', methods=['POST'])
def api_pedido_reingreso(pid):
    d = request.json; conn = get_db()
    p = fetchone(conn, "SELECT numero, total FROM pedidos WHERE id=%s", (pid,))
    if not p: conn.close(); return jsonify({'error': 'Pedido no encontrado'}), 404
    execute(conn, """INSERT INTO stock_reingreso (pedido_id,pedido_numero,producto_id,descripcion,cantidad,valor_unit,motivo,fecha)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        (pid, p['numero'], d.get('producto_id'), d.get('descripcion',''),
         float(d.get('cantidad',1)), float(d.get('valor_unit',0)),
         d.get('motivo',''), date.today().isoformat()))
    execute(conn, "UPDATE pedidos SET estado='Reingreso' WHERE id=%s", (pid,))
    execute(conn, "INSERT INTO pedido_estado_historial (pedido_id,estado,fecha_hora) VALUES (%s,%s,%s)",
        (pid, 'Reingreso', now_iso()))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

# ── STOCK REINGRESO ──────────────────────────────────────────────────────────
@app.route('/api/stock_reingreso', methods=['GET'])
def api_stock_reingreso():
    conn = get_db()
    rows = fetchall(conn, """SELECT s.*, p.nombre as producto_nombre
        FROM stock_reingreso s LEFT JOIN productos p ON p.id = s.producto_id
        ORDER BY s.fecha DESC""")
    conn.close()
    return jsonify(rows_to_list(rows))

@app.route('/api/stock_reingreso', methods=['POST'])
def api_stock_reingreso_post():
    d = request.json; conn = get_db()
    execute(conn, """INSERT INTO stock_reingreso (pedido_id,pedido_numero,producto_id,descripcion,cantidad,valor_unit,motivo,fecha,estado)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (None, None, d.get('producto_id'), d.get('descripcion',''),
         float(d.get('cantidad',1)), float(d.get('valor_unit',0)),
         d.get('motivo','Producción para stock'), date.today().isoformat(), 'Disponible'))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/stock_reingreso/<int:sid>', methods=['PUT'])
def api_stock_reingreso_put(sid):
    d = request.json; conn = get_db()
    execute(conn, "UPDATE stock_reingreso SET estado=%s WHERE id=%s", (d.get('estado','Disponible'), sid))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/stock_reingreso/<int:sid>/salida', methods=['POST'])
def api_stock_salida(sid):
    d = request.json; conn = get_db()
    item = fetchone(conn, "SELECT * FROM stock_reingreso WHERE id=%s", (sid,))
    if not item: conn.close(); return jsonify({'error': 'No encontrado'}), 404
    is_stock_new = item['pedido_id'] is None
    prefix = 'S' if is_stock_new else 'P'
    ultimo = fetchone(conn, f"SELECT numero FROM pedidos WHERE numero LIKE '{prefix}-%' ORDER BY id DESC LIMIT 1")
    if ultimo and ultimo['numero']:
        try: n = int(ultimo['numero'].replace(f'{prefix}-','')) + 1
        except: n = 1
    else: n = 1
    numero = f"{prefix}-{n:04d}"
    monto = float(d.get('monto', item['valor_unit'] * item['cantidad']))
    estado_pedido = 'Entregado (R)' if not is_stock_new else 'Entregado'
    pid = insert_returning_id(conn, """
        INSERT INTO pedidos (numero,fecha,cliente_id,cliente,telefono,total,adelanto,cuotas,estado,canal,notas)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (numero, date.today().isoformat(), d.get('cliente_id'), d.get('cliente',''),
         d.get('telefono',''), monto, monto, 1, estado_pedido, 'Stock', f"Salida de stock #{sid}"))
    execute(conn, "INSERT INTO pedido_items (pedido_id,producto_id,descripcion,cantidad,precio_unit) VALUES (%s,%s,%s,%s,%s)",
        (pid, item['producto_id'], item['descripcion'] or '', item['cantidad'], float(d.get('monto', item['valor_unit']))))
    execute(conn, "INSERT INTO pedido_estado_historial (pedido_id,estado,fecha_hora) VALUES (%s,%s,%s)",
        (pid, estado_pedido, now_iso()))
    execute(conn, "UPDATE stock_reingreso SET estado='Vendido' WHERE id=%s", (sid,))
    conn.commit(); conn.close()
    return jsonify({'ok': True, 'numero': numero})

# ── GASTOS ────────────────────────────────────────────────────────────────────
@app.route('/api/gastos', methods=['GET'])
def api_gastos():
    conn = get_db()
    mes = request.args.get('mes')
    if mes:
        rows = fetchall(conn, "SELECT * FROM gastos WHERE TO_CHAR(fecha::date,'YYYY-MM')=%s ORDER BY fecha DESC", (mes,))
    else:
        rows = fetchall(conn, "SELECT * FROM gastos ORDER BY fecha DESC LIMIT 200")
    conn.close()
    return jsonify(rows_to_list(rows))

@app.route('/api/gastos', methods=['POST'])
def api_gastos_post():
    d = request.json; conn = get_db()
    execute(conn, """INSERT INTO gastos (fecha,categoria,descripcion,proveedor,comprobante,forma_pago,monto,tipo_recurrencia,notas)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (d['fecha'], d['categoria'], d.get('descripcion',''), d.get('proveedor',''),
         d.get('comprobante',''), d.get('forma_pago',''), float(d.get('monto',0)),
         d.get('tipo_recurrencia','Único'), d.get('notas','')))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/gastos/<int:gid>', methods=['PUT'])
def api_gastos_put(gid):
    d = request.json; conn = get_db()
    execute(conn, """UPDATE gastos SET fecha=%s,categoria=%s,descripcion=%s,proveedor=%s,comprobante=%s,
        forma_pago=%s,monto=%s,tipo_recurrencia=%s,notas=%s WHERE id=%s""",
        (d['fecha'], d['categoria'], d.get('descripcion',''), d.get('proveedor',''),
         d.get('comprobante',''), d.get('forma_pago',''), float(d.get('monto',0)),
         d.get('tipo_recurrencia','Único'), d.get('notas',''), gid))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/gastos/<int:gid>', methods=['DELETE'])
def api_gastos_del(gid):
    conn = get_db()
    execute(conn, "DELETE FROM gastos WHERE id=%s", (gid,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

# ── MARKETING ─────────────────────────────────────────────────────────────────
@app.route('/api/marketing', methods=['GET'])
def api_marketing():
    conn = get_db()
    rows = fetchall(conn, "SELECT * FROM marketing ORDER BY mes DESC")
    conn.close()
    return jsonify(rows_to_list(rows))

@app.route('/api/marketing', methods=['POST'])
def api_marketing_post():
    d = request.json; conn = get_db()
    execute(conn, """INSERT INTO marketing (mes,plataforma,tipo_campana,presupuesto,gasto_real,alcance,interacciones,pedidos_generados,venta_generada,notas)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (d['mes'], d['plataforma'], d.get('tipo_campana',''),
         float(d.get('presupuesto',0)), float(d.get('gasto_real',0)),
         int(d.get('alcance',0)), int(d.get('interacciones',0)),
         int(d.get('pedidos_generados',0)), float(d.get('venta_generada',0)), d.get('notas','')))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/marketing/<int:mid>', methods=['PUT'])
def api_marketing_put(mid):
    d = request.json; conn = get_db()
    execute(conn, """UPDATE marketing SET mes=%s,plataforma=%s,tipo_campana=%s,presupuesto=%s,gasto_real=%s,
        alcance=%s,interacciones=%s,pedidos_generados=%s,venta_generada=%s,notas=%s WHERE id=%s""",
        (d['mes'], d['plataforma'], d.get('tipo_campana',''),
         float(d.get('presupuesto',0)), float(d.get('gasto_real',0)),
         int(d.get('alcance',0)), int(d.get('interacciones',0)),
         int(d.get('pedidos_generados',0)), float(d.get('venta_generada',0)), d.get('notas',''), mid))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/marketing/<int:mid>', methods=['DELETE'])
def api_marketing_del(mid):
    conn = get_db()
    execute(conn, "DELETE FROM marketing WHERE id=%s", (mid,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

# ── CATEGORÍAS ────────────────────────────────────────────────────────────────
@app.route('/api/categorias', methods=['GET'])
def api_categorias():
    conn = get_db()
    from_insumos   = [r['categoria'] for r in fetchall(conn, "SELECT categoria FROM insumos WHERE categoria IS NOT NULL ORDER BY categoria")]
    from_productos = [r['categoria'] for r in fetchall(conn, "SELECT categoria FROM productos WHERE categoria IS NOT NULL ORDER BY categoria")]
    custom = [r['valor'] for r in fetchall(conn, "SELECT valor FROM categorias WHERE valor IS NOT NULL ORDER BY orden")]
    all_cats = list(dict.fromkeys(from_insumos + from_productos + custom))
    conn.close()
    return jsonify(all_cats)

@app.route('/api/categorias', methods=['POST'])
def api_categorias_post():
    d = request.json; conn = get_db()
    try:
        execute(conn, """CREATE TABLE IF NOT EXISTS categorias
            (id SERIAL PRIMARY KEY, valor TEXT UNIQUE, orden INTEGER DEFAULT 0)""")
        execute(conn, "INSERT INTO categorias (valor, orden) VALUES (%s,%s) ON CONFLICT (valor) DO NOTHING", (d['valor'], 999))
        conn.commit()
    except: pass
    conn.close()
    return jsonify({'ok': True})

# ── PARÁMETROS ────────────────────────────────────────────────────────────────
@app.route('/api/parametros', methods=['GET'])
def api_parametros():
    conn = get_db()
    rows = fetchall(conn, "SELECT * FROM parametros")
    conn.close()
    return jsonify({r['clave']: r['valor'] for r in rows})

@app.route('/api/parametros', methods=['PUT'])
def api_parametros_put():
    d = request.json; conn = get_db()
    for k, v in d.items():
        execute(conn, """INSERT INTO parametros (clave,valor) VALUES (%s,%s)
            ON CONFLICT (clave) DO UPDATE SET valor=EXCLUDED.valor""", (k, str(v)))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

# ── PRÉSTAMOS ─────────────────────────────────────────────────────────────────
@app.route('/api/prestamos', methods=['GET'])
def api_prestamos():
    conn = get_db()
    rows = fetchall(conn, "SELECT * FROM prestamos WHERE activo=1 ORDER BY fecha_inicio DESC")
    result = []
    for p in rows:
        d = dict(p)
        d['cuotas_pagadas'] = d.get('cuotas_pagadas', 0) or 0
        d['cuotas_restantes'] = max(p['cuotas'] - d['cuotas_pagadas'], 0)
        d['saldo_pendiente'] = round(d['cuotas_restantes'] * (p['cuota_mensual'] or 0))
        pct = (d['cuotas_pagadas'] / p['cuotas'] * 100) if p['cuotas'] else 0
        d['progreso_pct'] = round(pct, 1)
        result.append(d)
    conn.close()
    return jsonify(result)

@app.route('/api/prestamos', methods=['POST'])
def api_prestamos_post():
    d = request.json; conn = get_db()
    monto = float(d.get('monto_total', 0)); cuotas = int(d.get('cuotas', 12))
    cuota_m = round(monto / cuotas) if cuotas else 0
    execute(conn, """INSERT INTO prestamos
        (descripcion,monto_total,monto_adjudicado,cuotas,cuotas_pagadas,plazo_meses,fecha_inicio,fecha_fin,cuota_mensual,entidad,notas)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (d['descripcion'], monto, float(d.get('monto_adjudicado', monto)),
         cuotas, int(d.get('cuotas_pagadas', 0)), int(d.get('plazo_meses', cuotas)),
         d.get('fecha_inicio',''), d.get('fecha_fin',''),
         float(d.get('cuota_mensual', cuota_m)), d.get('entidad',''), d.get('notas','')))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/prestamos/<int:pid>', methods=['PUT'])
def api_prestamos_put(pid):
    d = request.json; conn = get_db()
    execute(conn, """UPDATE prestamos SET descripcion=%s,monto_total=%s,monto_adjudicado=%s,cuotas=%s,cuotas_pagadas=%s,
        plazo_meses=%s,fecha_inicio=%s,fecha_fin=%s,cuota_mensual=%s,entidad=%s,notas=%s WHERE id=%s""",
        (d['descripcion'], float(d.get('monto_total',0)), float(d.get('monto_adjudicado',0)),
         int(d.get('cuotas',12)), int(d.get('cuotas_pagadas',0)),
         int(d.get('plazo_meses',12)), d.get('fecha_inicio',''), d.get('fecha_fin',''),
         float(d.get('cuota_mensual',0)), d.get('entidad',''), d.get('notas',''), pid))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/prestamos/<int:pid>/cuotas', methods=['PATCH'])
def api_prestamos_cuotas_patch(pid):
    d = request.json; conn = get_db()
    delta = int(d.get('delta', 0))
    execute(conn, "UPDATE prestamos SET cuotas_pagadas = GREATEST(0, LEAST(cuotas, cuotas_pagadas + %s)) WHERE id=%s", (delta, pid))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/prestamos/<int:pid>', methods=['DELETE'])
def api_prestamos_del(pid):
    conn = get_db()
    execute(conn, "UPDATE prestamos SET activo=0 WHERE id=%s", (pid,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

# ── EQUIPOS ──────────────────────────────────────────────────────────────────
@app.route('/api/equipos', methods=['GET'])
def api_equipos():
    conn = get_db()
    equipos = fetchall(conn, "SELECT * FROM equipos ORDER BY activo DESC, nombre")
    result = []
    for e in equipos:
        d = dict(e)
        amort = (e['costo_total'] - e['valor_residual']) / max(e['vida_util_meses'], 1)
        d['amort_mensual'] = round(amort)
        if e['fecha_compra']:
            try:
                fc = datetime.strptime(str(e['fecha_compra']), '%Y-%m-%d')
                meses = (date.today().year - fc.year)*12 + (date.today().month - fc.month)
                d['meses_transcurridos'] = meses
                d['valor_actual'] = max(e['valor_residual'], e['costo_total'] - amort * meses)
            except: d['meses_transcurridos'] = 0; d['valor_actual'] = e['costo_total']
        else: d['meses_transcurridos'] = 0; d['valor_actual'] = e['costo_total']
        result.append(d)
    conn.close()
    return jsonify(result)

@app.route('/api/equipos', methods=['POST'])
def api_equipos_post():
    d = request.json; conn = get_db()
    execute(conn, "INSERT INTO equipos (nombre,cantidad,fecha_compra,costo_total,vida_util_meses,valor_residual) VALUES (%s,%s,%s,%s,%s,%s)",
        (d['nombre'], int(d.get('cantidad',1)), d.get('fecha_compra',''),
         float(d.get('costo_total',0)), int(d.get('vida_util_meses',48)), float(d.get('valor_residual',0))))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/equipos/<int:eid>', methods=['PUT'])
def api_equipos_put(eid):
    d = request.json; conn = get_db()
    execute(conn, "UPDATE equipos SET nombre=%s,cantidad=%s,fecha_compra=%s,costo_total=%s,vida_util_meses=%s,valor_residual=%s WHERE id=%s",
        (d['nombre'], int(d.get('cantidad',1)), d.get('fecha_compra',''),
         float(d.get('costo_total',0)), int(d.get('vida_util_meses',48)),
         float(d.get('valor_residual',0)), eid))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/equipos/<int:eid>', methods=['DELETE'])
def api_equipos_delete(eid):
    conn = get_db()
    execute(conn, "DELETE FROM equipos WHERE id=%s", (eid,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/equipos/<int:eid>/toggle', methods=['PATCH'])
def api_equipos_toggle(eid):
    conn = get_db()
    execute(conn, "UPDATE equipos SET activo = CASE WHEN activo=1 THEN 0 ELSE 1 END WHERE id=%s", (eid,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

# ── EXPORT CSV ────────────────────────────────────────────────────────────────
@app.route('/api/export/<string:tabla>')
def api_export(tabla):
    ALLOWED = {'insumos','pedidos','gastos','consumos','marketing','equipos','clientes','stock_reingreso'}
    if tabla not in ALLOWED:
        return jsonify({'error': 'tabla no permitida'}), 400
    conn = get_db()
    rows = fetchall(conn, f"SELECT * FROM {tabla}")
    conn.close()
    if not rows:
        return Response('\ufeffSin datos\n', mimetype='text/csv; charset=utf-8',
                        headers={'Content-Disposition': f'attachment; filename=pixel90_{tabla}.csv'})
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(rows[0].keys())
    w.writerows([list(r.values()) for r in rows])
    return Response('\ufeff' + output.getvalue(), mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename=pixel90_{tabla}.csv'})

# ── BALANCE ───────────────────────────────────────────────────────────────────
@app.route('/api/balance/<int:year>')
def api_balance(year):
    conn = get_db()
    result = []
    for m in range(1, 13):
        ini = f"{year}-{m:02d}-01"; fin = f"{year}-{m:02d}-{monthrange(year, m)[1]}"
        ventas = fetchone(conn, """SELECT COALESCE(SUM(pi.cantidad * pi.precio_unit),0) as total
            FROM pedidos p JOIN pedido_items pi ON pi.pedido_id=p.id
            WHERE p.fecha BETWEEN %s AND %s AND p.estado != 'Cancelado'""", (ini,fin))['total']
        gastos = fetchone(conn, "SELECT COALESCE(SUM(monto),0) as total FROM gastos WHERE fecha BETWEEN %s AND %s", (ini,fin))['total']
        result.append({'mes': m, 'ventas': ventas, 'gastos': gastos, 'ganancia': ventas - gastos})
    conn.close()
    return jsonify(result)

# ── SQL ADMIN ─────────────────────────────────────────────────────────────────
@app.route('/api/sql', methods=['POST'])
def ejecutar_sql():
    clave = request.headers.get('x-api-key')
    if clave != "ueTJ{z410]Z^":
        return jsonify({'error': 'No autorizado'}), 403
    data = request.json
    query = data.get('query')
    if not query:
        return jsonify({'error': 'Query vacía'}), 400
    conn = get_db()
    try:
        if query.strip().lower().startswith("select"):
            rows = fetchall(conn, query)
            conn.close()
            return jsonify(rows_to_list(rows))
        execute(conn, query)
        conn.commit(); conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)})

# ── TEST DB ───────────────────────────────────────────────────────────────────
@app.route('/test-db')
def test_db():
    try:
        conn = get_db()
        result = fetchone(conn, "SELECT 1 as result")['result']
        conn.close()
        return jsonify({"ok": True, "result": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

if __name__ == '__main__':
    init_db()
    print("\n  ██████╗ ██╗██╗  ██╗███████╗██╗      █████╗  ██████╗ ")
    print("  ██╔══██╗██║╚██╗██╔╝██╔════╝██║     ██╔══██╗██╔═████╗")
    print("  ██████╔╝██║ ╚███╔╝ █████╗  ██║     ╚██████║██║██╔██║")
    print("  ██╔═══╝ ██║ ██╔██╗ ██╔══╝  ██║      ╚═══██║████╔╝██║")
    print("  ██║     ██║██╔╝ ██╗███████╗███████╗ █████╔╝╚██████╔╝")
    print("  ╚═╝     ╚═╝╚═╝  ╚═╝╚══════╝╚══════╝ ╚════╝  ╚═════╝ \n")
    print("  Sistema de Gestión Comercial")
    print("  → Abrí tu navegador en:  http://localhost:5000\n")
    app.run(debug=False, host='0.0.0.0', port=5000)
