"""Pruebas de la interfaz: la ventana se construye y las decisiones se registran.

No se abre ninguna ventana visible: se construye el objeto, se le piden las
actualizaciones pendientes (`update`) y se destruye. Requiere que Tkinter pueda
crear una ventana, que es lo normal en el escritorio del usuario.
"""
from __future__ import annotations

import pytest

tkinter = pytest.importorskip("tkinter")

import config
from tarjetas import executor
from tarjetas.cards import Destino
from tarjetas.pdf_reader import leer_extracto
from tarjetas.reconciler import conciliar
from tests.sintetico import crear_pdf
from tests.test_conciliacion import ClienteFalso, FabricaFalsa, _registro


@pytest.fixture(scope="module")
def ventana():
    """Una única ventana para todo el módulo.

    Crear y destruir varios intérpretes de Tk en el mismo proceso es inestable en
    Windows (a veces falla al releer ``tk.tcl``), así que la ventana se comparte y
    cada prueba rehace el contenido con ``mostrar()``.
    """
    from ui.app import VentanaPrincipal
    try:
        raiz = VentanaPrincipal(preguntar_al_arrancar=False)
    except tkinter.TclError as exc:            # pragma: no cover - sin pantalla
        pytest.skip("Sin entorno gráfico: %s" % exc)
    raiz.update()
    yield raiz
    try:
        raiz.destroy()
    except tkinter.TclError:                   # pragma: no cover
        pass


def _conciliacion(tmp_path):
    extracto = leer_extracto(crear_pdf(tmp_path / "extracto.pdf"))
    definicion = config.TARJETAS["5566 **** **** 5013"]
    base = config.BASES[str(definicion["base"])]
    destino = Destino(
        base_clave=str(definicion["base"]), base_id=base["id"],
        base_nombre=base["nombre"], tabla=base["tabla_yb"],
        tabla_nombre=base["tabla_yb_nombre"], xb_id=int(definicion["xb_id"]),
        titular=str(definicion["titular"]),
        numero_tarjeta_pdf="5566 **** **** 5013", etiqueta_tarjeta="prueba")
    cliente = ClienteFalso(base["nombre"], [
        _registro(1, "2026-09-01", 81.78),
        _registro(2, "2026-09-17", 170.00),
    ])
    return conciliar(extracto, destino, cliente)


def test_la_ventana_muestra_los_ficheros_de_la_carpeta(ventana):
    ficheros = ventana._refrescar_ficheros()
    assert len(ventana._lista.get_children()) == len(ficheros)
    # El campo de carpeta es informativo y no editable
    assert str(ventana._var_carpeta.get()) == str(config.PDFS_DIR)


def test_las_decisiones_empiezan_sin_marcar_y_bloquean_la_ejecucion(ventana, tmp_path):
    conciliacion = _conciliacion(tmp_path)
    ventana._resultado = type("R", (), {"conciliaciones": [conciliacion]})()
    ventana._resultados.mostrar([conciliacion])
    ventana.update()

    # 1 coincidencia + 1 incidencia deben decidirse; hay además 2 registros nuevos
    assert len(conciliacion.nuevas) == 2
    assert ventana._resultados.total_decisiones() == 2
    assert len(ventana._resultados.pendientes()) == 2
    assert ventana._resultados.decisiones() == {}

    # Al marcar todas, desaparecen las pendientes y el plan se puede construir
    ventana._resultados._marcar_seccion(conciliacion, executor.DECISION_DESESTIMAR)
    ventana.update()
    assert ventana._resultados.pendientes() == []
    plan = executor.construir_plan([conciliacion], ventana._resultados.decisiones())
    assert plan.total_desestimadas == 2
    assert plan.total_inserciones == 3          # 2 nuevos + el total mensual


def test_avisar_de_decisiones_pendientes_no_ejecuta(ventana, tmp_path, monkeypatch):
    conciliacion = _conciliacion(tmp_path)
    ventana._resultado = type("R", (), {"conciliaciones": [conciliacion]})()
    ventana._resultados.mostrar([conciliacion])
    ventana.update()

    avisos: list[tuple] = []
    monkeypatch.setattr("ui.app.messagebox.showwarning",
                        lambda *a, **k: avisos.append(a))
    ventana._ejecutar()
    assert avisos, "debe avisar de que faltan decisiones"
    assert "Faltan 2" in ventana._var_estado.get()


def test_el_estado_refleja_las_decisiones_tomadas(ventana, tmp_path):
    conciliacion = _conciliacion(tmp_path)
    ventana._resultado = type("R", (), {"conciliaciones": [conciliacion]})()
    ventana._resultados.mostrar([conciliacion])
    ventana.update()
    variable = next(iter(ventana._resultados._variables.values()))
    variable.set(executor.DECISION_INSERTAR)
    ventana.update()
    assert ventana._var_estado.get() == "Decisiones pendientes: 1 de 2."
    for otra in ventana._resultados._variables.values():
        otra.set(executor.DECISION_INSERTAR)
    ventana.update()
    assert "Todas las decisiones tomadas (2)" in ventana._var_estado.get()


def test_ejecucion_completa_desde_la_ventana(ventana, tmp_path, monkeypatch):
    """El camino completo de §8: decidir, ejecutar en segundo plano y avisar.

    Se sustituye la fábrica de clientes por una falsa: la ventana hace todo lo
    demás (validar decisiones, construir el plan, lanzar el hilo, consumir la cola
    y mostrar el resultado final) sin tocar Ninox.
    """
    import time

    conciliacion = _conciliacion(tmp_path)
    ventana._resultado = type("R", (), {"conciliaciones": [conciliacion]})()
    ventana._resultados.mostrar([conciliacion])
    ventana._resultados._marcar_seccion(conciliacion, executor.DECISION_DESESTIMAR)
    ventana.update()

    cliente = ClienteFalso("FAWALT INVESTMENT")
    monkeypatch.setattr("tarjetas.pipeline.FabricaClientes",
                        lambda *a, **k: FabricaFalsa(cliente))
    preguntas: list[tuple] = []
    informes: list[tuple] = []
    monkeypatch.setattr("ui.app.messagebox.askyesno", lambda *a, **k: preguntas.append(a) or True)
    monkeypatch.setattr("ui.app.messagebox.showinfo", lambda *a, **k: informes.append(a))
    monkeypatch.setattr("ui.app.messagebox.showerror", lambda *a, **k: informes.append(a))

    ventana._ejecutar()
    limite = time.time() + 20
    while ventana._ocupado and time.time() < limite:
        ventana.update()
        time.sleep(0.05)

    assert preguntas, "debe pedir confirmación antes de escribir en producción"
    assert not ventana._ocupado
    # 2 nuevos + 1 total mensual (las 2 decisiones se han desestimado)
    assert len(cliente.creados) == 3
    assert informes and "inserciones" in str(informes[-1])
    assert "Proceso completado: 3" in ventana._var_estado.get()
    tipos = [c["fields"][config.CAMPO_YB_TIPO] for c in cliente.creados]
    assert tipos.count("Cargo puntual") == 2
    assert tipos.count("Cargo Total Mes") == 1
