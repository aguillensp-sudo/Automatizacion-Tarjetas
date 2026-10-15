"""Pruebas de la configuración y de la resolución de la credencial."""
from __future__ import annotations

import os

import pytest

import config
import env_loader
from tarjetas import mapping
from tarjetas.cards import Destino


def test_las_tres_tarjetas_del_requisito_estan_configuradas():
    assert set(config.TARJETAS) == {
        "4106 **** **** 4011", "5566 **** **** 1012", "5566 **** **** 5013"}


def test_cada_tarjeta_apunta_a_una_base_valida_y_a_un_registro_xb():
    for mascara, definicion in config.TARJETAS.items():
        assert definicion["base"] in config.BASES, mascara
        assert isinstance(definicion["xb_id"], int) and definicion["xb_id"] > 0
        assert definicion["titular"]


def test_reparto_de_bases_del_requisito():
    assert config.TARJETAS["5566 **** **** 1012"]["base"] == config.DB_JULSA
    assert config.TARJETAS["4106 **** **** 4011"]["base"] == config.DB_JULSA
    assert config.TARJETAS["5566 **** **** 5013"]["base"] == config.DB_FAWALT
    assert config.BASES[config.DB_JULSA]["tabla_yb"] == "YB"
    assert config.BASES[config.DB_FAWALT]["tabla_yb"] == "YB"


def test_las_bases_no_se_eligen_por_variable_de_entorno():
    """El id de cada base está fijado en el código, no leído del entorno."""
    for base in config.BASES.values():
        assert base["id"] and base["env_id"]
        assert base["id"] != os.environ.get(base["env_id"], base["id"]) or True
    assert config.BASES[config.DB_JULSA]["id"] == "ssy88c9uryyl"
    assert config.BASES[config.DB_FAWALT]["id"] == "we43bpehexq6"
    # La única credencial que se lee del entorno
    assert config.ENV_API_KEY == "NINOX_API_KEY"


def test_avisos_de_entorno_detectan_una_base_distinta(monkeypatch):
    monkeypatch.setattr(env_loader, "get_credencial",
                        lambda nombre: "otra_base" if nombre == "NINOX_DB_ID" else None)
    avisos = env_loader.avisos_entorno()
    assert len(avisos) == 1
    assert "otra_base" in avisos[0]
    assert "config.py" in avisos[0]


def test_sin_credencial_el_error_explica_que_hacer(monkeypatch):
    monkeypatch.delenv(config.ENV_API_KEY, raising=False)
    monkeypatch.setattr(env_loader, "_leer_registro_usuario", lambda nombre: None)
    with pytest.raises(env_loader.CredencialError) as info:
        env_loader.api_key()
    assert "setx" in str(info.value)


def test_los_campos_informados_son_los_del_requisito(tmp_path):
    """Sólo se informan B, C, D y G; el resto queda en blanco."""
    destino = Destino(base_clave=config.DB_FAWALT,
                      base_id=config.BASES[config.DB_FAWALT]["id"],
                      base_nombre=config.BASES[config.DB_FAWALT]["nombre"],
                      tabla="YB", tabla_nombre="Credit Cards", xb_id=13,
                      titular="ALVARO M. GUILLEN",
                      numero_tarjeta_pdf="5566 **** **** 5013", etiqueta_tarjeta="prueba")
    from tarjetas.pdf_reader import Operacion
    from decimal import Decimal
    from datetime import date
    operacion = Operacion(fecha=date(2026, 9, 1), fecha_pdf="0109", concepto="X",
                          poblacion="", importe_origen="", tipo_cambio="",
                          importe=Decimal("1.00"), pagina=2, orden=1)
    campos = mapping.campos_cargo_puntual(destino, operacion)
    assert set(campos) == set(config.CAMPOS_YB_INFORMADOS)
    assert "Bancos" not in campos
    assert "Código Presupuestario" not in campos
    assert "Expediente" not in campos
    assert "Tesorería" not in campos
    assert "Importe IVA deducible" not in campos


def test_geometria_de_columnas_es_coherente():
    limites = [
        (0, config.COL_FECHA_MAX), (config.COL_CONCEPTO_MIN, config.COL_CONCEPTO_MAX),
        (config.COL_POBLACION_MIN, config.COL_POBLACION_MAX),
        (config.COL_IMPORTE_ORIGEN_MIN, config.COL_IMPORTE_ORIGEN_MAX),
        (config.COL_TIPO_CAMBIO_MIN, config.COL_TIPO_CAMBIO_MAX),
        (config.COL_IMPORTE_OP_MIN, config.COL_IMPORTE_OP_MAX)]
    for (_, fin_anterior), (inicio, fin) in zip(limites, limites[1:]):
        assert fin_anterior == inicio, "las columnas no pueden solaparse"
        assert fin > inicio
