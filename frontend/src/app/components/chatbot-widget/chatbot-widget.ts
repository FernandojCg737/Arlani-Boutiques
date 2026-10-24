import { DatePipe } from '@angular/common';
import {
  Component,
  DestroyRef,
  ElementRef,
  OnDestroy,
  OnInit,
  afterNextRender,
  computed,
  effect,
  inject,
  input,
  signal,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router } from '@angular/router';
import { filter } from 'rxjs/operators';
import { Auth } from '../../services/auth';
import { ChatbotService } from '../../services/chatbot';
import { TiendaActiva } from '../../services/tienda-activa';
import { hablar as leerEnVoz } from '../../services/voz';

// El navegador todavia no tiene tipos DOM oficiales para el Web Speech API
// (sigue siendo un borrador) -- se declara lo minimo que se usa.
interface SpeechRecognitionResultLike {
  results: { [i: number]: { [j: number]: { transcript: string } } };
}
interface SpeechRecognitionLike extends EventTarget {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  start(): void;
  stop(): void;
  onresult: ((ev: SpeechRecognitionResultLike) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
}

// CU19 (cliente): burbuja flotante con el chatbot -- solo para clientes con
// sesion iniciada. El reconocimiento de voz (dictar la pregunta) y la
// sintesis de voz (que el bot conteste hablado) se resuelven 100% en el
// navegador con la Web Speech API, sin pasar por el backend.
@Component({
  selector: 'app-chatbot-widget',
  imports: [DatePipe],
  templateUrl: './chatbot-widget.html',
  host: { '[class.chatbot--universal]': 'universal()' },
  styleUrl: './chatbot-widget.scss',
})
export class ChatbotWidget implements OnInit, OnDestroy {
  protected readonly auth = inject(Auth);
  protected readonly chat = inject(ChatbotService);
  private readonly tiendaActiva = inject(TiendaActiva);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  // true en el catálogo universal: el asistente de Arlani, con todas las tiendas.
  readonly universal = input(false);
  protected readonly titulo = computed(() =>
    this.universal() ? 'Asistente Arlani Boutiques' : `Asistente ${this.tiendaActiva.nombre()}`.trim(),
  );
  protected readonly subtitulo = computed(() =>
    this.universal()
      ? 'Prendas de todas las tiendas, planes y cómo crear tu boutique'
      : 'Pregunta por stock, precios o nuestros servicios',
  );

  protected readonly esClienteConSesion = computed(
    () => !!this.auth.currentUser() && this.auth.currentUser()?.tipo === 'cliente',
  );
  // El universal (portada y catálogo de Arlani) también lo usa quien no
  // tiene sesión; el de una tienda, solo sus clientes con sesión.
  protected readonly visible = computed(() => this.universal() || this.esClienteConSesion());

  protected readonly abierto = signal(false);
  protected readonly texto = signal('');
  protected readonly vozActiva = signal(true);
  protected readonly escuchando = signal(false);

  // Igual que el flotante de WhatsApp: mientras el ".hero" (a pantalla
  // completa) esta a la vista, el icono queda oculto para no taparlo -- se
  // muestra solo apenas el usuario baja y el hero sale del viewport. En
  // paginas sin hero queda visible siempre.
  protected readonly heroVisible = signal(false);
  private heroObserver?: IntersectionObserver;

  private readonly mensajesEl = viewChild<ElementRef<HTMLDivElement>>('mensajesEl');
  private reconocimiento: SpeechRecognitionLike | null = null;
  private cargado = false;

  protected readonly soportaReconocimiento =
    typeof window !== 'undefined' && !!((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition);
  protected readonly soportaSintesis = typeof window !== 'undefined' && 'speechSynthesis' in window;

  constructor() {
    // Se hace scroll al ultimo mensaje cada vez que la lista cambia.
    effect(() => {
      this.chat.mensajes();
      queueMicrotask(() => {
        const el = this.mensajesEl()?.nativeElement;
        if (el) el.scrollTop = el.scrollHeight;
      });
    });

    afterNextRender(() => this.configurarReconocimiento());
  }

  ngOnInit(): void {
    this.chat.universal.set(this.universal());
    if (this.visible()) void this.chat.cargar();

    this.watchCurrentRouteHero();
    this.router.events
      .pipe(
        filter((event) => event instanceof NavigationEnd),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => {
        // El componente de la nueva ruta recien se pinta despues de este
        // evento; se espera un tick para que ".hero" ya exista (o no) en el DOM.
        setTimeout(() => this.watchCurrentRouteHero());
      });
  }

  private watchCurrentRouteHero(): void {
    this.heroObserver?.disconnect();

    const hero = document.querySelector('.hero');
    if (!hero) {
      this.heroVisible.set(false);
      return;
    }

    this.heroObserver = new IntersectionObserver(([entry]) => {
      this.heroVisible.set(entry.isIntersecting);
    });
    this.heroObserver.observe(hero);
  }

  ngOnDestroy(): void {
    this.heroObserver?.disconnect();
    this.reconocimiento?.stop();
    if (this.soportaSintesis) window.speechSynthesis.cancel();
  }

  protected toggleAbierto(): void {
    this.abierto.update((v) => !v);
    if (this.abierto() && !this.cargado) {
      this.cargado = true;
      void this.chat.cargar();
    }
  }

  protected toggleVoz(): void {
    this.vozActiva.update((v) => !v);
    if (!this.vozActiva() && this.soportaSintesis) window.speechSynthesis.cancel();
  }

  private configurarReconocimiento(): void {
    if (!this.soportaReconocimiento) return;
    const Ctor = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    const reconocimiento: SpeechRecognitionLike = new Ctor();
    reconocimiento.lang = 'es-BO';
    reconocimiento.interimResults = false;
    reconocimiento.continuous = false;

    reconocimiento.onresult = (ev) => {
      const transcript = ev.results[0][0].transcript;
      this.texto.set(transcript);
      this.escuchando.set(false);
      void this.enviar();
    };
    reconocimiento.onerror = () => this.escuchando.set(false);
    reconocimiento.onend = () => this.escuchando.set(false);

    this.reconocimiento = reconocimiento;
  }

  protected escuchar(): void {
    if (!this.reconocimiento || this.escuchando()) return;
    this.escuchando.set(true);
    this.reconocimiento.start();
  }

  protected async enviar(): Promise<void> {
    const mensaje = this.texto();
    if (!mensaje.trim() || this.chat.enviando()) return;
    this.texto.set('');

    const respuesta = await this.chat.enviar(mensaje);
    if (respuesta && this.vozActiva() && this.soportaSintesis) {
      this.hablar(respuesta.mensaje);
    }
  }

  private hablar(texto: string): void {
    void leerEnVoz(texto);
  }
}
