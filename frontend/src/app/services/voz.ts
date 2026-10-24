// Respuestas habladas (Web Speech API, en el navegador). Se elige a mano una
// voz en español: pedir solo lang 'es-BO' no alcanza, casi ningún sistema la
// tiene y el navegador lee con su voz por defecto (en inglés) o se calla.

const PREFERIDAS = ['es-bo', 'es-419', 'es-us', 'es-mx', 'es-ar', 'es-es'];

export const soportaVoz = typeof window !== 'undefined' && 'speechSynthesis' in window;

// Las voces cargan en segundo plano: la primera vez getVoices() viene vacío.
function cargarVoces(): Promise<SpeechSynthesisVoice[]> {
  const ya = speechSynthesis.getVoices();
  if (ya.length) return Promise.resolve(ya);
  return new Promise((resolver) => {
    const listo = () => resolver(speechSynthesis.getVoices());
    speechSynthesis.addEventListener('voiceschanged', listo, { once: true });
    setTimeout(listo, 1500);
  });
}

function vozEnEspanol(voces: SpeechSynthesisVoice[]): SpeechSynthesisVoice | null {
  const es = voces.filter((v) => v.lang.toLowerCase().startsWith('es'));
  const lang = (v: SpeechSynthesisVoice) => v.lang.toLowerCase().replace('_', '-');
  for (const pref of PREFERIDAS) {
    // Entre las del mismo idioma, mejor las de red (Google / Microsoft "Online"): suenan más naturales.
    const del = es.filter((v) => lang(v) === pref);
    const voz = del.find((v) => !v.localService) ?? del[0];
    if (voz) return voz;
  }
  return es[0] ?? null;
}

const DIAS: Record<string, string> = { lun: 'lunes', mar: 'martes', mie: 'miércoles', jue: 'jueves', vie: 'viernes', sab: 'sábado', dom: 'domingo' };

// Lo que en pantalla se lee bien pero dicho suena raro (montos, horarios, abreviaturas).
export function paraVoz(texto: string): string {
  return texto
    .replace(/Bs\s*([\d.]+),00\b/g, '$1 bolivianos')
    .replace(/Bs\s*([\d.]+),(\d{2})\b/g, '$1 con $2 bolivianos')
    .replace(/\b(Lun|Mar|Mie|Jue|Vie|Sab|Dom)-(Lun|Mar|Mie|Jue|Vie|Sab|Dom)\b/gi, (_, a: string, b: string) => `de ${DIAS[a.toLowerCase()]} a ${DIAS[b.toLowerCase()]},`)
    .replace(/(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})/g, 'de $1 a $2')
    .replace(/n\.º\s*/g, 'número ')
    .replace(/[«»“”"]/g, '')
    .replace(/\s·\s/g, ', ');
}

export function callar(): void {
  if (soportaVoz) speechSynthesis.cancel();
}

// Lee el texto en voz alta. Va por frases: Chrome corta las lecturas largas.
export async function hablar(texto: string, alTerminar?: () => void): Promise<void> {
  if (!soportaVoz || !texto.trim()) {
    alTerminar?.();
    return;
  }
  speechSynthesis.cancel();
  const voz = vozEnEspanol(await cargarVoces());
  texto = paraVoz(texto);
  const frases = texto.match(/[^.!?;]+[.!?;]*/g)?.map((f) => f.trim()).filter(Boolean) ?? [texto];
  frases.forEach((frase, i) => {
    const u = new SpeechSynthesisUtterance(frase);
    u.lang = voz?.lang ?? 'es-ES';
    if (voz) u.voice = voz;
    if (i === frases.length - 1 && alTerminar) {
      u.onend = alTerminar;
      u.onerror = alTerminar;
    }
    speechSynthesis.speak(u);
  });
}
