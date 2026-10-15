"""Ventana principal de la Automatización Tarjetas Banco.

Flujo (§3 del requisito):

1. La aplicación muestra la **carpeta de trabajo** y la **lista de ficheros**
   disponibles. Ambos campos son informativos: nunca se editan desde aquí.
2. Si no hay ficheros, se avisa con un mensaje de error.
3. Si hay ficheros, pregunta si se quieren procesar. Con «No», la aplicación se
   cierra; con «Sí», se leen los extractos.
4. La ventana no se cierra: hay una **barra de estado** y un **historial (log)**
   de lo que va haciendo. Cualquier error se muestra en la barra de estado y
   detiene el proceso.
5. Los resultados se presentan por extracto y tarjeta, con las decisiones
   Insertar/Desestimar (§6) y un botón para ejecutar las inserciones (§8).
"""
from __future__ import annotations

import queue
import threading
import traceback
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
import tkinter as tk

import config
import env_loader
from tarjetas import executor, pipeline, pdf_reader
from ui.results_view import VistaResultados


class VentanaPrincipal(tk.Tk):
    """Ventana única de la aplicación."""

    def __init__(self, preguntar_al_arrancar: bool = True) -> None:
        super().__init__()
        self.title("%s  ·  v%s" % (config.APP_NOMBRE, config.APP_VERSION))
        self.geometry("1180x860")
        self.minsize(1000, 700)

        self._preguntar_al_arrancar = preguntar_al_arrancar
        self._cola: queue.Queue[tuple[str, str]] = queue.Queue()
        self._resultado: pipeline.ProcesoResultado | None = None
        self._callback_tarea = None
        self._ocupado = False
        self._ficheros_log: Path | None = None

        self._crear_widgets()
        self._aplicar_icono()
        config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        self._ficheros_log = config.LOGS_DIR / (
            "tarjetas_%s.log" % datetime.now().strftime("%Y%m%d_%H%M%S"))
        if self._preguntar_al_arrancar:
            self.after(200, self._arrancar)

    # ──────────────────────────────────────────────────────────────────────────
    # Construcción de la interfaz
    # ──────────────────────────────────────────────────────────────────────────
    def _crear_widgets(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=3)
        self.rowconfigure(2, weight=1)

        # ── Carpeta de trabajo (informativa) ─────────────────────────────────
        marco_carpeta = ttk.LabelFrame(self, text=" Carpeta de trabajo ", padding=8)
        marco_carpeta.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
        marco_carpeta.columnconfigure(1, weight=1)
        ttk.Label(marco_carpeta, text="Ruta:").grid(row=0, column=0, sticky="w")
        self._var_carpeta = tk.StringVar(value=str(config.PDFS_DIR))
        campo = ttk.Entry(marco_carpeta, textvariable=self._var_carpeta, state="readonly")
        campo.grid(row=0, column=1, sticky="ew", padx=(6, 8))
        ttk.Button(marco_carpeta, text="Abrir carpeta",
                   command=self._abrir_carpeta).grid(row=0, column=2)
        ttk.Button(marco_carpeta, text="Refrescar lista",
                   command=self._refrescar_ficheros).grid(row=0, column=3, padx=(6, 0))

        # ── Cuaderno: ficheros y resultados ──────────────────────────────────
        self._cuaderno = ttk.Notebook(self)
        self._cuaderno.grid(row=1, column=0, sticky="nsew", padx=10, pady=4)

        pestana_ficheros = ttk.Frame(self._cuaderno, padding=8)
        self._cuaderno.add(pestana_ficheros, text="Ficheros disponibles")
        pestana_ficheros.columnconfigure(0, weight=1)
        pestana_ficheros.rowconfigure(1, weight=1)
        ttk.Label(pestana_ficheros,
                  text="Ficheros PDF encontrados en la carpeta de trabajo "
                       "(el usuario deja aquí los extractos a procesar):"
                  ).grid(row=0, column=0, sticky="w")
        self._lista = ttk.Treeview(pestana_ficheros, columns=("fichero", "tamano"),
                                   show="headings", height=8)
        self._lista.heading("fichero", text="Fichero")
        self._lista.column("fichero", width=520, anchor="w")
        self._lista.heading("tamano", text="Tamaño (KB)")
        self._lista.column("tamano", width=110, anchor="e")
        self._lista.grid(row=1, column=0, sticky="nsew", pady=6)
        barra = ttk.Scrollbar(pestana_ficheros, orient="vertical", command=self._lista.yview)
        self._lista.configure(yscrollcommand=barra.set)
        barra.grid(row=1, column=1, sticky="ns", pady=6)
        botones = ttk.Frame(pestana_ficheros)
        botones.grid(row=2, column=0, columnspan=2, sticky="w")
        self._btn_procesar = ttk.Button(botones, text="Procesar los ficheros",
                                       command=self._procesar)
        self._btn_procesar.pack(side="left")
        ttk.Label(botones, text="   (también se pregunta al arrancar)").pack(side="left")

        pestana_resultados = ttk.Frame(self._cuaderno)
        self._cuaderno.add(pestana_resultados, text="Resultados y decisiones")
        pestana_resultados.columnconfigure(0, weight=1)
        pestana_resultados.rowconfigure(0, weight=1)
        self._resultados = VistaResultados(pestana_resultados,
                                           al_cambiar_decision=self._actualizar_estado)
        self._resultados.grid(row=0, column=0, sticky="nsew")

        # ── Historial ────────────────────────────────────────────────────────
        marco_log = ttk.LabelFrame(self, text=" Historial del proceso ", padding=6)
        marco_log.grid(row=2, column=0, sticky="nsew", padx=10, pady=4)
        marco_log.columnconfigure(0, weight=1)
        marco_log.rowconfigure(0, weight=1)
        self._log_texto = tk.Text(marco_log, height=10, wrap="word",
                                  state="disabled", background="#fbfbfb")
        self._log_texto.grid(row=0, column=0, sticky="nsew")
        barra_log = ttk.Scrollbar(marco_log, orient="vertical",
                                  command=self._log_texto.yview)
        self._log_texto.configure(yscrollcommand=barra_log.set)
        barra_log.grid(row=0, column=1, sticky="ns")

        # ── Barra de estado y acciones ───────────────────────────────────────
        marco_estado = ttk.Frame(self, padding=(10, 0, 10, 10))
        marco_estado.grid(row=3, column=0, sticky="ew")
        marco_estado.columnconfigure(0, weight=1)
        self._var_estado = tk.StringVar(value="Listo.")
        self._etiqueta_estado = ttk.Label(marco_estado, textvariable=self._var_estado,
                                          anchor="w")
        self._etiqueta_estado.grid(row=0, column=0, sticky="ew")
        self._progreso = ttk.Progressbar(marco_estado, mode="determinate", length=260)
        self._progreso.grid(row=0, column=1, padx=8)
        self._btn_ejecutar = ttk.Button(marco_estado, text="Ejecutar las inserciones",
                                        command=self._ejecutar, state="disabled")
        self._btn_ejecutar.grid(row=0, column=2, padx=4)
        ttk.Button(marco_estado, text="Salir", command=self.destroy).grid(row=0, column=3)

        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _aplicar_icono(self) -> None:
        for ruta, metodo in ((config.ICONO_ICO, "iconbitmap"),):
            if ruta.exists():
                try:
                    getattr(self, metodo)(str(ruta))
                except tk.TclError:      # pragma: no cover - sistema sin soporte
                    pass

    # ──────────────────────────────────────────────────────────────────────────
    # Arranque: carpeta, ficheros y pregunta al usuario (§3.3)
    # ──────────────────────────────────────────────────────────────────────────
    def _abrir_carpeta(self) -> None:
        config.PDFS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            import os
            os.startfile(str(config.PDFS_DIR))     # noqa: S606 - abrir el explorador
        except OSError:                            # pragma: no cover
            messagebox.showwarning(config.APP_NOMBRE,
                                   "No se ha podido abrir la carpeta:\n%s"
                                   % config.PDFS_DIR)

    def _refrescar_ficheros(self) -> list[Path]:
        self._lista.delete(*self._lista.get_children())
        try:
            ficheros = pdf_reader.listar_pdfs(config.PDFS_DIR)
        except pdf_reader.ExtractoError as exc:
            self._estado_error(str(exc))
            self._log("✘ %s" % exc)
            return []
        for fichero in ficheros:
            self._lista.insert("", "end", values=(
                fichero.name, "%.0f" % (fichero.stat().st_size / 1024)))
        return ficheros

    def _arrancar(self) -> None:
        self._log("Carpeta de trabajo: %s" % config.PDFS_DIR)
        ficheros = self._refrescar_ficheros()
        if not ficheros:
            mensaje = ("No hay ningún fichero PDF en la carpeta de trabajo:\n%s\n\n"
                       "Deja los extractos en esa carpeta y pulsa «Refrescar lista»."
                       % config.PDFS_DIR)
            self._estado_error("No hay ficheros PDF en la carpeta de trabajo.")
            self._log("✘ " + mensaje.replace("\n", " "))
            messagebox.showerror(config.APP_NOMBRE, mensaje)
            return
        self._log("Se han encontrado %d fichero(s):" % len(ficheros))
        for fichero in ficheros:
            self._log("   · %s" % fichero.name)
        self._var_estado.set("¿Procesar los ficheros encontrados?")
        if messagebox.askyesno(
                config.APP_NOMBRE,
                "Carpeta de trabajo:\n%s\n\nFicheros encontrados (%d):\n%s\n\n"
                "¿Quieres procesarlos?" % (
                    config.PDFS_DIR, len(ficheros),
                    "\n".join("   · " + f.name for f in ficheros))):
            self._procesar()
        else:
            self._log("El usuario ha decidido no procesar los ficheros: se cierra.")
            self.destroy()

    # ──────────────────────────────────────────────────────────────────────────
    # Proceso (§3.4 - §5)
    # ──────────────────────────────────────────────────────────────────────────
    def _procesar(self) -> None:
        if self._ocupado:
            return
        ficheros = [config.PDFS_DIR / self._lista.set(i, "fichero")
                    for i in self._lista.get_children()]
        if not ficheros:
            self._refrescar_ficheros()
            ficheros = [config.PDFS_DIR / self._lista.set(i, "fichero")
                        for i in self._lista.get_children()]
        if not ficheros:
            messagebox.showerror(config.APP_NOMBRE,
                                 "No hay ficheros PDF que procesar en:\n%s"
                                 % config.PDFS_DIR)
            return

        self._resultado = None
        self._resultados.limpiar()
        self._btn_ejecutar.configure(state="disabled")
        self._empezar_trabajo("Leyendo %d extracto(s)…" % len(ficheros))

        def tarea() -> pipeline.ProcesoResultado:
            return pipeline.procesar(ficheros, log=self._log_desde_hilo,
                                     progreso=self._progreso_desde_hilo)

        def terminado(resultado: pipeline.ProcesoResultado) -> None:
            self._resultado = resultado
            self._resultados.mostrar(resultado.conciliaciones)
            self._cuaderno.select(1)
            self._fin_trabajo()
            resumen = ("%d extracto(s) leído(s): %d registros nuevos, %d coincidencias "
                       "e incidencias por decidir, %d totales mensuales."
                       % (len(resultado.conciliaciones), resultado.total_nuevos,
                          resultado.total_decisiones, len(resultado.conciliaciones)))
            self._log("✔ " + resumen)
            self._var_estado.set(resumen + " Revisa las decisiones.")
            messagebox.showinfo(config.APP_NOMBRE, resumen)

        self._lanzar(tarea, terminado, "Lectura de los extractos")

    # ──────────────────────────────────────────────────────────────────────────
    # Ejecución de las inserciones (§8)
    # ──────────────────────────────────────────────────────────────────────────
    def _ejecutar(self) -> None:
        if self._ocupado or self._resultado is None:
            return
        pendientes = self._resultados.pendientes()
        if pendientes:
            detalle = "\n".join("   · " + p for p in pendientes[:12])
            if len(pendientes) > 12:
                detalle += "\n   · … y %d más" % (len(pendientes) - 12)
            messagebox.showwarning(
                config.APP_NOMBRE,
                "No se puede ejecutar todavía: hay que decidir «Insertar» o "
                "«Desestimar» en todos los registros.\n\nFaltan %d:\n%s"
                % (len(pendientes), detalle))
            self._estado_error("Faltan %d decisiones por marcar." % len(pendientes))
            return

        decisiones = self._resultados.decisiones()
        try:
            plan = executor.construir_plan(self._resultado.conciliaciones, decisiones)
        except executor.PlanError as exc:
            messagebox.showerror(config.APP_NOMBRE, str(exc))
            self._estado_error(str(exc))
            return

        if plan.total_inserciones == 0:
            messagebox.showinfo(config.APP_NOMBRE,
                                "No hay ninguna inserción que ejecutar.")
            return

        por_base: dict[str, int] = {}
        for tarea in plan.tareas:
            por_base[tarea.base_clave] = por_base.get(tarea.base_clave, 0) + 1
        detalle_bases = "\n".join(
            "   · %s: %d registro(s)" % (config.BASES[b]["nombre"], n)
            for b, n in sorted(por_base.items()))

        if not messagebox.askyesno(
                config.APP_NOMBRE,
                "Se van a dar de alta %d registro(s) en Ninox:\n%s\n\n"
                "Se desestimarán %d. ¿Continuar?" % (
                    plan.total_inserciones, detalle_bases, plan.total_desestimadas)):
            self._log("Ejecución cancelada por el usuario.")
            return

        self._btn_ejecutar.configure(state="disabled")
        self._empezar_trabajo("Insertando en Ninox…")
        fabrica = pipeline.FabricaClientes()

        def tarea() -> executor.ResultadoEjecucion:
            try:
                return executor.ejecutar_plan(plan, fabrica, log=self._log_desde_hilo,
                                              progreso=self._progreso_desde_hilo)
            finally:
                for cliente in fabrica.todos().values():
                    cliente.invalidar_cache()

        def terminado(resultado: executor.ResultadoEjecucion) -> None:
            self._fin_trabajo()
            if resultado.ok:
                self._var_estado.set(resultado.resumen())
                self._log("✔ " + resultado.resumen())
                for aviso in resultado.avisos:
                    self._log("⚠ " + aviso)
                messagebox.showinfo(
                    config.APP_NOMBRE,
                    "%s\n\nNº total de inserciones: %d" % (
                        resultado.resumen(), resultado.total_creados))
                self._btn_ejecutar.configure(state="disabled")
            else:
                self._estado_error(resultado.resumen())
                self._log("✘ " + resultado.resumen())
                for error in resultado.errores:
                    self._log("   · " + error)
                ids = ", ".join(str(c["id"]) for c in resultado.creados)
                messagebox.showerror(
                    config.APP_NOMBRE,
                    "El proceso no ha podido completarse:\n\n%s\n\n"
                    "Registros creados antes del error: %d%s"
                    % (resultado.errores[0], resultado.total_creados,
                       (" (ids: %s)" % ids) if ids else ""))
                self._btn_ejecutar.configure(state="normal")

        self._lanzar(tarea, terminado, "Inserción en Ninox")

    # ──────────────────────────────────────────────────────────────────────────
    # Ejecución en segundo plano
    #
    # Tkinter no es seguro entre hilos: el hilo de trabajo **sólo** escribe en la
    # cola y el hilo de la interfaz consume esa cola con `after()`. La ventana
    # sigue viva y mostrando el log y la barra de estado mientras se trabaja.
    # ──────────────────────────────────────────────────────────────────────────
    def _lanzar(self, tarea, al_terminar, descripcion: str) -> None:
        self._callback_tarea = al_terminar
        hilo = threading.Thread(target=self._ejecutar_tarea,
                                args=(tarea, descripcion), daemon=True)
        hilo.start()
        self.after(80, self._vaciar_cola)

    def _ejecutar_tarea(self, tarea, descripcion: str) -> None:
        try:
            resultado = tarea()
        except Exception as exc:                       # noqa: BLE001 - se informa al usuario
            self._cola.put(("error", "%s: %s" % (type(exc).__name__, exc)))
            self._cola.put(("detalle", traceback.format_exc()))
            return
        self._cola.put(("ok", resultado))

    def _vaciar_cola(self) -> None:
        while True:
            try:
                tipo, dato = self._cola.get_nowait()
            except queue.Empty:
                break
            if tipo == "log":
                self._log(dato)
            elif tipo == "progreso":
                actual, total = (int(x) for x in str(dato).split("/"))
                self._progreso.configure(maximum=max(total, 1), value=actual)
            elif tipo == "detalle":
                self._log(dato)
            elif tipo == "error":
                self._fin_trabajo()
                self._estado_error(dato)
                self._log("✘ " + dato)
                messagebox.showerror(
                    config.APP_NOMBRE,
                    "El proceso se ha detenido por un error:\n\n%s" % dato)
            elif tipo == "ok":
                callback = getattr(self, "_callback_tarea", None)
                if callback is not None:
                    callback(dato)
        if self._ocupado:
            self.after(120, self._vaciar_cola)

    def _log_desde_hilo(self, mensaje: str) -> None:
        self._cola.put(("log", mensaje))

    def _progreso_desde_hilo(self, actual: int, total: int) -> None:
        self._cola.put(("progreso", "%d/%d" % (actual, total)))

    def _empezar_trabajo(self, estado: str) -> None:
        self._ocupado = True
        self._var_estado.set(estado)
        self._etiqueta_estado.configure(foreground="#000000")
        self._progreso.configure(value=0)
        self._btn_procesar.configure(state="disabled")
        self._log("── %s ──" % estado)

    def _fin_trabajo(self) -> None:
        self._ocupado = False
        self._btn_procesar.configure(state="normal")
        self._progreso.configure(value=self._progreso.cget("maximum"))

    def _estado_error(self, mensaje: str) -> None:
        self._var_estado.set(mensaje)
        self._etiqueta_estado.configure(foreground="#b00020")

    def _actualizar_estado(self) -> None:
        """Se llama al marcar o desmarcar cualquier decisión."""
        if self._resultado is None:
            return
        pendientes = self._resultados.pendientes()
        total = self._resultados.total_decisiones()
        if pendientes:
            self._var_estado.set("Decisiones pendientes: %d de %d."
                                 % (len(pendientes), total))
        elif total:
            self._var_estado.set("Todas las decisiones tomadas (%d). Ya se puede ejecutar."
                                 % total)
            self._etiqueta_estado.configure(foreground="#1b7f3b")
        self._btn_ejecutar.configure(
            state="disabled" if (self._ocupado or self._resultado is None) else "normal")

    # ──────────────────────────────────────────────────────────────────────────
    # Historial
    # ──────────────────────────────────────────────────────────────────────────
    def _log(self, mensaje: str) -> None:
        marca = datetime.now().strftime("%H:%M:%S")
        linea = "[%s] %s" % (marca, mensaje)
        self._log_texto.configure(state="normal")
        self._log_texto.insert("end", linea + "\n")
        self._log_texto.see("end")
        self._log_texto.configure(state="disabled")
        if self._ficheros_log is not None:
            try:
                with open(self._ficheros_log, "a", encoding="utf-8") as fichero:
                    fichero.write(linea + "\n")
            except OSError:                       # pragma: no cover - disco lleno
                pass


def arrancar() -> None:
    """Punto de entrada de la interfaz gráfica."""
    try:
        env_loader.api_key()
    except env_loader.CredencialError as exc:
        raiz = tk.Tk()
        raiz.withdraw()
        messagebox.showerror(config.APP_NOMBRE, str(exc))
        raiz.destroy()
        return
    ventana = VentanaPrincipal()
    ventana.mainloop()
