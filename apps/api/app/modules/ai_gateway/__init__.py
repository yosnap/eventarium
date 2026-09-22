"""Pasarela de IA multi-proveedor.

Fase 1 del plan `260911-0325-prd-pasarela-ia-multiproveedor`: modelo de datos
de dos niveles (plataforma y organización), cifrado en reposo de las claves,
gates de cada nivel y endpoints de lectura/escritura. **Todavía no hay
ningún consumidor**: nada de este módulo llama a un proveedor de IA (eso es
la fase 2, `client.py`).
"""
