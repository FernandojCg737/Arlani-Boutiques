import 'dart:convert';

import 'package:path/path.dart' as p;
import 'package:sqflite/sqflite.dart';

import 'offline_modelos.dart';

/// P4 offline (persistencia movil): base SQLite del telefono, equivalente al
/// IndexedDB de la web (`offline-db.ts`) pero con tablas relacionadas:
/// - paquetes: cada descarga (del personal por sucursal, o el catalogo del
///   cliente). Sus tiendas, sucursales, productos, variantes, clientes,
///   direcciones y cuentas PayPal cuelgan de el con ON DELETE CASCADE, asi una
///   descarga nueva reemplaza a la anterior sin dejar filas sueltas ni repetidas.
/// - operaciones + operacion_items: ventas, reservas y compras hechas aqui.
/// - registro_sync: cada intento de sincronizacion y su resultado.
/// - imagenes: las fotos de las prendas guardadas en el telefono.
class OfflineDb {
  OfflineDb._();
  static final instancia = OfflineDb._();

  Database? _db;

  Future<Database> get _base async => _db ??= await openDatabase(
        p.join(await getDatabasesPath(), 'arlani_offline.db'),
        version: 1,
        onConfigure: (db) => db.execute('PRAGMA foreign_keys = ON'),
        onCreate: (db, _) async {
          final b = db.batch();
          b.execute('''CREATE TABLE paquetes (
            clave TEXT PRIMARY KEY, usuario_id INTEGER NOT NULL, tipo TEXT NOT NULL CHECK (tipo IN ('personal','cliente')),
            empresa_id INTEGER, empresa_nombre TEXT, sucursal_id INTEGER, sucursal_nombre TEXT, descargado_en TEXT NOT NULL)''');
          b.execute('''CREATE TABLE tiendas (
            paquete TEXT NOT NULL REFERENCES paquetes(clave) ON DELETE CASCADE, empresa_id INTEGER NOT NULL,
            nombre TEXT NOT NULL, logo_url TEXT, acepta_contra_entrega INTEGER NOT NULL DEFAULT 0,
            acepta_paypal INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (paquete, empresa_id))''');
          b.execute('''CREATE TABLE sucursales (
            paquete TEXT NOT NULL REFERENCES paquetes(clave) ON DELETE CASCADE, id INTEGER NOT NULL,
            empresa_id INTEGER NOT NULL, nombre TEXT NOT NULL, PRIMARY KEY (paquete, id))''');
          b.execute('''CREATE TABLE productos (
            paquete TEXT NOT NULL REFERENCES paquetes(clave) ON DELETE CASCADE, producto_id INTEGER NOT NULL,
            empresa_id INTEGER NOT NULL, nombre TEXT NOT NULL, precio REAL NOT NULL CHECK (precio >= 0),
            imagen_url TEXT, categoria TEXT, PRIMARY KEY (paquete, producto_id))''');
          b.execute('''CREATE TABLE variantes (
            paquete TEXT NOT NULL, producto_id INTEGER NOT NULL, talla_id INTEGER NOT NULL, talla_codigo TEXT NOT NULL,
            color_id INTEGER NOT NULL, color_nombre TEXT NOT NULL, sucursal_id INTEGER NOT NULL DEFAULT 0,
            stock INTEGER NOT NULL CHECK (stock >= 0),
            PRIMARY KEY (paquete, producto_id, talla_id, color_id, sucursal_id),
            FOREIGN KEY (paquete, producto_id) REFERENCES productos(paquete, producto_id) ON DELETE CASCADE)''');
          b.execute('''CREATE TABLE clientes (
            paquete TEXT NOT NULL REFERENCES paquetes(clave) ON DELETE CASCADE, id INTEGER NOT NULL,
            nombre TEXT NOT NULL, email TEXT NOT NULL, PRIMARY KEY (paquete, id))''');
          b.execute('''CREATE TABLE direcciones (
            paquete TEXT NOT NULL REFERENCES paquetes(clave) ON DELETE CASCADE, id INTEGER NOT NULL,
            alias TEXT NOT NULL, direccion TEXT NOT NULL, PRIMARY KEY (paquete, id))''');
          b.execute('''CREATE TABLE cuentas_paypal (
            paquete TEXT NOT NULL REFERENCES paquetes(clave) ON DELETE CASCADE, id INTEGER NOT NULL,
            cuenta TEXT, autorizada INTEGER NOT NULL DEFAULT 0, tiendas TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (paquete, id))''');
          b.execute('''CREATE TABLE operaciones (
            uuid TEXT PRIMARY KEY, usuario_id INTEGER NOT NULL,
            tipo TEXT NOT NULL CHECK (tipo IN ('venta','reserva','pedido')),
            empresa_nombre TEXT NOT NULL, sucursal_id INTEGER NOT NULL, sucursal_nombre TEXT NOT NULL,
            registrada_en TEXT NOT NULL, cliente_id INTEGER, cliente_nombre TEXT, factura_nombre TEXT, factura_nit TEXT,
            horario_atencion TEXT, entrega TEXT, direccion_id INTEGER, forma_pago TEXT, metodo_pago_id INTEGER,
            paypal_cuenta TEXT, total REAL NOT NULL, estado TEXT NOT NULL, mensaje TEXT, venta_id INTEGER,
            reserva_id INTEGER, intentos INTEGER NOT NULL DEFAULT 0, ultimo_intento TEXT, no_pagados TEXT,
            total_cobrado TEXT, cobro_visto INTEGER NOT NULL DEFAULT 0)''');
          b.execute('CREATE INDEX ix_operaciones_usuario ON operaciones(usuario_id, estado)');
          b.execute('''CREATE TABLE operacion_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operacion_uuid TEXT NOT NULL REFERENCES operaciones(uuid) ON DELETE CASCADE,
            producto_id INTEGER NOT NULL, talla_id INTEGER NOT NULL, color_id INTEGER NOT NULL,
            cantidad INTEGER NOT NULL CHECK (cantidad BETWEEN 1 AND 99), precio REAL NOT NULL,
            producto_nombre TEXT NOT NULL, talla TEXT NOT NULL, color TEXT NOT NULL,
            empresa_id INTEGER, empresa_nombre TEXT, sucursal_id INTEGER, sucursal_nombre TEXT,
            UNIQUE (operacion_uuid, producto_id, talla_id, color_id))''');
          b.execute('''CREATE TABLE registro_sync (
            id INTEGER PRIMARY KEY AUTOINCREMENT, usuario_id INTEGER NOT NULL, fecha TEXT NOT NULL,
            enviadas INTEGER NOT NULL, confirmadas INTEGER NOT NULL, conflictos INTEGER NOT NULL,
            rechazadas INTEGER NOT NULL, errores INTEGER NOT NULL, detalle TEXT NOT NULL)''');
          b.execute('CREATE TABLE imagenes (url TEXT PRIMARY KEY, ruta TEXT NOT NULL)');
          await b.commit(noResult: true);
        },
      );

