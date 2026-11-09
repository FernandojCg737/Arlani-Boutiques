"""Numeracion propia de cada tienda (#1, #2, ...) para lo que se muestra con
numero: ventas, reservas, devoluciones, cambios de prenda, cajas, operaciones
offline y backups. El id sigue siendo el de toda la tabla (lo usan la API y
las llaves foraneas); `numero` es el que ve la tienda.

- Cada tienda (y el sistema completo, para los backups) tiene una secuencia
  por tabla (numero_<tabla>_<empresa>): nunca se repite un numero, aunque se
  borre el ultimo.
- Un trigger BEFORE INSERT (trg_0_numero, corre antes que los demas) lo asigna
  si viene vacio; las filas que ya existian se numeran por orden de creacion.
- fn_numerar_faltantes() resincroniza las secuencias y numera lo que quedo sin
  numero (lo llama la restauracion de backups, que apaga los triggers).
- Los textos que arma la base (notificaciones "Tu reserva #...", referencias
  de inventario "Venta presencial #...", comisiones) pasan a usar el numero.

Revision ID: b2d4f6a8c013
Revises: a1c3e5f7b902
Create Date: 2026-11-08
"""

import re

from alembic import op

revision = "b2d4f6a8c013"
down_revision = "a1c3e5f7b902"
branch_labels = None
depends_on = None

# tabla -> expresion SQL con la empresa de la fila X (0 = sistema completo)
EMPRESA = {
    "venta": "(SELECT s.empresa_id FROM sucursal s WHERE s.id = X.sucursal_id)",
    "reserva": "(SELECT s.empresa_id FROM sucursal s WHERE s.id = X.sucursal_id)",
    "cambio_prenda": "(SELECT s.empresa_id FROM sucursal s WHERE s.id = X.sucursal_id)",
    "devolucion": "(SELECT s.empresa_id FROM venta v JOIN sucursal s ON s.id = v.sucursal_id WHERE v.id = X.venta_id)",
    "caja": "X.empresa_id",
    "operacion_offline": "X.empresa_id",
    "backup": "coalesce(X.empresa_id, 0)",
}

FUNCIONES = r"""
CREATE OR REPLACE FUNCTION fn_siguiente_numero(p_tabla text, p_empresa integer) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
    v_seq text := 'numero_' || p_tabla || '_' || coalesce(p_empresa, 0);
BEGIN
    BEGIN
        EXECUTE format('CREATE SEQUENCE IF NOT EXISTS %I', v_seq);
    EXCEPTION WHEN unique_violation OR duplicate_table THEN
        NULL;  -- otra transaccion la creo al mismo tiempo
    END;
    RETURN nextval(v_seq::regclass);
END;
$$;

CREATE OR REPLACE FUNCTION fn_asignar_numero() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
    v_empresa integer;
BEGIN
    IF NEW.numero IS NOT NULL THEN
        RETURN NEW;
    END IF;
    CASE TG_TABLE_NAME
        WHEN 'venta', 'reserva', 'cambio_prenda' THEN
            SELECT empresa_id INTO v_empresa FROM sucursal WHERE id = NEW.sucursal_id;
        WHEN 'devolucion' THEN
            SELECT s.empresa_id INTO v_empresa FROM venta v JOIN sucursal s ON s.id = v.sucursal_id WHERE v.id = NEW.venta_id;
        WHEN 'backup' THEN
            v_empresa := coalesce(NEW.empresa_id, 0);
        ELSE
            v_empresa := NEW.empresa_id;
    END CASE;
    NEW.numero := fn_siguiente_numero(TG_TABLE_NAME, v_empresa);
    RETURN NEW;
END;
$$;

-- Numero que ve la tienda (el id si todavia no tiene).
CREATE OR REPLACE FUNCTION fn_numero_venta(p_id integer) RETURNS integer
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
    SELECT coalesce((SELECT numero FROM venta WHERE id = p_id), p_id)
$$;
CREATE OR REPLACE FUNCTION fn_numero_reserva(p_id integer) RETURNS integer
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
    SELECT coalesce((SELECT numero FROM reserva WHERE id = p_id), p_id)
$$;
CREATE OR REPLACE FUNCTION fn_numero_cambio(p_id integer) RETURNS integer
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
    SELECT coalesce((SELECT numero FROM cambio_prenda WHERE id = p_id), p_id)
$$;
"""


def _numerar_faltantes() -> str:
    """fn_numerar_faltantes: deja cada secuencia por encima del mayor numero
    usado en su tienda y numera (por orden de id) las filas sin numero."""
    partes = []
    for tabla, expr in EMPRESA.items():
        empresa = expr.replace("X.", "x.")
        partes.append(f"""
    FOR r IN SELECT {empresa} AS empresa, max(x.numero) AS maximo FROM {tabla} x
             WHERE x.numero IS NOT NULL GROUP BY 1 LOOP
        v_seq := 'numero_{tabla}_' || coalesce(r.empresa, 0);
        EXECUTE format('CREATE SEQUENCE IF NOT EXISTS %I', v_seq);
        EXECUTE format('SELECT last_value, is_called FROM %I', v_seq) INTO v_ultimo, v_usada;
        IF r.maximo > (CASE WHEN v_usada THEN v_ultimo ELSE 0 END) THEN
            PERFORM setval(v_seq::regclass, r.maximo);
        END IF;
    END LOOP;
    FOR r IN SELECT x.id, {empresa} AS empresa FROM {tabla} x WHERE x.numero IS NULL ORDER BY x.id LOOP
        UPDATE {tabla} SET numero = fn_siguiente_numero('{tabla}', r.empresa) WHERE id = r.id;
        n := n + 1;
    END LOOP;""")
    return ("CREATE OR REPLACE FUNCTION fn_numerar_faltantes() RETURNS integer\n"
            "LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$\n"
            "DECLARE\n    r record;\n    n integer := 0;\n    v_seq text;\n    v_ultimo bigint;\n    v_usada boolean;\nBEGIN" + "".join(partes) + "\n    RETURN n;\nEND;\n$$;")


