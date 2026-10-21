// Textos legales de la plataforma: Política de privacidad (/privacidad) y
// Términos y condiciones (/terminos). Describen lo que la app hace de verdad
// (qué guarda y a qué servicios lo manda): si eso cambia, se cambia acá.

export interface SeccionLegal {
  id: string;
  titulo: string;
  parrafos?: string[];
  lista?: string[];
  // Texto que va después de la lista.
  cierre?: string;
}

export interface DocumentoLegal {
  titulo: string;
  bajada: string;
  actualizado: string;
  secciones: SeccionLegal[];
}

export const CONTACTO_LEGAL = {
  correo: 'fcalanigarcia7@gmail.com',
  whatsappTexto: '+591 73766956',
  whatsappNumero: '59173766956',
};

export const ACTUALIZADO = '21 de octubre de 2026';

export const PRIVACIDAD: DocumentoLegal = {
  titulo: 'Política de privacidad',
  bajada:
    'Qué datos guardamos cuando usas Arlani Boutiques, para qué los usamos, con quién se comparten y cómo puedes pedir que los corrijamos o borremos.',
  actualizado: ACTUALIZADO,
  secciones: [
    {
      id: 'quienes-somos',
      titulo: 'Quiénes somos',
      parrafos: [
        'Arlani Boutiques es una plataforma donde boutiques de Bolivia venden sus prendas en línea y en sus tiendas físicas. Una sola cuenta te sirve para comprar en cualquiera de las boutiques de Arlani.',
        'Esta política explica cómo tratamos tus datos personales cuando visitas el sitio, usas la aplicación móvil o trabajas en una boutique que usa Arlani.',
      ],
    },
    {
      id: 'datos',
      titulo: 'Qué datos guardamos',
      lista: [
        'Datos de tu cuenta: nombre, correo electrónico y, si los cargas, teléfono y dirección. Tu contraseña se guarda cifrada: nunca la vemos ni la guardamos tal cual.',
        'Si entras con Google: solo recibimos tu nombre y tu correo de Google. No recibimos tu contraseña de Google ni accedemos a tu correo, contactos o archivos.',
        'Tu actividad en las boutiques: carrito, reservas, compras, devoluciones, calificaciones, las prendas que miraste y los mensajes que escribes al asistente virtual.',
        'Pagos: los pagos con PayPal o tarjeta los procesa PayPal; nosotros no recibimos ni guardamos los datos de tu tarjeta. Si pagas con QR, guardamos la imagen del comprobante que subes.',
        'Personal de las boutiques: al marcar asistencia se guardan la foto, la ubicación y la hora del marcado.',
        'Datos técnicos: la dirección IP y si usaste la web o la app quedan en un registro de actividad, para la seguridad de las cuentas.',
      ],
    },
    {
      id: 'para-que',
      titulo: 'Para qué los usamos',
      lista: [
        'Crear tu cuenta, iniciar sesión y mantenerla segura.',
        'Procesar tus compras, reservas, pagos y devoluciones en la boutique que elegiste.',
        'Enviarte correos sobre tu cuenta y tus pedidos (bienvenida, recuperación de contraseña, estado de una reserva o un pago).',
        'Mostrarte recomendaciones de prendas según lo que compraste y miraste.',
        'Responder tus consultas en el asistente virtual.',
        'Detectar accesos indebidos y llevar un registro de lo que se hace en cada boutique.',
      ],
      cierre: 'No vendemos tus datos ni los usamos para publicidad de terceros.',
    },
    {
      id: 'compartir',
      titulo: 'Con quién se comparten',
      parrafos: [
        'Cada boutique solo ve los datos de los clientes que compraron, reservaron o usaron sus servicios, y solo lo necesario para atenderte (nombre, contacto y tu pedido). Una boutique no puede ver los clientes de otra.',
        'Para que Arlani funcione usamos estos servicios, que tratan datos por nosotros:',
      ],
      lista: [
        'Supabase: base de datos y almacenamiento de imágenes (fotos de productos, comprobantes y fotos de asistencia).',
        'Render: los servidores donde corre la plataforma.',
        'Google: inicio de sesión con Google, y Gemini para redactar las respuestas del asistente y el motivo de cada recomendación (recibe tus mensajes al asistente y el nombre de las prendas que compraste).',
        'PayPal: pagos en línea.',
        'Decart: el probador de realidad aumentada. La foto o la imagen de tu cámara se envía a Decart solo para generar la prueba; Arlani no la guarda.',
        'Gmail: envío de los correos de la plataforma.',
      ],
      cierre: 'Estos servidores están fuera de Bolivia (Brasil y Estados Unidos).',
    },
    {
      id: 'navegador',
      titulo: 'Lo que se guarda en tu navegador',
      parrafos: [
        'Para mantener tu sesión iniciada guardamos un identificador en el almacenamiento local de tu navegador. Se borra al cerrar sesión. No usamos cookies de publicidad ni herramientas de rastreo de terceros.',
      ],
    },
    {
      id: 'conservacion',
      titulo: 'Cuánto tiempo los guardamos',
      parrafos: [
        'Guardamos tus datos mientras tengas tu cuenta. Si pides darla de baja, la desactivamos y borramos los datos que no hagan falta conservar; los registros de compras y pagos pueden guardarse el tiempo necesario para respaldar esas operaciones.',
      ],
    },
    {
      id: 'derechos',
      titulo: 'Tus derechos',
      lista: [
        'Ver y corregir tus datos desde tu perfil.',
        'Pedirnos una copia de tus datos, o que los corrijamos o borremos.',
        'Dar de baja tu cuenta.',
        'Quitar el acceso de Arlani a tu cuenta de Google en myaccount.google.com/permissions.',
      ],
      cierre: 'Para cualquiera de estos pedidos escríbenos (ver «Contacto»); te respondemos en un plazo de 15 días.',
    },
    {
      id: 'menores',
      titulo: 'Menores de edad',
      parrafos: ['Arlani está pensado para mayores de 18 años. Si eres menor, usa la plataforma junto a un adulto responsable.'],
    },
    {
      id: 'cambios',
      titulo: 'Cambios en esta política',
      parrafos: [
        'Si cambiamos esta política actualizaremos la fecha de arriba y, si el cambio es importante, te avisaremos por correo o dentro de la plataforma.',
      ],
    },
  ],
};

