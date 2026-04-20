from flask import Flask, jsonify, request, render_template, send_from_directory
from db import get_db, init_db
import os, json
from datetime import datetime, date
from calendar import monthrange

app = Flask(__name__)
app.config['JSON_ENSURE_ASCII'] = False

# ── helpers ──────────────────────────────────────────────────────────────────
def rows_to_list(rows):
    return [dict(r) for r in rows]

def stock_actual(conn, insumo_id):
    row = conn.execute("SELECT stock_inicial, uds_por_pack FROM insumos WHERE id=?", (insumo_id,)).fetchone()
    if not row: return 0
    compras = conn.execute("SELECT COALESCE(SUM(cantidad_uds),0) FROM compras WHERE insumo_id=?", (insumo_id,)).fetchone()[0]
    consumos = conn.execute("SELECT COALESCE(SUM(cantidad_real),0) FROM consumos WHERE insumo_id=?", (insumo_id,)).fetchone()[0]
    return (row['stock_inicial'] or 0) + (compras or 0) - (consumos or 0)

def costo_unit(conn, insumo_id):
    row = conn.execute("SELECT precio_pack, uds_por_pack FROM insumos WHERE id=?", (insumo_id,)).fetchone()
    if not row or not row['uds_por_pack']: return 0
    return (row['precio_pack'] or 0) / row['uds_por_pack']

def amort_mensual(conn):
    equipos = conn.execute("SELECT costo_total, vida_util_meses, valor_residual FROM equipos WHERE activo=1").fetchall()
    return sum((e['costo_total'] - e['valor_residual']) / max(e['vida_util_meses'], 1) for e in equipos)

def param(conn, key, default=0):
    row = conn.execute("SELECT valor FROM parametros WHERE clave=?", (key,)).fetchone()
    try: return float(row['valor']) if row else default
    except: return default

def now_iso():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

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
    mes_ref_row = conn.execute("SELECT strftime('%Y-%m', MAX(fecha)) as ultimo_mes FROM pedidos WHERE estado != 'Cancelado'").fetchone()
    if mes_ref_row and mes_ref_row['ultimo_mes']:
        y_ref, m_ref = map(int, mes_ref_row['ultimo_mes'].split('-'))
        ref = date(y_ref, m_ref, 1)
    else:
        ref = hoy
    mes_ini = f"{ref.year}-{ref.month:02d}-01"
    mes_fin = f"{ref.year}-{ref.month:02d}-{monthrange(ref.year, ref.month)[1]}"
    ventas_mes = conn.execute("SELECT COALESCE(SUM(pi.cantidad * pi.precio_unit),0) FROM pedidos p JOIN pedido_items pi ON pi.pedido_id = p.id WHERE p.fecha BETWEEN ? AND ? AND p.estado != 'Cancelado'", (mes_ini, mes_fin)).fetchone()[0]
    gastos_mes = conn.execute("SELECT COALESCE(SUM(monto),0) FROM gastos WHERE fecha BETWEEN ? AND ?", (mes_ini, mes_fin)).fetchone()[0]
    pedidos_mes = conn.execute("SELECT COUNT(*) FROM pedidos WHERE fecha BETWEEN ? AND ? AND estado != 'Cancelado'", (mes_ini, mes_fin)).fetchone()[0]
    pendientes = conn.execute("SELECT COUNT(*) FROM pedidos WHERE estado IN ('Pendiente','En Producción')").fetchone()[0]
    insumos = conn.execute("SELECT id, nombre, stock_minimo FROM insumos WHERE activo=1").fetchall()
    alertas = []
    for ins in insumos:
        s = stock_actual(conn, ins['id'])
        if s <= ins['stock_minimo']:
            alertas.append({'nombre': ins['nombre'], 'stock': round(s, 2), 'minimo': ins['stock_minimo']})
    por_cat = conn.execute("SELECT pr.categoria, COALESCE(SUM(pi.cantidad * pi.precio_unit),0) as total FROM pedidos p JOIN pedido_items pi ON pi.pedido_id = p.id JOIN productos pr ON pr.id = pi.producto_id WHERE p.fecha BETWEEN ? AND ? AND p.estado != 'Cancelado' GROUP BY pr.categoria ORDER BY total DESC", (mes_ini, mes_fin)).fetchall()
    meses_data = []
    for i in range(5, -1, -1):
        m = ref.month - i; y = ref.year
        while m <= 0: m += 12; y -= 1
        ini = f"{y}-{m:02d}-01"; fin = f"{y}-{m:02d}-{monthrange(y, m)[1]}"
        v = conn.execute("SELECT COALESCE(SUM(pi.cantidad * pi.precio_unit),0) FROM pedidos p JOIN pedido_items pi ON pi.pedido_id = p.id WHERE p.fecha BETWEEN ? AND ? AND p.estado != 'Cancelado'", (ini, fin)).fetchone()[0]
        g = conn.execute("SELECT COALESCE(SUM(monto),0) FROM gastos WHERE fecha BETWEEN ? AND ?", (ini, fin)).fetchone()[0]
        meses_data.append({'mes': f"{y}-{m:02d}", 'ventas': v, 'gastos': g})
    ganancia = ventas_mes - gastos_mes
    margen = (ganancia / ventas_mes * 100) if ventas_mes > 0 else 0
    conn.close()
    return jsonify({
        'ventas_mes': ventas_mes, 'gastos_mes': gastos_mes,
        'ganancia': ganancia, 'margen': round(margen, 1),
        'pedidos_mes': pedidos_mes, 'pendientes': pendientes,
        'alertas': alertas, 'por_categoria': rows_to_list(por_cat),
        'historico': meses_data, 'mes_referencia': f"{ref.year}-{ref.month:02d}",
    })

