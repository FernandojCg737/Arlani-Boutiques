"""CU16 Arqueo y cierre de caja

- caja: dos tipos.
  * fisica: la abre el personal en su sucursal con un fondo inicial (el
    cambio con el que empieza) y la cierra contando el efectivo. Una sola
    abierta por sucursal. Sin caja abierta no se puede vender en mostrador.
  * online: una por tienda y por dia (hora de Bolivia). Se abre sola con la
    primera venta en linea del dia y se cierra sola al terminar el dia; junta
    las ventas por PayPal o QR, sobre todo las que entran con la tienda
    cerrada. No se cuenta efectivo.
- movimiento_caja: ingresos y retiros de efectivo durante el turno.
- venta.caja_id: el trigger trg_venta_caja pone cada venta en su caja. Una
  venta OFFLINE (CU12) va a la caja del momento en que se hizo; si esa caja
  ya se cerro queda como "fuera de arqueo" (venta tardia) y no cambia el
  arqueo ya hecho.
- fn_resumen_caja: totales de una caja (por metodo, movimientos, efectivo
  esperado). sp_abrir_caja / sp_cerrar_caja: abrir y arquear.
- Permiso 2P-CU16 para Encargado de Sucursal y Cajero en todas las tiendas.

Revision ID: a4c6e8f0b123
Revises: f2b4d6e8a091
Create Date: 2026-10-23

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "a4c6e8f0b123"
down_revision = "f2b4d6e8a091"
branch_labels = None
depends_on = None


UPGRADE = r"""
-- Las fechas se guardan en UTC; el "dia" de una caja es el de Bolivia.
CREATE OR REPLACE FUNCTION fn_dia_bolivia(p_momento TIMESTAMP)
RETURNS DATE AS $$
    SELECT (p_momento AT TIME ZONE 'UTC' AT TIME ZONE 'America/La_Paz')::date;
$$ LANGUAGE sql IMMUTABLE;

CREATE TABLE caja (
    id                SERIAL PRIMARY KEY,
    empresa_id        INTEGER NOT NULL DEFAULT fn_empresa_para_alta() REFERENCES empresa(id) ON DELETE CASCADE,
    sucursal_id       INTEGER REFERENCES sucursal(id) ON DELETE CASCADE,
    tipo              VARCHAR(10) NOT NULL CHECK (tipo IN ('fisica', 'online')),
    fecha             DATE NOT NULL,
    abierta_en        TIMESTAMP NOT NULL DEFAULT now(),
    abierta_por_id    INTEGER REFERENCES usuario(id) ON DELETE SET NULL,
    monto_inicial     NUMERIC(10,2) NOT NULL DEFAULT 0 CHECK (monto_inicial >= 0),
    cerrada_en        TIMESTAMP,
    cerrada_por_id    INTEGER REFERENCES usuario(id) ON DELETE SET NULL,
    efectivo_esperado NUMERIC(10,2),
    efectivo_contado  NUMERIC(10,2) CHECK (efectivo_contado >= 0),
    diferencia        NUMERIC(10,2),
    observacion       TEXT,
    CONSTRAINT ck_caja_sucursal CHECK ((tipo = 'fisica') = (sucursal_id IS NOT NULL))
);
CREATE UNIQUE INDEX ux_caja_fisica_abierta ON caja (sucursal_id) WHERE tipo = 'fisica' AND cerrada_en IS NULL;
CREATE UNIQUE INDEX ux_caja_online_dia ON caja (empresa_id, fecha) WHERE tipo = 'online';
CREATE INDEX ix_caja_empresa ON caja (empresa_id, abierta_en DESC);
ALTER TABLE caja ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_caja_empresa ON caja FOR ALL TO arlani_tenant
    USING (empresa_id = fn_empresa_actual()) WITH CHECK (empresa_id = fn_empresa_actual());