  static String clavePersonal(int usuarioId, int sucursalId) => 'personal:$usuarioId:$sucursalId';
  static String claveCliente(int usuarioId) => 'cliente:$usuarioId';

  // ---------- Paquetes descargados (CU11) ----------

  void _productos(Batch b, String clave, int empresaId, List<ProductoLocal> productos) {
    for (final pr in productos) {
      b.insert('productos', {
        'paquete': clave,
        'producto_id': pr.productoId,
        'empresa_id': empresaId,
        'nombre': pr.nombre,
        'precio': pr.precio,
        'imagen_url': pr.imagenUrl,
        'categoria': pr.categoria,
      });
      for (final v in pr.variantes) {
        b.insert(
          'variantes',
          {
            'paquete': clave,
            'producto_id': pr.productoId,
            'talla_id': v.tallaId,
            'talla_codigo': v.tallaCodigo,
            'color_id': v.colorId,
            'color_nombre': v.colorNombre,
            'sucursal_id': v.sucursalId ?? 0,
            'stock': v.stock < 0 ? 0 : v.stock,
          },
          conflictAlgorithm: ConflictAlgorithm.replace,
        );
      }
    }
  }

  Future<void> guardarPersonal(int usuarioId, PaquetePersonal pq) async {
    final clave = clavePersonal(usuarioId, pq.sucursal.id);
    await (await _base).transaction((tx) async {
      await tx.delete('paquetes', where: 'clave = ?', whereArgs: [clave]);
      final b = tx.batch();
      b.insert('paquetes', {
        'clave': clave,
        'usuario_id': usuarioId,
        'tipo': 'personal',
        'empresa_id': pq.empresaId,
        'empresa_nombre': pq.empresaNombre,
        'sucursal_id': pq.sucursal.id,
        'sucursal_nombre': pq.sucursal.nombre,
        'descargado_en': pq.descargadoEn.toUtc().toIso8601String(),
      });
      _productos(b, clave, pq.empresaId, pq.productos);
      for (final c in pq.clientes) {
        b.insert('clientes', {'paquete': clave, 'id': c.id, 'nombre': c.nombre, 'email': c.email},
            conflictAlgorithm: ConflictAlgorithm.ignore);
      }
      await b.commit(noResult: true);
    });
  }