# ── ALERTAS COUNT (for sidebar badge) ─────────────────────────────────────────
@app.route('/api/alertas_count')
def api_alertas_count():
    conn = get_db()
    insumos = conn.execute("SELECT id, stock_minimo FROM insumos WHERE activo=1").fetchall()
    count = sum(1 for ins in insumos if stock_actual(conn, ins['id']) <= ins['stock_minimo'])
    stock_count = conn.execute("SELECT COUNT(*) FROM stock_reingreso WHERE estado='Disponible'").fetchone()[0]
    conn.close()
    return jsonify({'count': count, 'stock_count': stock_count})

# ── INSUMOS ───────────────────────────────────────────────────────────────────
@app.route('/api/insumos', methods=['GET'])
def api_insumos():
    conn = get_db()
    insumos = conn.execute("SELECT * FROM insumos WHERE activo=1 ORDER BY categoria, nombre").fetchall()
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
    conn.execute("""INSERT INTO insumos (nombre,categoria,proveedor,unidad_compra,uds_por_pack,precio_pack,unidad_consum,stock_inicial,stock_minimo) VALUES (?,?,?,?,?,?,?,?,?)""",
        (d['nombre'], d['categoria'], d.get('proveedor',''), d.get('unidad_compra',''),
         float(d.get('uds_por_pack',1)), float(d.get('precio_pack',0)),
         d.get('unidad_consum',''), float(d.get('stock_inicial',0)), float(d.get('stock_minimo',0))))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/insumos/<int:iid>', methods=['PUT'])
def api_insumos_put(iid):
    d = request.json; conn = get_db()
    conn.execute("""UPDATE insumos SET nombre=?,categoria=?,proveedor=?,unidad_compra=?,uds_por_pack=?,precio_pack=?,unidad_consum=?,stock_inicial=?,stock_minimo=? WHERE id=?""",
        (d['nombre'], d['categoria'], d.get('proveedor',''), d.get('unidad_compra',''),
         float(d.get('uds_por_pack',1)), float(d.get('precio_pack',0)),
         d.get('unidad_consum',''), float(d.get('stock_inicial',0)), float(d.get('stock_minimo',0)), iid))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/insumos/<int:iid>', methods=['DELETE'])
