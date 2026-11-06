import { DecimalPipe } from '@angular/common';
import { Component, ElementRef, OnDestroy, OnInit, computed, inject, input, output, signal, viewChild } from '@angular/core';
import { RouterLink } from '@angular/router';
import {
  DisconnectReason,
  LocalVideoTrack,
  Participant,
  RemoteParticipant,
  RemoteTrack,
  Room,
  RoomEvent,
  Track,
} from 'livekit-client';
import { Auth } from '../../services/auth';
import { Cart } from '../../services/cart';
import {
  ComentarioLive,
  EMOJIS_LIVE,
  EspectadorLive,
  LiveApi,
  MensajeLive,
  ProductoLive,
  SalaLive,
  VarianteLive,
} from '../../services/live';
import { mensajeError } from '../../services/plataforma';

interface Reaccion {
  id: number;
  emoji: string;
  izquierda: number;
}

interface Conectado {
  usuarioId: number;
  nombre: string;
}

// CU22: la sala de un live. Si quien entra es el vendedor (personal de la
// tienda con el permiso), transmite su cámara y micrófono y modera; si no, mira,
// comenta, reacciona y agrega la prenda fijada al carrito.
@Component({
  selector: 'app-live-sala',
  imports: [DecimalPipe, RouterLink],
  templateUrl: './live-sala.html',
  styleUrl: './live-sala.scss',
})
export class LiveSala implements OnInit, OnDestroy {
  readonly liveId = input.required<number>();
  readonly terminado = output<void>();

  private readonly api = inject(LiveApi);
  private readonly auth = inject(Auth);
  private readonly cart = inject(Cart);
  private readonly video = viewChild<ElementRef<HTMLVideoElement>>('video');
  private readonly audios = viewChild<ElementRef<HTMLDivElement>>('audios');
  private readonly lista = viewChild<ElementRef<HTMLDivElement>>('lista');
  private room: Room | null = null;
  private siguienteReaccion = 0;

  protected readonly emojis = EMOJIS_LIVE;
  protected readonly sala = signal<SalaLive | null>(null);
  protected readonly comentarios = signal<ComentarioLive[]>([]);
  protected readonly productos = signal<ProductoLive[]>([]);
  protected readonly espectadores = signal<EspectadorLive[]>([]);
  protected readonly conectados = signal<Conectado[]>([]);
  protected readonly reacciones = signal<Reaccion[]>([]);
  protected readonly silenciado = signal(false);
  protected readonly cargando = signal(true);
  protected readonly error = signal('');
  protected readonly fin = signal<string | null>(null);
  protected readonly sinSonido = signal(false);
  protected readonly sinVideo = signal(true);
  protected readonly micActivo = signal(true);
  protected readonly camActiva = signal(true);
  protected readonly texto = signal('');
  protected readonly enviando = signal(false);
  protected readonly variante = signal('');
  protected readonly agregando = signal(false);
  protected readonly avisoCarrito = signal('');
  protected readonly panel = signal<'comentarios' | 'espectadores' | 'prendas'>('comentarios');
  protected readonly terminando = signal(false);

  protected readonly vendedor = computed(() => this.sala()?.vendedor ?? false);
  // El SuperAdministrador y el vendedor moderan.
  protected readonly modera = computed(() => this.vendedor() || this.auth.isSuperAdmin());
  protected readonly fijado = computed(() => this.productos().find((p) => p.fijado) ?? null);
  protected readonly puedeComprar = computed(() => !!this.auth.currentUser() && !this.auth.isStaff());
  protected readonly bloqueoDe = computed(() => {
    const mapa: Record<number, string | null> = {};
    for (const e of this.espectadores()) mapa[e.usuario_id] = e.bloqueo;
    return mapa;
  });

  async ngOnInit(): Promise<void> {
    try {
      const sala = await this.api.sala(this.liveId());
      this.sala.set(sala);
      this.comentarios.set(sala.comentarios);
      this.productos.set(sala.productos);
      this.espectadores.set(sala.espectadores ?? []);
      this.silenciado.set(sala.silenciado);
      // Primero se dibuja la sala (el <video> tiene que existir) y luego se conecta.
      this.cargando.set(false);
      await new Promise((listo) => setTimeout(listo));
      await this.conectar(sala);
    } catch (err) {
      this.error.set(mensajeError(err, 'No se pudo entrar al live.'));
    } finally {
      this.cargando.set(false);
    }
  }

  ngOnDestroy(): void {
    void this.room?.disconnect();
  }