  Future<void> guardarCliente(int usuarioId, CatalogoCliente c) async {
    final clave = claveCliente(usuarioId);
    await (await _base).transaction((tx) async {
      await tx.delete('paquetes', where: 'clave = ?', whereArgs: [clave]);
      final b = tx.batch();
      b.insert('paquetes', {
        'clave': clave,
        'usuario_id': usuarioId,
        'tipo': 'cliente',
        'descargado_en': c.descargadoEn.toUtc().toIso8601String(),
      });
      for (final t in c.tiendas) {
        b.insert('tiendas', {
          'paquete': clave,
          'empresa_id': t.empresaId,
          'nombre': t.nombre,
          'logo_url': t.logoUrl,
          'acepta_contra_entrega': t.aceptaContraEntrega ? 1 : 0,
          'acepta_paypal': t.aceptaPaypal ? 1 : 0,
        });
        for (final s in t.sucursales) {
          b.insert('sucursales', {'paquete': clave, 'id': s.id, 'empresa_id': t.empresaId, 'nombre': s.nombre},
              conflictAlgorithm: ConflictAlgorithm.ignore);
        }
        _productos(b, clave, t.empresaId, t.productos);
      }
      for (final d in c.direcciones) {
        b.insert('direcciones', {'paquete': clave, 'id': d.id, 'alias': d.alias, 'direccion': d.direccion});
      }
      for (final pp in c.paypals) {
        b.insert('cuentas_paypal', {
          'paquete': clave,
          'id': pp.id,
          'cuenta': pp.cuenta,
          'autorizada': pp.autorizada ? 1 : 0,
          'tiendas': pp.tiendas.join(','),
        });
      }
      await b.commit(noResult: true);
    });
  }

  Future<Map<int, List<ProductoLocal>>> _productosDe(String clave) async {
    final db = await _base;
    final variantes = <int, List<VarianteLocal>>{};
    for (final v in await db.query('variantes', where: 'paquete = ?', whereArgs: [clave], orderBy: 'talla_id, color_id')) {
      final sucursal = v['sucursal_id'] as int;
      (variantes[v['producto_id'] as int] ??= []).add(VarianteLocal(
        tallaId: v['talla_id'] as int,
        tallaCodigo: v['talla_codigo'] as String,
        colorId: v['color_id'] as int,
        colorNombre: v['color_nombre'] as String,
        stock: v['stock'] as int,
        sucursalId: sucursal == 0 ? null : sucursal,
      ));
    }
    final porEmpresa = <int, List<ProductoLocal>>{};
    for (final pr in await db.query('productos', where: 'paquete = ?', whereArgs: [clave], orderBy: 'nombre')) {
      (porEmpresa[pr['empresa_id'] as int] ??= []).add(ProductoLocal(
        productoId: pr['producto_id'] as int,
        nombre: pr['nombre'] as String,
        precio: (pr['precio'] as num).toDouble(),
        imagenUrl: pr['imagen_url'] as String?,
        categoria: pr['categoria'] as String?,
        variantes: variantes[pr['producto_id'] as int] ?? [],
      ));
    }
    return porEmpresa;
  }

  Future<PaquetePersonal?> personal(int usuarioId, int sucursalId) async {
    final clave = clavePersonal(usuarioId, sucursalId);
    final db = await _base;
    final fila = (await db.query('paquetes', where: 'clave = ?', whereArgs: [clave])).firstOrNull;
    if (fila == null) return null;
    final productos = await _productosDe(clave);
    return PaquetePersonal(
      empresaId: fila['empresa_id'] as int,
      empresaNombre: fila['empresa_nombre'] as String,
      sucursal: SucursalLocal(sucursalId, fila['sucursal_nombre'] as String),
      descargadoEn: DateTime.parse(fila['descargado_en'] as String),
      productos: productos[fila['empresa_id'] as int] ?? [],
      clientes: [
        for (final c in await db.query('clientes', where: 'paquete = ?', whereArgs: [clave], orderBy: 'nombre'))
          ClienteLocal(c['id'] as int, c['nombre'] as String, c['email'] as String),
      ],
    );
  }

  /// Sucursales que este usuario ya descargo (para elegir sin conexion).
  Future<List<SucursalLocal>> sucursalesDescargadas(int usuarioId) async {
    final filas = await (await _base).query('paquetes',
        where: "usuario_id = ? AND tipo = 'personal'", whereArgs: [usuarioId], orderBy: 'sucursal_nombre');
    return [for (final f in filas) SucursalLocal(f['sucursal_id'] as int, f['sucursal_nombre'] as String)];
  }