def api_insumos_del(iid):
    conn = get_db()
    conn.execute("UPDATE insumos SET activo=0 WHERE id=?", (iid,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

# ── COMPRAS ───────────────────────────────────────────────────────────────────
@app.route('/api/compras', methods=['POST'])
def api_compras_post():
    d = request.json; conn = get_db()
    conn.execute("INSERT INTO compras (fecha,insumo_id,cantidad_uds,costo_total,proveedor,notas) VALUES (?,?,?,?,?,?)",
        (d['fecha'], d['insumo_id'], float(d['cantidad_uds']),
         float(d.get('costo_total',0)), d.get('proveedor',''), d.get('notas','')))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

# ── CONSUMOS ──────────────────────────────────────────────────────────────────
@app.route('/api/consumos', methods=['GET'])
def api_consumos():
    conn = get_db()
    rows = conn.execute("""SELECT c.*, i.nombre as insumo_nombre, i.unidad_consum,
        ROUND(c.cantidad_real * (i.precio_pack / MAX(i.uds_por_pack,1)), 0) as costo_total
        FROM consumos c LEFT JOIN insumos i ON i.id = c.insumo_id
        ORDER BY c.fecha DESC, c.id DESC LIMIT 200""").fetchall()
    conn.close()
    return jsonify(rows_to_list(rows))

@app.route('/api/consumos', methods=['POST'])
def api_consumos_post():
    d = request.json; conn = get_db()
    conn.execute("INSERT INTO consumos (fecha,tipo,descripcion,pedido_ref,insumo_id,cantidad_base,cantidad_real,notas) VALUES (?,?,?,?,?,?,?,?)",
        (d['fecha'], d['tipo'], d.get('descripcion',''), d.get('pedido_ref',''),
         d.get('insumo_id'), float(d.get('cantidad_base',0)), float(d.get('cantidad_real',0)), d.get('notas','')))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/consumos/<int:cid>', methods=['DELETE'])
def api_consumos_del(cid):
    conn = get_db()
    conn.execute("DELETE FROM consumos WHERE id=?", (cid,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

# ── PRODUCTOS & RECETAS ───────────────────────────────────────────────────────
@app.route('/api/productos', methods=['GET'])
def api_productos():
    conn = get_db()
    prods = conn.execute("SELECT * FROM productos WHERE activo=1 ORDER BY categoria,nombre").fetchall()
    result = []
    for p in prods:
        d = dict(p)
        recetas = conn.execute("SELECT r.*, i.nombre as insumo_nombre, i.unidad_consum, ROUND(i.precio_pack / MAX(i.uds_por_pack,1), 0) as costo_unit FROM recetas r JOIN insumos i ON i.id = r.insumo_id WHERE r.producto_id=?", (p['id'],)).fetchall()
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
    cur = conn.execute("INSERT INTO productos (nombre,categoria) VALUES (?,?)", (d['nombre'], d['categoria']))
    pid = cur.lastrowid
    for item in d.get('receta', []):
        conn.execute("INSERT OR REPLACE INTO recetas (producto_id,insumo_id,cantidad) VALUES (?,?,?)",
                     (pid, item['insumo_id'], float(item['cantidad'])))
    conn.commit(); conn.close()
    return jsonify({'ok': True, 'id': pid})

@app.route('/api/productos/<int:pid>/receta', methods=['PUT'])
def api_receta_put(pid):
    items = request.json; conn = get_db()
    conn.execute("DELETE FROM recetas WHERE producto_id=?", (pid,))
    for item in items:
        if float(item.get('cantidad', 0)) > 0:
            conn.execute("INSERT INTO recetas (producto_id,insumo_id,cantidad) VALUES (?,?,?)",
                         (pid, item['insumo_id'], float(item['cantidad'])))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/costo_producto/<int:pid>')
def api_costo_producto(pid):
    conn = get_db()
    p = param
    horas_mes = p(conn,'horas_mes',160); sueldo = p(conn,'sueldo_mensual',3500000)
    g_fijos = p(conn,'gastos_fijos',800000); ventas_e = p(conn,'ventas_estimadas_mes',80)
    margen = p(conn,'margen_deseado',0.35); impuestos = p(conn,'impuestos',0.10)
    recetas = conn.execute("SELECT r.cantidad, i.precio_pack, i.uds_por_pack FROM recetas r JOIN insumos i ON i.id = r.insumo_id WHERE r.producto_id=?", (pid,)).fetchall()
    costo_mat = sum(r['cantidad'] * (r['precio_pack'] / max(r['uds_por_pack'],1)) for r in recetas)
    tiempo_hs = 0.5; costo_hora = sueldo / max(horas_mes, 1)
    mano_obra = tiempo_hs * costo_hora; gasto_unit = g_fijos / max(ventas_e, 1)
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
    rows = conn.execute("SELECT * FROM clientes WHERE activo=1 ORDER BY nombre, apellido").fetchall()
    conn.close()
    return jsonify(rows_to_list(rows))

@app.route('/api/clientes', methods=['POST'])
def api_clientes_post():
    d = request.json; conn = get_db()
    cur = conn.execute("""INSERT INTO clientes (nombre,apellido,tipo_documento,numero_documento,telefono,email,direccion,ciudad,fecha_creacion)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (d['nombre'], d.get('apellido',''), d.get('tipo_documento','CI'),
         d.get('numero_documento',''), d.get('telefono',''), d.get('email',''),
         d.get('direccion',''), d.get('ciudad',''), date.today().isoformat()))
    conn.commit()
    cid = cur.lastrowid
    conn.close()
    return jsonify({'ok': True, 'id': cid})

@app.route('/api/clientes/<int:cid>', methods=['PUT'])
def api_clientes_put(cid):
    d = request.json; conn = get_db()
    conn.execute("""UPDATE clientes SET nombre=?,apellido=?,tipo_documento=?,numero_documento=?,telefono=?,email=?,direccion=?,ciudad=? WHERE id=?""",
        (d['nombre'], d.get('apellido',''), d.get('tipo_documento','CI'),
         d.get('numero_documento',''), d.get('telefono',''), d.get('email',''),
         d.get('direccion',''), d.get('ciudad',''), cid))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/clientes/<int:cid>', methods=['DELETE'])
def api_clientes_del(cid):
    conn = get_db()
    conn.execute("UPDATE clientes SET activo=0 WHERE id=?", (cid,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/clientes/buscar')
def api_clientes_buscar():
    q = request.args.get('q', '')
    conn = get_db()
    rows = conn.execute("SELECT * FROM clientes WHERE activo=1 AND (nombre LIKE ? OR apellido LIKE ? OR numero_documento LIKE ?) LIMIT 10",
        (f'%{q}%', f'%{q}%', f'%{q}%')).fetchall()
    conn.close()
    return jsonify(rows_to_list(rows))

# ── PEDIDOS ───────────────────────────────────────────────────────────────────
@app.route('/api/pedidos', methods=['GET'])
def api_pedidos():
    conn = get_db()
    estado = request.args.get('estado')
    q = "SELECT * FROM pedidos"; args = []
    if estado: q += " WHERE estado=?"; args.append(estado)
    q += " ORDER BY fecha DESC, id DESC LIMIT 200"
    pedidos = conn.execute(q, args).fetchall()
    result = []
    for p in pedidos:
        d = dict(p)
        items = conn.execute("SELECT pi.*, pr.nombre as producto_nombre FROM pedido_items pi LEFT JOIN productos pr ON pr.id = pi.producto_id WHERE pi.pedido_id=?", (p['id'],)).fetchall()
        d['items'] = rows_to_list(items)
        # Calculate saldo from cuotas if they exist
        cuotas = conn.execute("SELECT * FROM pedido_cuotas WHERE pedido_id=? ORDER BY numero_cuota", (p['id'],)).fetchall()
        if cuotas:
            total_pagado = sum(c['monto_pagado'] for c in cuotas)
            d['saldo'] = (d['total'] or 0) - total_pagado
            d['cuotas_data'] = rows_to_list(cuotas)
        else:
            d['saldo'] = (d['total'] or 0) - (d['adelanto'] or 0)
            d['cuotas_data'] = []
        # Get client data if linked
        if d.get('cliente_id'):
            cli = conn.execute("SELECT * FROM clientes WHERE id=?", (d['cliente_id'],)).fetchone()
            if cli: d['cliente_info'] = dict(cli)
        result.append(d)
    conn.close()
    return jsonify(result)

@app.route('/api/pedidos', methods=['POST'])
def api_pedidos_post():
    d = request.json; conn = get_db()
    ultimo = conn.execute("SELECT numero FROM pedidos ORDER BY id DESC LIMIT 1").fetchone()
    if ultimo and ultimo['numero']:
        try: n = int(ultimo['numero'].replace('P-','')) + 1
        except: n = 1
    else: n = 1
    numero = f"P-{n:04d}"
    cur = conn.execute("""INSERT INTO pedidos (numero,fecha,cliente_id,cliente,telefono,total,adelanto,cuotas,fecha_entrega,estado,canal,modelo_seguir,notas)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (numero, d['fecha'], d.get('cliente_id'), d.get('cliente',''), d.get('telefono',''),
         float(d.get('total',0)), float(d.get('adelanto',0)), int(d.get('cuotas',1)),
         d.get('fecha_entrega',''), d.get('estado','Pendiente'),
         d.get('canal',''), d.get('modelo_seguir',''), d.get('notas','')))
    pid = cur.lastrowid
    for item in d.get('items', []):
        conn.execute("INSERT INTO pedido_items (pedido_id,producto_id,descripcion,cantidad,precio_unit) VALUES (?,?,?,?,?)",
            (pid, item.get('producto_id'), item.get('descripcion',''),
             float(item.get('cantidad',1)), float(item.get('precio_unit',0))))
    # Create cuotas
    num_cuotas = int(d.get('cuotas', 1))
    total = float(d.get('total', 0))
    if num_cuotas > 1:
        monto_cuota = round(total / num_cuotas)
        for i in range(1, num_cuotas + 1):
            conn.execute("INSERT INTO pedido_cuotas (pedido_id,numero_cuota,monto_esperado) VALUES (?,?,?)",
                (pid, i, monto_cuota))
    elif num_cuotas == 1:
        conn.execute("INSERT INTO pedido_cuotas (pedido_id,numero_cuota,monto_esperado,monto_pagado,pagada) VALUES (?,?,?,?,?)",
            (pid, 1, total, float(d.get('adelanto',0)), 1 if float(d.get('adelanto',0)) >= total else 0))
    # Record initial state
    conn.execute("INSERT INTO pedido_estado_historial (pedido_id,estado,fecha_hora) VALUES (?,?,?)",
        (pid, d.get('estado','Pendiente'), now_iso()))
    conn.commit(); conn.close()
    return jsonify({'ok': True, 'numero': numero, 'id': pid})

@app.route('/api/pedidos/<int:pid>/consumos_registrados')
def api_pedido_consumos_check(pid):
    conn = get_db()
    p = conn.execute("SELECT numero FROM pedidos WHERE id=?", (pid,)).fetchone()
    if not p: conn.close(); return jsonify({'registrados': False})
    count = conn.execute("SELECT COUNT(*) FROM consumos WHERE pedido_ref=? AND tipo='VENTA'", (p['numero'],)).fetchone()[0]
    conn.close()
    return jsonify({'registrados': count > 0, 'cantidad': count})

@app.route('/api/pedidos/<int:pid>', methods=['PUT'])
def api_pedidos_put(pid):
    d = request.json; conn = get_db()
    old = conn.execute("SELECT estado FROM pedidos WHERE id=?", (pid,)).fetchone()
    conn.execute("""UPDATE pedidos SET cliente=?,cliente_id=?,telefono=?,total=?,adelanto=?,cuotas=?,
        fecha_entrega=?,estado=?,canal=?,modelo_seguir=?,notas=?,
        solicita_factura=?,factura_razon=?,factura_ruc=?,factura_email=?,factura_tel=?,factura_dir=? WHERE id=?""",
        (d.get('cliente',''), d.get('cliente_id'), d.get('telefono',''),
         float(d.get('total',0)), float(d.get('adelanto',0)), int(d.get('cuotas',1)),
         d.get('fecha_entrega',''), d.get('estado','Pendiente'),
         d.get('canal',''), d.get('modelo_seguir',''), d.get('notas',''),
         int(d.get('solicita_factura',0)), d.get('factura_razon',''),
         d.get('factura_ruc',''), d.get('factura_email',''),
         d.get('factura_tel',''), d.get('factura_dir',''), pid))
    # Record state change
    new_estado = d.get('estado','Pendiente')
    if old and old['estado'] != new_estado:
        conn.execute("INSERT INTO pedido_estado_historial (pedido_id,estado,fecha_hora) VALUES (?,?,?)",
            (pid, new_estado, now_iso()))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/pedidos/<int:pid>/cuotas', methods=['GET'])
def api_pedido_cuotas(pid):
    conn = get_db()
    rows = conn.execute("SELECT * FROM pedido_cuotas WHERE pedido_id=? ORDER BY numero_cuota", (pid,)).fetchall()
    conn.close()
    return jsonify(rows_to_list(rows))

@app.route('/api/pedidos/<int:pid>/cuotas', methods=['PUT'])
def api_pedido_cuotas_put(pid):
    data = request.json; conn = get_db()
    for c in data:
        conn.execute("UPDATE pedido_cuotas SET monto_pagado=?,pagada=?,fecha_pago=? WHERE id=?",
            (float(c.get('monto_pagado',0)), int(c.get('pagada',0)), c.get('fecha_pago',''), c['id']))
    # Recalc adelanto (total paid)
    total_paid = sum(float(c.get('monto_pagado',0)) for c in data)
    conn.execute("UPDATE pedidos SET adelanto=? WHERE id=?", (total_paid, pid))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/pedidos/<int:pid>/historial')
def api_pedido_historial(pid):
    conn = get_db()
    rows = conn.execute("SELECT * FROM pedido_estado_historial WHERE pedido_id=? ORDER BY fecha_hora", (pid,)).fetchall()
    conn.close()
    return jsonify(rows_to_list(rows))

@app.route('/api/pedidos/<int:pid>/reingreso', methods=['POST'])
def api_pedido_reingreso(pid):
    d = request.json; conn = get_db()
    p = conn.execute("SELECT numero, total FROM pedidos WHERE id=?", (pid,)).fetchone()
    if not p: conn.close(); return jsonify({'error': 'Pedido no encontrado'}), 404
    conn.execute("""INSERT INTO stock_reingreso (pedido_id,pedido_numero,producto_id,descripcion,cantidad,valor_unit,motivo,fecha)
        VALUES (?,?,?,?,?,?,?,?)""",
        (pid, p['numero'], d.get('producto_id'), d.get('descripcion',''),
         float(d.get('cantidad',1)), float(d.get('valor_unit',0)),
         d.get('motivo',''), date.today().isoformat()))
    # Update pedido estado
    conn.execute("UPDATE pedidos SET estado='Reingreso' WHERE id=?", (pid,))
    conn.execute("INSERT INTO pedido_estado_historial (pedido_id,estado,fecha_hora) VALUES (?,?,?)",
        (pid, 'Reingreso', now_iso()))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

# ── STOCK REINGRESO ──────────────────────────────────────────────────────────
@app.route('/api/stock_reingreso', methods=['GET'])
def api_stock_reingreso():
    conn = get_db()
    rows = conn.execute("""SELECT s.*, p.nombre as producto_nombre 
        FROM stock_reingreso s LEFT JOIN productos p ON p.id = s.producto_id 
        ORDER BY s.fecha DESC""").fetchall()
    conn.close()
    return jsonify(rows_to_list(rows))

@app.route('/api/stock_reingreso', methods=['POST'])
def api_stock_reingreso_post():
    d = request.json; conn = get_db()
    conn.execute("""INSERT INTO stock_reingreso (pedido_id,pedido_numero,producto_id,descripcion,cantidad,valor_unit,motivo,fecha,estado)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (None, None, d.get('producto_id'), d.get('descripcion',''),
         float(d.get('cantidad',1)), float(d.get('valor_unit',0)),
         d.get('motivo','Producción para stock'), date.today().isoformat(), 'Disponible'))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/stock_reingreso/<int:sid>', methods=['PUT'])
def api_stock_reingreso_put(sid):
    d = request.json; conn = get_db()
    conn.execute("UPDATE stock_reingreso SET estado=? WHERE id=?", (d.get('estado','Disponible'), sid))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/stock_reingreso/<int:sid>/salida', methods=['POST'])
def api_stock_salida(sid):
    d = request.json; conn = get_db()
    item = conn.execute("SELECT * FROM stock_reingreso WHERE id=?", (sid,)).fetchone()
    if not item: conn.close(); return jsonify({'error': 'No encontrado'}), 404
    # Determine prefix: S- for stock-produced, P- for reingreso from pedido
    is_stock_new = item['pedido_id'] is None
    prefix = 'S' if is_stock_new else 'P'
    ultimo = conn.execute(f"SELECT numero FROM pedidos WHERE numero LIKE '{prefix}-%' ORDER BY id DESC LIMIT 1").fetchone()
    if ultimo and ultimo['numero']:
        try: n = int(ultimo['numero'].replace(f'{prefix}-','')) + 1
        except: n = 1
    else: n = 1
    numero = f"{prefix}-{n:04d}"
    monto = float(d.get('monto', item['valor_unit'] * item['cantidad']))
    estado_pedido = 'Entregado (R)' if not is_stock_new else 'Entregado'
    cur = conn.execute("""INSERT INTO pedidos (numero,fecha,cliente_id,cliente,telefono,total,adelanto,cuotas,estado,canal,notas)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (numero, date.today().isoformat(), d.get('cliente_id'), d.get('cliente',''),
         d.get('telefono',''), monto, monto, 1, estado_pedido, 'Stock',
         f"Salida de stock #{sid}"))
    pid = cur.lastrowid
    conn.execute("INSERT INTO pedido_items (pedido_id,producto_id,descripcion,cantidad,precio_unit) VALUES (?,?,?,?,?)",
        (pid, item['producto_id'], item['descripcion'] or '', item['cantidad'], float(d.get('monto', item['valor_unit']))))
    conn.execute("INSERT INTO pedido_estado_historial (pedido_id,estado,fecha_hora) VALUES (?,?,?)",
        (pid, estado_pedido, now_iso()))
    conn.execute("UPDATE stock_reingreso SET estado='Vendido' WHERE id=?", (sid,))
    conn.commit(); conn.close()
    return jsonify({'ok': True, 'numero': numero})

# ── GASTOS ────────────────────────────────────────────────────────────────────
@app.route('/api/gastos', methods=['GET'])
def api_gastos():
    conn = get_db()
    mes = request.args.get('mes')
    if mes:
        rows = conn.execute("SELECT * FROM gastos WHERE strftime('%Y-%m',fecha)=? ORDER BY fecha DESC", (mes,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM gastos ORDER BY fecha DESC LIMIT 200").fetchall()
    conn.close()
    return jsonify(rows_to_list(rows))

@app.route('/api/gastos', methods=['POST'])
def api_gastos_post():
    d = request.json; conn = get_db()
    conn.execute("INSERT INTO gastos (fecha,categoria,descripcion,proveedor,comprobante,forma_pago,monto,tipo_recurrencia,notas) VALUES (?,?,?,?,?,?,?,?,?)",
        (d['fecha'], d['categoria'], d.get('descripcion',''), d.get('proveedor',''),
         d.get('comprobante',''), d.get('forma_pago',''), float(d.get('monto',0)),
         d.get('tipo_recurrencia','Único'), d.get('notas','')))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/gastos/<int:gid>', methods=['PUT'])
def api_gastos_put(gid):
    d = request.json; conn = get_db()
    conn.execute("""UPDATE gastos SET fecha=?,categoria=?,descripcion=?,proveedor=?,comprobante=?,forma_pago=?,monto=?,tipo_recurrencia=?,notas=? WHERE id=?""",
        (d['fecha'], d['categoria'], d.get('descripcion',''), d.get('proveedor',''),
         d.get('comprobante',''), d.get('forma_pago',''), float(d.get('monto',0)),
         d.get('tipo_recurrencia','Único'), d.get('notas',''), gid))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/gastos/<int:gid>', methods=['DELETE'])
def api_gastos_del(gid):
    conn = get_db()
    conn.execute("DELETE FROM gastos WHERE id=?", (gid,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

# ── MARKETING ─────────────────────────────────────────────────────────────────
@app.route('/api/marketing', methods=['GET'])
def api_marketing():
    conn = get_db()
    rows = conn.execute("SELECT * FROM marketing ORDER BY mes DESC").fetchall()
    conn.close()
    return jsonify(rows_to_list(rows))

@app.route('/api/marketing', methods=['POST'])
def api_marketing_post():
    d = request.json; conn = get_db()
    conn.execute("""INSERT INTO marketing (mes,plataforma,tipo_campana,presupuesto,gasto_real,alcance,interacciones,pedidos_generados,venta_generada,notas)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (d['mes'], d['plataforma'], d.get('tipo_campana',''),
         float(d.get('presupuesto',0)), float(d.get('gasto_real',0)),
         int(d.get('alcance',0)), int(d.get('interacciones',0)),
         int(d.get('pedidos_generados',0)), float(d.get('venta_generada',0)),
         d.get('notas','')))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/marketing/<int:mid>', methods=['PUT'])
def api_marketing_put(mid):
    d = request.json; conn = get_db()
    conn.execute("""UPDATE marketing SET mes=?,plataforma=?,tipo_campana=?,presupuesto=?,gasto_real=?,alcance=?,interacciones=?,pedidos_generados=?,venta_generada=?,notas=? WHERE id=?""",
        (d['mes'], d['plataforma'], d.get('tipo_campana',''),
         float(d.get('presupuesto',0)), float(d.get('gasto_real',0)),
         int(d.get('alcance',0)), int(d.get('interacciones',0)),
         int(d.get('pedidos_generados',0)), float(d.get('venta_generada',0)),
         d.get('notas',''), mid))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/marketing/<int:mid>', methods=['DELETE'])
def api_marketing_del(mid):
    conn = get_db()
    conn.execute("DELETE FROM marketing WHERE id=?", (mid,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

# ── CATEGORÍAS ────────────────────────────────────────────────────────────────
@app.route('/api/categorias', methods=['GET'])
def api_categorias():
    conn = get_db()
    from_insumos = [r[0] for r in conn.execute("SELECT DISTINCT categoria FROM insumos ORDER BY categoria").fetchall()]
    from_productos = [r[0] for r in conn.execute("SELECT DISTINCT categoria FROM productos ORDER BY categoria").fetchall()]
    custom = []
    try: custom = [r[0] for r in conn.execute("SELECT DISTINCT valor FROM categorias ORDER BY orden").fetchall()]
    except: pass
    all_cats = list(dict.fromkeys(from_insumos + from_productos + custom))
    conn.close()
    return jsonify(all_cats)

@app.route('/api/categorias', methods=['POST'])
def api_categorias_post():
    d = request.json; conn = get_db()
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS categorias (id INTEGER PRIMARY KEY AUTOINCREMENT, valor TEXT UNIQUE, orden INTEGER DEFAULT 0)")
        conn.execute("INSERT OR IGNORE INTO categorias (valor, orden) VALUES (?,?)", (d['valor'], 999))
        conn.commit()
    except: pass
    conn.close()
    return jsonify({'ok': True})

# ── PARÁMETROS ────────────────────────────────────────────────────────────────
@app.route('/api/parametros', methods=['GET'])
def api_parametros():
    conn = get_db()
    rows = conn.execute("SELECT * FROM parametros").fetchall()
    conn.close()
    return jsonify({r['clave']: r['valor'] for r in rows})

@app.route('/api/parametros', methods=['PUT'])
def api_parametros_put():
    d = request.json; conn = get_db()
    for k, v in d.items():
        conn.execute("INSERT OR REPLACE INTO parametros VALUES (?,?)", (k, str(v)))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

# ── PRÉSTAMOS ─────────────────────────────────────────────────────────────────
@app.route('/api/prestamos', methods=['GET'])
def api_prestamos():
    conn = get_db()
    rows = conn.execute("SELECT * FROM prestamos WHERE activo=1 ORDER BY fecha_inicio DESC").fetchall()
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
    conn.execute("""INSERT INTO prestamos (descripcion,monto_total,monto_adjudicado,cuotas,cuotas_pagadas,plazo_meses,fecha_inicio,fecha_fin,cuota_mensual,entidad,notas)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (d['descripcion'], monto, float(d.get('monto_adjudicado', monto)),
         cuotas, int(d.get('cuotas_pagadas', 0)), int(d.get('plazo_meses', cuotas)),
         d.get('fecha_inicio',''), d.get('fecha_fin',''),
         float(d.get('cuota_mensual', cuota_m)), d.get('entidad',''), d.get('notas','')))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/prestamos/<int:pid>', methods=['PUT'])
def api_prestamos_put(pid):
    d = request.json; conn = get_db()
    conn.execute("""UPDATE prestamos SET descripcion=?,monto_total=?,monto_adjudicado=?,cuotas=?,cuotas_pagadas=?,
        plazo_meses=?,fecha_inicio=?,fecha_fin=?,cuota_mensual=?,entidad=?,notas=? WHERE id=?""",
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
    conn.execute("UPDATE prestamos SET cuotas_pagadas = MAX(0, MIN(cuotas, cuotas_pagadas + ?)) WHERE id=?", (delta, pid))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/prestamos/<int:pid>', methods=['DELETE'])
def api_prestamos_del(pid):
    conn = get_db()
    conn.execute("UPDATE prestamos SET activo=0 WHERE id=?", (pid,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

# ── EQUIPOS (now labeled "Inventario" in UI) ─────────────────────────────────
@app.route('/api/equipos', methods=['GET'])
def api_equipos():
    conn = get_db()
    equipos = conn.execute("SELECT * FROM equipos ORDER BY activo DESC, nombre").fetchall()
    result = []
    for e in equipos:
        d = dict(e)
        amort = (e['costo_total'] - e['valor_residual']) / max(e['vida_util_meses'], 1)
        d['amort_mensual'] = round(amort)
        if e['fecha_compra']:
            try:
                fc = datetime.strptime(e['fecha_compra'], '%Y-%m-%d')
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
    conn.execute("INSERT INTO equipos (nombre,cantidad,fecha_compra,costo_total,vida_util_meses,valor_residual) VALUES (?,?,?,?,?,?)",
        (d['nombre'], int(d.get('cantidad',1)), d.get('fecha_compra',''),
         float(d.get('costo_total',0)), int(d.get('vida_util_meses',48)), float(d.get('valor_residual',0))))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/equipos/<int:eid>', methods=['PUT'])
def api_equipos_put(eid):
    d = request.json; conn = get_db()
    conn.execute("UPDATE equipos SET nombre=?,cantidad=?,fecha_compra=?,costo_total=?,vida_util_meses=?,valor_residual=? WHERE id=?",
        (d['nombre'], int(d.get('cantidad',1)), d.get('fecha_compra',''),
         float(d.get('costo_total',0)), int(d.get('vida_util_meses',48)),
         float(d.get('valor_residual',0)), eid))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/equipos/<int:eid>', methods=['DELETE'])
def api_equipos_delete(eid):
    conn = get_db()
    conn.execute("DELETE FROM equipos WHERE id=?", (eid,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/equipos/<int:eid>/toggle', methods=['PATCH'])
def api_equipos_toggle(eid):
    conn = get_db()
    conn.execute("UPDATE equipos SET activo = CASE WHEN activo=1 THEN 0 ELSE 1 END WHERE id=?", (eid,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

# ── EXPORT CSV ────────────────────────────────────────────────────────────────
@app.route('/api/export/<string:tabla>')
def api_export(tabla):
    import csv, io
    ALLOWED = {'insumos','pedidos','gastos','consumos','marketing','equipos','clientes','stock_reingreso'}
    if tabla not in ALLOWED:
        return jsonify({'error': 'tabla no permitida'}), 400
    conn = get_db()
    rows = conn.execute(f"SELECT * FROM {tabla}").fetchall()
    conn.close()
    if not rows:
        from flask import Response
        return Response('\ufeffSin datos\n', mimetype='text/csv; charset=utf-8',
                        headers={'Content-Disposition': f'attachment; filename=pixel90_{tabla}.csv'})
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(rows[0].keys())
    w.writerows([list(r) for r in rows])
    from flask import Response
    return Response('\ufeff' + output.getvalue(), mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename=pixel90_{tabla}.csv'})

# ── BALANCE ───────────────────────────────────────────────────────────────────
@app.route('/api/balance/<int:year>')
def api_balance(year):
    conn = get_db()
    result = []
    for m in range(1, 13):
        ini = f"{year}-{m:02d}-01"; fin = f"{year}-{m:02d}-{monthrange(year, m)[1]}"
        ventas = conn.execute("SELECT COALESCE(SUM(pi.cantidad * pi.precio_unit),0) FROM pedidos p JOIN pedido_items pi ON pi.pedido_id=p.id WHERE p.fecha BETWEEN ? AND ? AND p.estado != 'Cancelado'", (ini,fin)).fetchone()[0]
        gastos = conn.execute("SELECT COALESCE(SUM(monto),0) FROM gastos WHERE fecha BETWEEN ? AND ?", (ini,fin)).fetchone()[0]
        result.append({'mes': m, 'ventas': ventas, 'gastos': gastos, 'ganancia': ventas - gastos})
    conn.close()
    return jsonify(result)

# ── BASA ───────────────────────────────────────────────────────────────────

@app.route('/api/sql', methods=['POST'])
def ejecutar_sql():
    clave = request.headers.get('x-api-key')

    # 🔐 cambiá esto por una clave tuya
    if clave != "ueTJ{z410]Z^":
        return jsonify({'error': 'No autorizado'}), 403

    data = request.json
    query = data.get('query')

    if not query:
        return jsonify({'error': 'Query vacía'}), 400

    conn = get_db()
    try:
        cur = conn.execute(query)

        # Si es SELECT → devolver datos
        if query.strip().lower().startswith("select"):
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            return jsonify(rows)

        # Si es INSERT/UPDATE/DELETE
        conn.commit()
        conn.close()
        return jsonify({'ok': True})

    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)})

# ── BASE TEST ───────────────────────────────────────────────────────────────────
@app.route('/test-db')
def test_db():
    from db import get_db
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT 1")
    result = cur.fetchone()
    conn.close()
    return {"ok": True, "result": result}

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
