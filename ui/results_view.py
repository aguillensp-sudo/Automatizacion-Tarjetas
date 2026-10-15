"""Presentación de resultados y toma de decisiones (§6 del requisito).

* **Cada tabla tiene su espacio**: una sección por pareja extracto + tarjeta, con
  el fichero, la máscara de la tarjeta, la base de datos y la tabla de Ninox
  contra la que se va a escribir.
* Los registros **nuevos** (caso a) se cuentan y se listan: no requieren decisión.
* Los casos b) **coincidencia** y c) **incidencia** se muestran con los datos
  separados —lo que dice el PDF a un lado, lo que hay en Ninox al otro— y con un
  radio button a cada lado: **Insertar** o **Desestimar**. Ninguno viene marcado
  por defecto: el requisito obliga a decidir uno u otro.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from tarjetas.executor import DECISION_DESESTIMAR, DECISION_INSERTAR
from tarjetas.pdf_reader import formato_es
from tarjetas.reconciler import Conciliacion, Estado

COLOR_COINCIDENCIA = "#1b7f3b"
COLOR_INCIDENCIA = "#b35c00"
COLOR_NUEVO = "#1f4e79"
COLOR_AVISO = "#b00020"
COLOR_SECCION = "#eef3f8"


class VistaResultados(ttk.Frame):
    """Área desplazable con una sección por extracto."""

    def __init__(self, master: tk.Misc,
                 al_cambiar_decision: Callable[[], None] | None = None) -> None:
        super().__init__(master)
        self._al_cambiar = al_cambiar_decision
        self._variables: dict[tuple[str, int], tk.StringVar] = {}
        self._conciliaciones: list[Conciliacion] = []
        self._secciones: list[tuple[str, list[tk.StringVar]]] = []

        self._lienzo = tk.Canvas(self, highlightthickness=0)
        barra = ttk.Scrollbar(self, orient="vertical", command=self._lienzo.yview)
        self._lienzo.configure(yscrollcommand=barra.set)
        barra.pack(side="right", fill="y")
        self._lienzo.pack(side="left", fill="both", expand=True)

        self._interior = ttk.Frame(self._lienzo)
        self._ventana = self._lienzo.create_window((0, 0), window=self._interior, anchor="nw")
        self._interior.bind(
            "<Configure>",
            lambda _e: self._lienzo.configure(scrollregion=self._lienzo.bbox("all")))
        self._lienzo.bind(
            "<Configure>",
            lambda e: self._lienzo.itemconfigure(self._ventana, width=e.width))
        for widget in (self._lienzo, self._interior):
            widget.bind("<MouseWheel>", self._rueda)

        self._vacio = ttk.Label(
            self._interior,
            text="Todavía no hay resultados.\nPulsa «Procesar» para leer los extractos "
                 "de la carpeta de trabajo.",
            justify="center", padding=40)
        self._vacio.pack()

    # ──────────────────────────────────────────────────────────────────────────
    def _rueda(self, evento: tk.Event) -> None:  # pragma: no cover - sólo interfaz
        self._lienzo.yview_scroll(int(-1 * (evento.delta / 120)), "units")

    def limpiar(self) -> None:
        for hijo in self._interior.winfo_children():
            hijo.destroy()
        self._variables.clear()
        self._secciones.clear()
        self._conciliaciones = []

    def mostrar(self, conciliaciones: list[Conciliacion]) -> None:
        """Reconstruye la vista con las conciliaciones indicadas."""
        self.limpiar()
        self._conciliaciones = list(conciliaciones)
        if not conciliaciones:
            self._vacio = ttk.Label(self._interior, text="No hay resultados.",
                                    justify="center", padding=40)
            self._vacio.pack()
            self._notificar()
            return
        for indice, conciliacion in enumerate(conciliaciones, start=1):
            self._seccion(indice, conciliacion)
        self._lienzo.yview_moveto(0)
        self._notificar()

    # ──────────────────────────────────────────────────────────────────────────
    def _seccion(self, numero: int, conciliacion: Conciliacion) -> None:
        destino = conciliacion.destino
        marco = ttk.LabelFrame(
            self._interior,
            text=" %d. %s · tarjeta %s · %s " % (
                numero, conciliacion.extracto.nombre, destino.numero_tarjeta_pdf,
                destino.base_nombre),
            padding=10)
        marco.pack(fill="x", expand=True, padx=8, pady=6)

        cabecera = ttk.Label(
            marco,
            text="Se ejecutará sobre: %s · tabla `%s` «%s» · registro `XB` %s · titular %s\n"
                 "Período liquidado: %s · liquidación %s · %s operaciones · "
                 "total del banco %s €" % (
                     destino.base_nombre, destino.tabla, destino.tabla_nombre,
                     destino.xb_id, destino.titular,
                     conciliacion.extracto.periodo_texto,
                     conciliacion.extracto.fecha_liquidacion.isoformat(),
                     len(conciliacion.extracto.operaciones),
                     formato_es(conciliacion.extracto.total_operaciones)),
            justify="left", background=COLOR_SECCION, padding=6)
        cabecera.pack(fill="x")

        # ── Caso a): registros que no existen en Ninox ───────────────────────
        nuevas = conciliacion.nuevas
        ttk.Label(
            marco,
            text="a) Registros que NO existen en Ninox: %d %s" % (
                len(nuevas), "(se insertarán sin necesidad de decisión)"
                if nuevas else "(ninguno)"),
            foreground=COLOR_NUEVO, font=("Segoe UI", 9, "bold")).pack(
                anchor="w", pady=(8, 2))
        if nuevas:
            tabla = ttk.Treeview(marco, columns=("fecha", "importe", "concepto"),
                                 show="headings", height=min(len(nuevas), 6))
            for columna, titulo, ancho in (("fecha", "Fecha", 90),
                                           ("importe", "Importe", 90),
                                           ("concepto", "Concepto del extracto", 420)):
                tabla.heading(columna, text=titulo)
                tabla.column(columna, width=ancho, anchor="w")
            for fila in nuevas:
                tabla.insert("", "end", values=(
                    fila.operacion.fecha.isoformat(),
                    formato_es(fila.operacion.importe),
                    fila.operacion.concepto))
            tabla.pack(fill="x")

        # ── Casos b) y c): requieren decisión ────────────────────────────────
        decisiones = conciliacion.decisiones
        ttk.Label(
            marco,
            text="b) Coincidencias y c) incidencias: %d %s" % (
                len(decisiones), "(hay que decidir en todas)" if decisiones else "(ninguna)"),
            foreground=COLOR_INCIDENCIA if conciliacion.incidencias else COLOR_COINCIDENCIA,
            font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(10, 2))

        if decisiones:
            botones = ttk.Frame(marco)
            botones.pack(anchor="w", pady=(0, 4))
            ttk.Label(botones, text="Marcar todas como:").pack(side="left")
            ttk.Button(botones, text="Insertar",
                       command=lambda: self._marcar_seccion(conciliacion, DECISION_INSERTAR)
                       ).pack(side="left", padx=4)
            ttk.Button(botones, text="Desestimar",
                       command=lambda: self._marcar_seccion(conciliacion, DECISION_DESESTIMAR)
                       ).pack(side="left")
            ttk.Button(botones, text="Desmarcar",
                       command=lambda: self._marcar_seccion(conciliacion, "")
                       ).pack(side="left", padx=4)

            rejilla = ttk.Frame(marco)
            rejilla.pack(fill="x")
            for columna, texto in enumerate(
                    ("Decisión", "Datos del extracto (PDF)", "Estado",
                     "Datos existentes en Ninox", "Decisión")):
                ttk.Label(rejilla, text=texto, font=("Segoe UI", 8, "bold")).grid(
                    row=0, column=columna, sticky="w", padx=4)

            variables: list[tk.StringVar] = []
            for indice, fila in enumerate(decisiones, start=1):
                var = tk.StringVar(value="")
                self._variables[(conciliacion.extracto.nombre, fila.operacion.orden)] = var
                variables.append(var)
                var.trace_add("write", lambda *_a: self._notificar())

                color = (COLOR_COINCIDENCIA if fila.estado is Estado.COINCIDENCIA
                         else COLOR_INCIDENCIA)
                ttk.Radiobutton(rejilla, text="Insertar", value=DECISION_INSERTAR,
                                variable=var).grid(row=indice, column=0, sticky="w", padx=4)
                ttk.Label(
                    rejilla,
                    text="%s · %s €\n%s%s" % (
                        fila.operacion.fecha.isoformat(),
                        formato_es(fila.operacion.importe),
                        fila.operacion.concepto,
                        ("\n" + fila.operacion.poblacion) if fila.operacion.poblacion else ""),
                    justify="left").grid(row=indice, column=1, sticky="w", padx=4, pady=2)
                ttk.Label(rejilla, text=fila.estado.etiqueta, foreground=color,
                          justify="left", wraplength=170).grid(
                    row=indice, column=2, sticky="w", padx=4)
                ttk.Label(
                    rejilla,
                    text=(fila.ninox.descripcion() if fila.ninox else "(sin registro)"),
                    justify="left", wraplength=260).grid(
                    row=indice, column=3, sticky="w", padx=4)
                ttk.Radiobutton(rejilla, text="Desestimar", value=DECISION_DESESTIMAR,
                                variable=var).grid(row=indice, column=4, sticky="w", padx=4)
                ttk.Separator(rejilla, orient="horizontal").grid(
                    row=indice, column=0, columnspan=5, sticky="ew", pady=(4, 0))
            self._secciones.append((conciliacion.extracto.nombre, variables))

        # ── Total operaciones (§7) ───────────────────────────────────────────
        ttk.Label(
            marco,
            text="Total operaciones (§7): se creará 1 registro «Cargo Total Mes»\n"
                 "    Fecha %s · Importe %s € · Tarjeta %s · Tipo «Cargo Total Mes» · "
                 "resto de campos en blanco" % (
                     conciliacion.total_mes_fecha.isoformat(),
                     formato_es(conciliacion.total_mes_importe),
                     destino.numero_tarjeta_pdf),
            justify="left", foreground=COLOR_NUEVO).pack(anchor="w", pady=(10, 0))
        if conciliacion.total_mes_previo is not None:
            ttk.Label(
                marco,
                text="    ⚠ Ya existe un registro idéntico en Ninox: %s. Volver a "
                     "procesar este extracto crearía un duplicado."
                     % conciliacion.total_mes_previo.descripcion(),
                justify="left", foreground=COLOR_AVISO, wraplength=900).pack(
                    anchor="w", pady=(2, 0))

    # ──────────────────────────────────────────────────────────────────────────
    def _marcar_seccion(self, conciliacion: Conciliacion, valor: str) -> None:
        for fila in conciliacion.decisiones:
            var = self._variables.get((conciliacion.extracto.nombre, fila.operacion.orden))
            if var is not None:
                var.set(valor)
        self._notificar()

    # ──────────────────────────────────────────────────────────────────────────
    # Estado de las decisiones
    # ──────────────────────────────────────────────────────────────────────────
    def decisiones(self) -> dict[tuple[str, int], str]:
        """{clave de fila: 'I' o 'D'} con lo marcado por el usuario."""
        return {clave: var.get() for clave, var in self._variables.items() if var.get()}

    def total_decisiones(self) -> int:
        return len(self._variables)

    def pendientes(self) -> list[str]:
        """Descripción de las filas que aún no tienen decisión."""
        faltan: list[str] = []
        for conciliacion in self._conciliaciones:
            for fila in conciliacion.decisiones:
                var = self._variables.get((conciliacion.extracto.nombre,
                                           fila.operacion.orden))
                if var is None or not var.get():
                    faltan.append("%s · %s · %s €" % (
                        conciliacion.extracto.nombre, fila.operacion.fecha.isoformat(),
                        formato_es(fila.operacion.importe)))
        return faltan

    def _notificar(self) -> None:
        if self._al_cambiar:
            self._al_cambiar()