  private async conectar(sala: SalaLive): Promise<void> {
    const room = new Room({ adaptiveStream: true, dynacast: true });
    this.room = room;
    room
      .on(RoomEvent.TrackSubscribed, (track: RemoteTrack) => this.mostrarPista(track))
      .on(RoomEvent.TrackUnsubscribed, (track: RemoteTrack) => {
        track.detach();
        if (track.kind === Track.Kind.Video) this.sinVideo.set(true);
      })
      .on(RoomEvent.DataReceived, (datos: Uint8Array, _p?: RemoteParticipant, _k?: unknown, tema?: string) => {
        if (tema === 'live') this.recibir(JSON.parse(new TextDecoder().decode(datos)) as MensajeLive);
      })
      .on(RoomEvent.ParticipantConnected, () => this.actualizarConectados())
      .on(RoomEvent.ParticipantDisconnected, () => this.actualizarConectados())
      .on(RoomEvent.AudioPlaybackStatusChanged, () => this.sinSonido.set(!room.canPlaybackAudio))
      .on(RoomEvent.Disconnected, (motivo?: DisconnectReason) => {
        if (motivo === DisconnectReason.PARTICIPANT_REMOVED) this.fin.set('La tienda te sacó de este live.');
        else if (motivo === DisconnectReason.ROOM_DELETED && !this.fin()) this.fin.set('El live terminó.');
      });

    await room.connect(sala.url, sala.token);
    this.actualizarConectados();
    if (sala.vendedor) {
      await room.localParticipant.enableCameraAndMicrophone();
      const camara = room.localParticipant.getTrackPublication(Track.Source.Camera)?.track as LocalVideoTrack | undefined;
      const video = this.video()?.nativeElement;
      if (camara && video) {
        camara.attach(video);
        this.sinVideo.set(false);
      }
      // Ya se está transmitiendo: empieza la grabación.
      void this.api.grabar(sala.live.id).catch(() => undefined);
    } else {
      for (const p of room.remoteParticipants.values()) {
        for (const pub of p.trackPublications.values()) {
          if (pub.track) this.mostrarPista(pub.track as RemoteTrack);
        }
      }
      this.sinSonido.set(!room.canPlaybackAudio);
    }
    this.bajarComentarios();
  }

  private mostrarPista(track: RemoteTrack): void {
    if (track.kind === Track.Kind.Video) {
      const video = this.video()?.nativeElement;
      if (video) {
        track.attach(video);
        this.sinVideo.set(false);
      }
    } else if (track.kind === Track.Kind.Audio) {
      this.audios()?.nativeElement.appendChild(track.attach());
    }
  }

  private actualizarConectados(): void {
    const room = this.room;
    if (!room) return;
    const lista: Conectado[] = [];
    for (const p of room.remoteParticipants.values()) {
      if (this.rolDe(p) === 'espectador') lista.push({ usuarioId: Number(p.identity.slice(1)), nombre: p.name || p.identity });
    }
    this.conectados.set(lista);
    if (this.modera()) void this.api.espectadores(this.liveId()).then((e) => this.espectadores.set(e), () => undefined);
  }

  private rolDe(p: Participant): string {
    try {
      return JSON.parse(p.metadata || '{}').rol ?? '';
    } catch {
      return '';
    }
  }

  private recibir(m: MensajeLive): void {
    switch (m.tipo) {
      case 'comentario':
        if (!this.comentarios().some((c) => c.id === m.comentario.id)) {
          this.comentarios.update((cs) => [...cs.slice(-199), m.comentario]);
          this.bajarComentarios();
        }
        break;
      case 'ocultar':
        this.comentarios.update((cs) =>
          this.modera() ? cs.map((c) => (c.id === m.id ? { ...c, oculto: true } : c)) : cs.filter((c) => c.id !== m.id),
        );
        break;
      case 'productos':
        this.productos.set(m.productos);
        this.variante.set('');
        break;
      case 'reaccion':
        this.flotar(m.emoji);
        break;
      case 'bloqueo':
        if (m.usuario_id === this.auth.currentUser()?.id) this.silenciado.set(m.bloqueo !== null);
        if (this.modera()) void this.api.espectadores(this.liveId()).then((e) => this.espectadores.set(e), () => undefined);
        break;
      case 'fin':
        this.fin.set(m.motivo ?? 'El live terminó.');
        void this.room?.disconnect();
        break;
    }
  }

  private bajarComentarios(): void {
    setTimeout(() => {
      const el = this.lista()?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    });
  }

  private flotar(emoji: string): void {
    const id = ++this.siguienteReaccion;
    this.reacciones.update((rs) => [...rs.slice(-24), { id, emoji, izquierda: 10 + Math.random() * 70 }]);
    setTimeout(() => this.reacciones.update((rs) => rs.filter((r) => r.id !== id)), 2600);
  }