CREATE TABLE movimiento_caja (
    id          SERIAL PRIMARY KEY,
    caja_id     INTEGER NOT NULL REFERENCES caja(id) ON DELETE CASCADE,
    tipo        VARCHAR(10) NOT NULL CHECK (tipo IN ('ingreso', 'retiro')),
    monto       NUMERIC(10,2) NOT NULL CHECK (monto > 0),
    motivo      VARCHAR(200) NOT NULL,
    usuario_id  INTEGER REFERENCES usuario(id) ON DELETE SET NULL,
    fecha       TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX ix_movimiento_caja ON movimiento_caja (caja_id);
ALTER TABLE movimiento_caja ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_movimiento_caja_empresa ON movimiento_caja FOR ALL TO arlani_tenant
    USING (caja_id IN (SELECT id FROM caja)) WITH CHECK (caja_id IN (SELECT id FROM caja));

ALTER TABLE venta ADD COLUMN caja_id INTEGER REFERENCES caja(id) ON DELETE SET NULL;
ALTER TABLE venta ADD COLUMN fuera_de_arqueo BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX ix_venta_caja ON venta (caja_id);

-- Caja online de una tienda en un dia: la crea si aun no existe.
CREATE OR REPLACE FUNCTION fn_caja_online(p_empresa_id INTEGER, p_dia DATE)
RETURNS INTEGER AS $$
DECLARE
    v_id INTEGER;
BEGIN
    INSERT INTO caja (empresa_id, tipo, fecha, abierta_en)
    VALUES (p_empresa_id, 'online', p_dia, (p_dia::timestamp AT TIME ZONE 'America/La_Paz') AT TIME ZONE 'UTC')
    ON CONFLICT (empresa_id, fecha) WHERE tipo = 'online' DO NOTHING;
    SELECT id INTO v_id FROM caja WHERE empresa_id = p_empresa_id AND tipo = 'online' AND fecha = p_dia;
    RETURN v_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

-- Cada venta entra a su caja.
CREATE OR REPLACE FUNCTION fn_trg_venta_caja()
RETURNS trigger AS $$
DECLARE
    v_empresa INTEGER;
    v_caja    INTEGER;
    v_cerrada TIMESTAMP;
    v_momento TIMESTAMP := coalesce(NEW.fecha, now()::timestamp);
BEGIN
    IF NEW.caja_id IS NOT NULL THEN
        RETURN NEW;
    END IF;
    SELECT empresa_id INTO v_empresa FROM sucursal WHERE id = NEW.sucursal_id;
    IF v_empresa IS NULL THEN
        RETURN NEW;
    END IF;

    IF NEW.tipo = 'venta_presencial' THEN
        IF coalesce(NEW.origen, 'online') = 'offline' THEN
            -- Sincronizada (CU12): la caja que estaba abierta cuando se vendio.
            SELECT id, cerrada_en INTO v_caja, v_cerrada FROM caja
            WHERE tipo = 'fisica' AND sucursal_id = NEW.sucursal_id
              AND abierta_en <= v_momento AND (cerrada_en IS NULL OR cerrada_en >= v_momento)
            ORDER BY abierta_en DESC LIMIT 1;
            IF v_caja IS NOT NULL THEN
                NEW.caja_id := v_caja;
                NEW.fuera_de_arqueo := v_cerrada IS NOT NULL;
            ELSE
                NEW.caja_id := fn_caja_online(v_empresa, fn_dia_bolivia(v_momento));
                NEW.fuera_de_arqueo := TRUE;
            END IF;
            RETURN NEW;
        END IF;

        SELECT id INTO v_caja FROM caja
        WHERE tipo = 'fisica' AND sucursal_id = NEW.sucursal_id AND cerrada_en IS NULL;
        IF v_caja IS NULL THEN
            RAISE EXCEPTION 'caja_cerrada';
        END IF;
        NEW.caja_id := v_caja;
        RETURN NEW;
    END IF;

    -- Venta en linea: a la caja online del dia en que se hizo.
    NEW.caja_id := fn_caja_online(v_empresa, fn_dia_bolivia(v_momento));
    NEW.fuera_de_arqueo := fn_dia_bolivia(v_momento) < fn_dia_bolivia(now()::timestamp);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

CREATE TRIGGER trg_venta_caja
BEFORE INSERT ON venta
FOR EACH ROW EXECUTE FUNCTION fn_trg_venta_caja();

-- Totales de una caja. El efectivo esperado solo cuenta lo que entro por
-- la caja (ventas fuera de arqueo no) y resta las devoluciones pagadas en
-- efectivo en esa sucursal mientras la caja estaba abierta.
CREATE OR REPLACE FUNCTION fn_resumen_caja(p_caja_id INTEGER)
RETURNS TABLE (ventas INTEGER, total_ventas NUMERIC, efectivo NUMERIC, qr NUMERIC, paypal NUMERIC, otros NUMERIC,
               ingresos NUMERIC, retiros NUMERIC, devoluciones_efectivo NUMERIC, efectivo_esperado NUMERIC) AS $$
    WITH c AS (
        SELECT * FROM caja WHERE id = p_caja_id
    ), v AS (
        SELECT v.id, v.total, v.fuera_de_arqueo FROM venta v WHERE v.caja_id = p_caja_id
    ), p AS (
        SELECT pg.metodo, pg.monto FROM pago pg JOIN v ON v.id = pg.venta_id
        WHERE pg.estado = 'completado' AND NOT v.fuera_de_arqueo
    ), m AS (
        SELECT coalesce(sum(monto) FILTER (WHERE tipo = 'ingreso'), 0) AS ingresos,
               coalesce(sum(monto) FILTER (WHERE tipo = 'retiro'), 0) AS retiros
        FROM movimiento_caja WHERE caja_id = p_caja_id
    ), d AS (
        SELECT coalesce(sum(dv.monto_reembolso), 0) AS monto
        FROM devolucion dv JOIN venta vv ON vv.id = dv.venta_id, c
        WHERE c.tipo = 'fisica' AND vv.sucursal_id = c.sucursal_id AND dv.estado = 'completada'
          AND dv.fecha_resolucion >= c.abierta_en AND dv.fecha_resolucion <= coalesce(c.cerrada_en, now()::timestamp)
          AND (dv.metodo_reembolso = 'efectivo'
               OR (dv.metodo_reembolso = 'mismo_medio'
                   AND EXISTS (SELECT 1 FROM pago x WHERE x.venta_id = vv.id AND x.metodo = 'efectivo')))
    ), t AS (
        SELECT coalesce(sum(monto) FILTER (WHERE metodo = 'efectivo'), 0) AS efectivo,
               coalesce(sum(monto) FILTER (WHERE metodo = 'qr'), 0) AS qr,
               coalesce(sum(monto) FILTER (WHERE metodo = 'paypal'), 0) AS paypal,
               coalesce(sum(monto) FILTER (WHERE metodo NOT IN ('efectivo', 'qr', 'paypal')), 0) AS otros
        FROM p
    )
    SELECT (SELECT count(*) FROM v)::int,
           (SELECT coalesce(sum(total), 0) FROM v WHERE NOT fuera_de_arqueo),
           t.efectivo, t.qr, t.paypal, t.otros, m.ingresos, m.retiros, d.monto,
           CASE WHEN c.tipo = 'fisica' THEN c.monto_inicial + t.efectivo + m.ingresos - m.retiros - d.monto END
    FROM c, t, m, d;
$$ LANGUAGE sql STABLE;

CREATE OR REPLACE FUNCTION sp_abrir_caja(p_sucursal_id INTEGER, p_usuario_id INTEGER, p_monto_inicial NUMERIC)
RETURNS INTEGER AS $$
DECLARE
    v_id INTEGER;
    v_empresa INTEGER;
BEGIN
    SELECT empresa_id INTO v_empresa FROM sucursal WHERE id = p_sucursal_id;
    IF v_empresa IS NULL THEN
        RAISE EXCEPTION 'sucursal_no_encontrada';
    END IF;
    IF p_monto_inicial IS NULL OR p_monto_inicial < 0 THEN
        RAISE EXCEPTION 'caja_monto_invalido';
    END IF;
    IF EXISTS (SELECT 1 FROM caja WHERE tipo = 'fisica' AND sucursal_id = p_sucursal_id AND cerrada_en IS NULL) THEN
        RAISE EXCEPTION 'caja_ya_abierta';
    END IF;
    INSERT INTO caja (empresa_id, sucursal_id, tipo, fecha, abierta_por_id, monto_inicial)
    VALUES (v_empresa, p_sucursal_id, 'fisica', fn_dia_bolivia(now()::timestamp), p_usuario_id, p_monto_inicial)
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION sp_cerrar_caja(p_caja_id INTEGER, p_usuario_id INTEGER, p_contado NUMERIC, p_observacion TEXT)
RETURNS VOID AS $$
DECLARE
    v_caja caja%ROWTYPE;
    v_esperado NUMERIC;
BEGIN
    SELECT * INTO v_caja FROM caja WHERE id = p_caja_id FOR UPDATE;
    IF v_caja.id IS NULL THEN
        RAISE EXCEPTION 'caja_no_encontrada';
    END IF;
    IF v_caja.tipo <> 'fisica' OR v_caja.cerrada_en IS NOT NULL THEN
        RAISE EXCEPTION 'caja_no_abierta';
    END IF;
    IF p_contado IS NULL OR p_contado < 0 THEN
        RAISE EXCEPTION 'caja_monto_invalido';
    END IF;
    SELECT efectivo_esperado INTO v_esperado FROM fn_resumen_caja(p_caja_id);
    UPDATE caja SET cerrada_en = now(), cerrada_por_id = p_usuario_id, efectivo_esperado = v_esperado,
                    efectivo_contado = p_contado, diferencia = p_contado - v_esperado,
                    observacion = nullif(trim(p_observacion), '')
    WHERE id = p_caja_id;
END;
$$ LANGUAGE plpgsql;

-- Permiso del CU16 para el personal de todas las tiendas.
INSERT INTO rol_permiso (rol_id, permiso_id)
SELECT r.id, p.id FROM rol r, permiso p
WHERE r.nombre IN ('Administrador', 'Encargado de Sucursal', 'Cajero') AND p.nombre = '2P-CU16'
ON CONFLICT DO NOTHING;
INSERT INTO empresa_rol_permiso (empresa_id, rol_id, permiso_id)
SELECT e.id, r.id, p.id FROM empresa e, rol r, permiso p
WHERE r.nombre IN ('Administrador', 'Encargado de Sucursal', 'Cajero') AND p.nombre = '2P-CU16'
ON CONFLICT DO NOTHING;
"""

DOWNGRADE = r"""
DELETE FROM empresa_rol_permiso
WHERE permiso_id = (SELECT id FROM permiso WHERE nombre = '2P-CU16')
  AND rol_id IN (SELECT id FROM rol WHERE nombre IN ('Administrador', 'Encargado de Sucursal', 'Cajero'));
DELETE FROM rol_permiso
WHERE permiso_id = (SELECT id FROM permiso WHERE nombre = '2P-CU16')
  AND rol_id IN (SELECT id FROM rol WHERE nombre IN ('Administrador', 'Encargado de Sucursal', 'Cajero'));
DROP FUNCTION IF EXISTS sp_cerrar_caja(INTEGER, INTEGER, NUMERIC, TEXT);
DROP FUNCTION IF EXISTS sp_abrir_caja(INTEGER, INTEGER, NUMERIC);
DROP FUNCTION IF EXISTS fn_resumen_caja(INTEGER);
DROP TRIGGER IF EXISTS trg_venta_caja ON venta;
DROP FUNCTION IF EXISTS fn_trg_venta_caja();
DROP FUNCTION IF EXISTS fn_caja_online(INTEGER, DATE);
ALTER TABLE venta DROP COLUMN IF EXISTS fuera_de_arqueo;
ALTER TABLE venta DROP COLUMN IF EXISTS caja_id;
DROP TABLE IF EXISTS movimiento_caja;
DROP TABLE IF EXISTS caja;
DROP FUNCTION IF EXISTS fn_dia_bolivia(TIMESTAMP);
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