export const TERMINOS: DocumentoLegal = {
  titulo: 'Términos y condiciones',
  bajada: 'Las reglas para usar Arlani Boutiques, tanto si compras en una boutique como si tienes la tuya en la plataforma.',
  actualizado: ACTUALIZADO,
  secciones: [
    {
      id: 'aceptacion',
      titulo: 'Aceptación',
      parrafos: [
        'Al crear una cuenta o usar Arlani Boutiques (el sitio web o la aplicación móvil) aceptas estos términos y la Política de privacidad. Si no estás de acuerdo, no uses la plataforma.',
      ],
    },
    {
      id: 'servicio',
      titulo: 'Qué es Arlani',
      parrafos: [
        'Arlani es una plataforma que ofrece a las boutiques las herramientas para vender en línea y en sus tiendas: catálogo, inventario, ventas, reservas, reportes y más. Cada boutique vende sus propios productos y es responsable de ellos; Arlani no es el vendedor.',
      ],
    },
    {
      id: 'cuenta',
      titulo: 'Tu cuenta',
      lista: [
        'Los datos que cargues tienen que ser verdaderos.',
        'Eres responsable de cuidar tu contraseña y de lo que se haga con tu cuenta.',
        'Si detectas un acceso que no hiciste, cambia tu contraseña y avísanos.',
        'Podemos desactivar cuentas que se usen para fraude o que incumplan estos términos.',
      ],
    },
    {
      id: 'compras',
      titulo: 'Compras, reservas y devoluciones',
      lista: [
        'Los precios, el stock y las condiciones de cada prenda los define la boutique que la vende.',
        'Una reserva aparta la prenda hasta la fecha y la hora que elegiste para pasar a pagarla y recogerla en la sucursal; si no vas, la reserva vence y la prenda vuelve a estar disponible.',
        'Los pagos en línea se hacen con PayPal o tarjeta (procesados por PayPal) o con QR; el pago con QR queda confirmado cuando la boutique verifica el comprobante.',
        'Las devoluciones se piden desde tu perfil dentro del plazo que se indica en cada compra y las aprueba la boutique.',
      ],
    },
    {
      id: 'boutiques',
      titulo: 'Si tienes una boutique en Arlani',
      lista: [
        'Usas la plataforma según el plan que contrataste (Prueba, Básico o Profesional) y sus límites, como la cantidad de sucursales activas.',
        'La suscripción vale por el periodo contratado (mensual, anual o los días de prueba). Para seguir usando Arlani al terminar, hay que renovarla.',
        'Eres responsable de tu catálogo, tus precios, el trato con tus clientes y el uso que tu personal hace de la plataforma.',
        'Solo puedes usar los datos de tus clientes para atenderlos, y tienes que cuidarlos según la Política de privacidad.',
        'Podemos suspender una boutique por falta de pago o por un uso indebido de la plataforma.',
      ],
    },
    {
      id: 'uso',
      titulo: 'Uso permitido',
      parrafos: ['No está permitido:'],
      lista: [
        'Usar Arlani para fraudes, estafas o ventas de productos ilegales.',
        'Intentar entrar a cuentas o datos que no son tuyos, o alterar el funcionamiento de la plataforma.',
        'Subir contenido ofensivo o que infrinja derechos de otras personas.',
      ],
    },
    {
      id: 'ia',
      titulo: 'Probador virtual y asistente con IA',
      parrafos: [
        'El probador de realidad aumentada muestra una aproximación de cómo te quedaría una prenda; el resultado puede no ser exacto. El asistente virtual y las recomendaciones usan inteligencia artificial y pueden equivocarse: ante cualquier duda sobre precio, stock o talla, consulta a la boutique.',
      ],
    },
    {
      id: 'disponibilidad',
      titulo: 'Disponibilidad y responsabilidad',
      parrafos: [
        'Trabajamos para que Arlani esté siempre disponible, pero puede haber interrupciones por mantenimiento o por fallas de los servicios que usamos. Arlani no responde por la calidad de los productos que vende cada boutique ni por los acuerdos entre una boutique y sus clientes.',
      ],
    },
    {
      id: 'cambios',
      titulo: 'Cambios y ley aplicable',
      parrafos: [
        'Podemos actualizar estos términos; la fecha de arriba indica la última versión. Seguir usando la plataforma después de un cambio significa que lo aceptas. Estos términos se rigen por las leyes del Estado Plurinacional de Bolivia.',
      ],
    },
  ],
};