# Textos de las funciones de la base: lo que va despues de "#' || ".
CAMBIOS_TEXTO = [
    (r"(#' \|\| )(NEW\.venta_id|v_venta_id|p_venta_id|v_c\.venta_id)\b", r"\1fn_numero_venta(\2)"),
    (r"(#' \|\| )NEW\.id\b", r"\1coalesce(NEW.numero, NEW.id)"),
    (r"(#' \|\| )(r\.id|res\.id)\b", r"\1fn_numero_reserva(\2)"),
    (r"(#' \|\| )v_c\.id\b", r"\1fn_numero_cambio(v_c.id)"),
]
DESHACER_TEXTO = [
    (r"fn_numero_venta\(([\w.]+)\)", r"\1"),
    (r"coalesce\(NEW\.numero, NEW\.id\)", "NEW.id"),
    (r"fn_numero_reserva\(([\w.]+)\)", r"\1"),
    (r"fn_numero_cambio\(([\w.]+)\)", r"\1"),
]
# Funciones cuyo "#' || NEW.id" es de una tabla numerada.
CON_NEW_ID = ("fn_notificar_reserva_creada", "fn_notificar_reserva_estado", "fn_trg_venta_comision",
              "fn_trg_devolucion_deuda")


def _ejecutar(sql: str) -> None:
    # Cursor de psycopg2 sin parametros: los % y : del cuerpo de las funciones
    # no se interpretan.
    cur = op.get_bind().connection.cursor()
    try:
        cur.execute(sql)
    finally:
        cur.close()


def _reescribir_funciones(cambios) -> None:
    cur = op.get_bind().connection.cursor()
    cur.execute(
        "SELECT p.proname, pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'public' AND p.prokind = 'f' AND p.proname NOT LIKE 'fn\\_numero\\_%' "
        "AND p.proname NOT IN ('fn_numerar_faltantes', 'fn_asignar_numero', 'fn_siguiente_numero')"
    )
    filas = cur.fetchall()
    cur.close()
    for nombre, definicion in filas:
        nueva = definicion
        for patron, reemplazo in cambios:
            if "NEW" in patron and "NEW\\.id" in patron and nombre not in CON_NEW_ID:
                continue
            nueva = re.sub(patron, reemplazo, nueva)
        if nueva != definicion:
            _ejecutar(nueva)


def upgrade() -> None:
    for tabla in EMPRESA:
        op.execute(f"ALTER TABLE {tabla} ADD COLUMN IF NOT EXISTS numero INTEGER")
    _ejecutar(FUNCIONES)
    _ejecutar(_numerar_faltantes())

    # Lo que ya existe: numerado por orden de creacion dentro de cada tienda.
    for tabla, expr in EMPRESA.items():
        empresa = expr.replace("X.", "x.")
        op.execute(
            f"""UPDATE {tabla} t SET numero = o.n FROM (
                    SELECT x.id, row_number() OVER (PARTITION BY {empresa} ORDER BY x.id) AS n FROM {tabla} x
                ) o WHERE o.id = t.id AND t.numero IS NULL"""
        )
    op.execute("SELECT fn_numerar_faltantes()")

    for tabla in EMPRESA:
        op.execute(f"DROP TRIGGER IF EXISTS trg_0_numero ON {tabla}")
        op.execute(f"CREATE TRIGGER trg_0_numero BEFORE INSERT ON {tabla} FOR EACH ROW EXECUTE FUNCTION fn_asignar_numero()")
    # Donde la empresa es una columna de la tabla, el numero no se repite.
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_caja_numero ON caja (empresa_id, numero)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_operacion_offline_numero ON operacion_offline (empresa_id, numero)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_backup_numero ON backup ((coalesce(empresa_id, 0)), numero)")

    _reescribir_funciones(CAMBIOS_TEXTO)


def downgrade() -> None:
    _reescribir_funciones(DESHACER_TEXTO)
    for tabla in EMPRESA:
        op.execute(f"DROP TRIGGER IF EXISTS trg_0_numero ON {tabla}")
    for indice in ("ux_caja_numero", "ux_operacion_offline_numero", "ux_backup_numero"):
        op.execute(f"DROP INDEX IF EXISTS {indice}")
    op.execute("DROP FUNCTION IF EXISTS fn_numerar_faltantes()")
    op.execute("DROP FUNCTION IF EXISTS fn_asignar_numero()")
    for f in ("fn_numero_venta", "fn_numero_reserva", "fn_numero_cambio"):
        op.execute(f"DROP FUNCTION IF EXISTS {f}(integer)")
    _ejecutar(
        "DO $$ DECLARE s record; BEGIN FOR s IN SELECT relname FROM pg_class WHERE relkind = 'S' AND relname LIKE 'numero\\_%' "
        "LOOP EXECUTE format('DROP SEQUENCE %I', s.relname); END LOOP; END $$;"
    )
    op.execute("DROP FUNCTION IF EXISTS fn_siguiente_numero(text, integer)")
    for tabla in EMPRESA:
        op.execute(f"ALTER TABLE {tabla} DROP COLUMN IF EXISTS numero")