  Future<CatalogoCliente?> cliente(int usuarioId) async {
    final clave = claveCliente(usuarioId);
    final db = await _base;
    final fila = (await db.query('paquetes', where: 'clave = ?', whereArgs: [clave])).firstOrNull;
    if (fila == null) return null;
    final productos = await _productosDe(clave);
    final sucursales = await db.query('sucursales', where: 'paquete = ?', whereArgs: [clave], orderBy: 'nombre');
    return CatalogoCliente(
      descargadoEn: DateTime.parse(fila['descargado_en'] as String),
      tiendas: [
        for (final t in await db.query('tiendas', where: 'paquete = ?', whereArgs: [clave], orderBy: 'nombre'))
          TiendaLocal(
            empresaId: t['empresa_id'] as int,
            nombre: t['nombre'] as String,
            logoUrl: t['logo_url'] as String?,
            aceptaContraEntrega: t['acepta_contra_entrega'] == 1,
            aceptaPaypal: t['acepta_paypal'] == 1,
            sucursales: [
              for (final s in sucursales.where((s) => s['empresa_id'] == t['empresa_id']))
                SucursalLocal(s['id'] as int, s['nombre'] as String),
            ],
            productos: productos[t['empresa_id'] as int] ?? [],
          ),
      ],
      direcciones: [
        for (final d in await db.query('direcciones', where: 'paquete = ?', whereArgs: [clave]))
          DireccionLocal(d['id'] as int, d['alias'] as String, d['direccion'] as String),
      ],
      paypals: [
        for (final pp in await db.query('cuentas_paypal', where: 'paquete = ?', whereArgs: [clave]))
          PaypalLocal(
            id: pp['id'] as int,
            cuenta: pp['cuenta'] as String?,
            autorizada: pp['autorizada'] == 1,
            tiendas: [for (final t in (pp['tiendas'] as String).split(',')) if (t.isNotEmpty) int.parse(t)],
          ),
      ],
    );
  }

  // ---------- Operaciones (CU12/CU13) ----------

  Map<String, Object?> _filaOperacion(OperacionLocal o) => {
        'uuid': o.uuid,
        'usuario_id': o.usuarioId,
        'tipo': o.tipo,
        'empresa_nombre': o.empresaNombre,
        'sucursal_id': o.sucursalId,
        'sucursal_nombre': o.sucursalNombre,
        'registrada_en': o.registradaEn,
        'cliente_id': o.clienteId,
        'cliente_nombre': o.clienteNombre,
        'factura_nombre': o.facturaNombre,
        'factura_nit': o.facturaNit,
        'horario_atencion': o.horarioAtencion,
        'entrega': o.entrega,
        'direccion_id': o.direccionId,
        'forma_pago': o.formaPago,
        'metodo_pago_id': o.metodoPagoId,
        'paypal_cuenta': o.paypalCuenta,
        'total': o.total,
        'estado': o.estado,
        'mensaje': o.mensaje,
        'venta_id': o.ventaId,
        'reserva_id': o.reservaId,
        'intentos': o.intentos,
        'ultimo_intento': o.ultimoIntento,
        'no_pagados': o.noPagados.isEmpty
            ? null
            : jsonEncode([
                for (final n in o.noPagados) {'producto': n.producto, 'talla': n.talla, 'color': n.color, 'motivo': n.motivo},
              ]),
        'total_cobrado': o.totalCobrado,
        'cobro_visto': o.cobroVisto ? 1 : 0,
      };

  /// Guarda una operacion nueva con sus prendas (todo o nada).
  Future<void> nuevaOperacion(OperacionLocal o) async {
    await (await _base).transaction((tx) async {
      await tx.insert('operaciones', _filaOperacion(o));
      for (final i in o.items) {
        await tx.insert('operacion_items', {
          'operacion_uuid': o.uuid,
          'producto_id': i.productoId,
          'talla_id': i.tallaId,
          'color_id': i.colorId,
          'cantidad': i.cantidad,
          'precio': i.precio,
          'producto_nombre': i.productoNombre,
          'talla': i.talla,
          'color': i.color,
          'empresa_id': i.empresaId,
          'empresa_nombre': i.empresaNombre,
          'sucursal_id': i.sucursalId,
          'sucursal_nombre': i.sucursalNombre,
        });
      }
    });
  }