  protected activarSonido(): void {
    void this.room?.startAudio().then(() => this.sinSonido.set(false));
  }

  // ------------------------------------------------------------ espectador

  protected async comentar(): Promise<void> {
    const texto = this.texto().trim();
    if (!texto || this.enviando()) return;
    this.enviando.set(true);
    try {
      const c = await this.api.comentar(this.liveId(), texto);
      this.texto.set('');
      if (!this.comentarios().some((x) => x.id === c.id)) {
        this.comentarios.update((cs) => [...cs, c]);
        this.bajarComentarios();
      }
    } catch (err) {
      this.error.set(mensajeError(err, 'No se pudo enviar el comentario.'));
      setTimeout(() => this.error.set(''), 3500);
    } finally {
      this.enviando.set(false);
    }
  }

  protected agregarEmoji(emoji: string): void {
    this.texto.update((t) => t + emoji);
  }

  protected reaccionar(emoji: string): void {
    this.flotar(emoji);
    void this.api.reaccionar(this.liveId(), emoji).catch(() => undefined);
  }

  protected claveVariante(v: VarianteLive): string {
    return `${v.talla_id}-${v.color_id}-${v.sucursal_id}`;
  }

  protected async agregarAlCarrito(p: ProductoLive): Promise<void> {
    const v = p.variantes.find((x) => this.claveVariante(x) === this.variante());
    if (!v) {
      this.avisoCarrito.set('Elige talla y color.');
      return;
    }
    this.agregando.set(true);
    this.avisoCarrito.set('');
    try {
      await this.cart.agregar(p.id, v.talla_id, v.color_id, v.sucursal_id, 1);
      this.avisoCarrito.set('¡Agregado a tu carrito!');
    } catch (err) {
      this.avisoCarrito.set(mensajeError(err, 'No se pudo agregar al carrito.'));
    } finally {
      this.agregando.set(false);
    }
  }

  // --------------------------------------------------------------- vendedor

  protected async alternarMic(): Promise<void> {
    const activo = !this.micActivo();
    await this.room?.localParticipant.setMicrophoneEnabled(activo);
    this.micActivo.set(activo);
  }

  protected async alternarCam(): Promise<void> {
    const activa = !this.camActiva();
    await this.room?.localParticipant.setCameraEnabled(activa);
    this.camActiva.set(activa);
    if (activa) {
      const camara = this.room?.localParticipant.getTrackPublication(Track.Source.Camera)?.track as LocalVideoTrack | undefined;
      const video = this.video()?.nativeElement;
      if (camara && video) camara.attach(video);
    }
  }

  protected async terminar(): Promise<void> {
    if (!confirm('¿Terminar el live? Se cierra para todos y queda la grabación.')) return;
    this.terminando.set(true);
    try {
      await this.api.finalizar(this.liveId());
      this.fin.set('Terminaste el live. La grabación aparecerá en el historial en unos minutos.');
      await this.room?.disconnect();
      this.terminado.emit();
    } catch (err) {
      this.error.set(mensajeError(err, 'No se pudo terminar el live.'));
    } finally {
      this.terminando.set(false);
    }
  }

  protected async fijar(p: ProductoLive | null): Promise<void> {
    try {
      this.productos.set(await this.api.fijar(this.liveId(), p?.id ?? null));
    } catch (err) {
      this.error.set(mensajeError(err, 'No se pudo fijar la prenda.'));
    }
  }

  protected async ocultar(c: ComentarioLive): Promise<void> {
    try {
      await this.api.ocultar(this.liveId(), c.id);
      this.comentarios.update((cs) => cs.map((x) => (x.id === c.id ? { ...x, oculto: true } : x)));
    } catch (err) {
      this.error.set(mensajeError(err, 'No se pudo ocultar el comentario.'));
    }
  }

  protected async bloquear(usuarioId: number, nombre: string, tipo: 'silenciado' | 'expulsado'): Promise<void> {
    const texto = tipo === 'expulsado' ? `¿Sacar a ${nombre} del live? No podrá volver a entrar.` : `¿Silenciar a ${nombre}? No podrá comentar.`;
    if (!confirm(texto)) return;
    try {
      this.espectadores.set(await this.api.bloquear(this.liveId(), usuarioId, tipo));
    } catch (err) {
      this.error.set(mensajeError(err, 'No se pudo aplicar.'));
    }
  }

  protected async desbloquear(usuarioId: number): Promise<void> {
    try {
      this.espectadores.set(await this.api.desbloquear(this.liveId(), usuarioId));
    } catch (err) {
      this.error.set(mensajeError(err, 'No se pudo quitar el bloqueo.'));
    }
  }
}
