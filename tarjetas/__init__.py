"""Paquete de lógica de negocio de la Automatización Tarjetas Banco.

| Módulo | Responsabilidad |
|---|---|
| `pdf_reader` | Leer el extracto: operaciones y «Total operaciones» |
| `cards` | Resolver tarjeta del PDF → base de datos y registro de `XB` |
| `mapping` | Convertir una operación del PDF en campos de la tabla `YB` |
| `reconciler` | Comparar con Ninox y clasificar: nuevo / coincidencia / incidencia |
| `executor` | Dar de alta en Ninox con verificación por relectura |
"""