  /// Solo cambia el estado (nunca se borra una operacion por enviarla).
  Future<void> actualizarOperacion(OperacionLocal o) async {
    final fila = _filaOperacion(o)..remove('uuid');
    await (await _base).update('operaciones', fila, where: 'uuid = ?', whereArgs: [o.uuid]);
  }

  Future<List<OperacionLocal>> operaciones(int usuarioId) async {
    final db = await _base;
    final items = <String, List<ItemLocal>>{};
    for (final i in await db.rawQuery(
        'SELECT i.* FROM operacion_items i JOIN operaciones o ON o.uuid = i.operacion_uuid WHERE o.usuario_id = ? ORDER BY i.id',
        [usuarioId])) {
      (items[i['operacion_uuid'] as String] ??= []).add(ItemLocal(
        productoId: i['producto_id'] as int,
        tallaId: i['talla_id'] as int,
        colorId: i['color_id'] as int,
        cantidad: i['cantidad'] as int,
        precio: (i['precio'] as num).toDouble(),
        productoNombre: i['producto_nombre'] as String,
        talla: i['talla'] as String,
        color: i['color'] as String,
        empresaId: i['empresa_id'] as int?,
        empresaNombre: i['empresa_nombre'] as String?,
        sucursalId: i['sucursal_id'] as int?,
        sucursalNombre: i['sucursal_nombre'] as String?,
      ));
    }
    return [
      for (final o in await db.query('operaciones', where: 'usuario_id = ?', whereArgs: [usuarioId], orderBy: 'registrada_en DESC'))
        OperacionLocal(
          uuid: o['uuid'] as String,
          usuarioId: usuarioId,
          tipo: o['tipo'] as String,
          empresaNombre: o['empresa_nombre'] as String,
          sucursalId: o['sucursal_id'] as int,
          sucursalNombre: o['sucursal_nombre'] as String,
          registradaEn: o['registrada_en'] as String,
          clienteId: o['cliente_id'] as int?,
          clienteNombre: o['cliente_nombre'] as String?,
          facturaNombre: o['factura_nombre'] as String?,
          facturaNit: o['factura_nit'] as String?,
          horarioAtencion: o['horario_atencion'] as String?,
          entrega: o['entrega'] as String?,
          direccionId: o['direccion_id'] as int?,
          formaPago: o['forma_pago'] as String?,
          metodoPagoId: o['metodo_pago_id'] as int?,
          paypalCuenta: o['paypal_cuenta'] as String?,
          items: items[o['uuid']] ?? [],
          total: (o['total'] as num).toDouble(),
          estado: o['estado'] as String,
          mensaje: o['mensaje'] as String?,
          ventaId: o['venta_id'] as int?,
          reservaId: o['reserva_id'] as int?,
          intentos: o['intentos'] as int,
          ultimoIntento: o['ultimo_intento'] as String?,
          noPagados: NoPagado.deJson(o['no_pagados']),
          totalCobrado: o['total_cobrado'] as String?,
          cobroVisto: o['cobro_visto'] == 1,
        ),
    ];
  }

  // ---------- Historial de sincronizacion ----------

  Future<void> registrar(int usuarioId, RegistroSync r) async {
    await (await _base).insert('registro_sync', {
      'usuario_id': usuarioId,
      'fecha': r.fecha.toUtc().toIso8601String(),
      'enviadas': r.enviadas,
      'confirmadas': r.confirmadas,
      'conflictos': r.conflictos,
      'rechazadas': r.rechazadas,
      'errores': r.errores,
      'detalle': r.detalle,
    });
  }

  Future<List<RegistroSync>> registro(int usuarioId) async {
    final filas = await (await _base)
        .query('registro_sync', where: 'usuario_id = ?', whereArgs: [usuarioId], orderBy: 'id DESC', limit: 30);
    return [
      for (final f in filas)
        RegistroSync(
          fecha: DateTime.parse(f['fecha'] as String),
          enviadas: f['enviadas'] as int,
          confirmadas: f['confirmadas'] as int,
          conflictos: f['conflictos'] as int,
          rechazadas: f['rechazadas'] as int,
          errores: f['errores'] as int,
          detalle: f['detalle'] as String,
        ),
    ];
  }

  // ---------- Fotos ----------

  Future<Map<String, String>> imagenes() async => {
        for (final f in await (await _base).query('imagenes')) f['url'] as String: f['ruta'] as String,
      };

  Future<void> guardarImagen(String url, String ruta) async {
    await (await _base).insert('imagenes', {'url': url, 'ruta': ruta}, conflictAlgorithm: ConflictAlgorithm.replace);
  }
}
