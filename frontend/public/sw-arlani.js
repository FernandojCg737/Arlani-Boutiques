// Service worker de Arlani: el de Angular (cache de la app para abrirla sin
// conexion) + Background Sync (CU12). Cuando vuelve la conexion, el
// navegador despierta este worker aunque la app este cerrada y se envian las
// ventas y reservas guardadas sin conexion. Mismo contrato que
// src/app/services/offline/sincronizacion.ts; el backend no duplica una
// operacion que llegue dos veces (uuid).
importScripts('./ngsw-worker.js');

const ETIQUETA_SYNC = 'arlani-sync';
const POR_ENVIAR = ['pendiente', 'enviando', 'error'];

self.addEventListener('sync', (event) => {
  if (event.tag === ETIQUETA_SYNC) event.waitUntil(sincronizarEnFondo());
});

function abrirDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open('arlani-offline');
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function todos(db, almacen) {
  return new Promise((resolve, reject) => {
    if (!db.objectStoreNames.contains(almacen)) return resolve([]);
    const req = db.transaction(almacen).objectStore(almacen).getAll();
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function guardar(db, almacen, valor) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(almacen, 'readwrite');
    tx.objectStore(almacen).put(valor);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

function contrato(o) {
  return {
    uuid: o.uuid,
    tipo: o.tipo,
    sucursal_id: o.sucursal_id,
    registrada_en: o.registrada_en,
    cliente_id: o.cliente_id,
    factura_nombre: o.factura_nombre,
    factura_nit: o.factura_nit,
    horario_atencion: o.horario_atencion,
    items: o.items.map((i) => ({
      producto_id: i.producto_id,
      talla_id: i.talla_id,
      color_id: i.color_id,
      cantidad: i.cantidad,
      precio: i.precio,
    })),
  };
}

async function sincronizarEnFondo() {
  const db = await abrirDb();
  const sesiones = await todos(db, 'sesion');
  const operaciones = await todos(db, 'operaciones');
  let huboCambios = false;

  for (const sesion of sesiones) {
    const pendientes = operaciones.filter((o) => o.usuario_id === sesion.usuario_id && POR_ENVIAR.includes(o.estado));
    if (!pendientes.length) continue;
    const ahora = new Date().toISOString();
    const respuesta = await fetch(`${sesion.api}/sincronizar`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${sesion.token}`,
        'X-Client-Platform': 'web',
      },
      body: JSON.stringify({ operaciones: pendientes.slice(0, 50).map(contrato) }),
    });
    // 401 (sesion vencida) u otro error: quedan pendientes; las envia la app
    // al volver a iniciar sesion. Un error de red rechaza la promesa y el
    // navegador vuelve a intentar el sync mas tarde.
    if (!respuesta.ok) continue;
    const resultados = await respuesta.json();
    const cuenta = { enviadas: 0, confirmadas: 0, conflictos: 0, rechazadas: 0, errores: 0 };
    for (const r of resultados) {
      const op = pendientes.find((o) => o.uuid === r.uuid);
      if (!op) continue;
      cuenta.enviadas++;
      if (r.estado === 'confirmada') cuenta.confirmadas++;
      else if (r.estado === 'conflicto') cuenta.conflictos++;
      else if (r.estado === 'rechazada') cuenta.rechazadas++;
      else cuenta.errores++;
      await guardar(db, 'operaciones', {
        ...op,
        estado: r.estado,
        mensaje: r.mensaje,
        venta_id: r.venta_id ?? op.venta_id,
        reserva_id: r.reserva_id ?? op.reserva_id,
        intentos: op.intentos + 1,
        ultimo_intento: ahora,
      });
    }
    await guardar(db, 'registro', {
      usuario_id: sesion.usuario_id,
      fecha: ahora,
      ...cuenta,
      detalle: 'Sincronizado en segundo plano al volver la conexión.',
    });
    huboCambios = true;
  }
  db.close();

  if (huboCambios) {
    const ventanas = await self.clients.matchAll({ includeUncontrolled: true });
    for (const v of ventanas) v.postMessage({ tipo: 'arlani-sincronizado' });
  }
}
