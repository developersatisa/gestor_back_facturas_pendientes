"""
Constantes del dominio de la aplicación.
"""
from typing import Dict

# Códigos de sociedades permitidas
SOCIEDADES_PERMITIDAS = ['S005', 'S001', 'S010']

# Nombres de sociedades
SOCIEDADES_NAMES: Dict[str, str] = {
    'S005': 'Grupo Atisa BPO',
    'S001': 'Asesores Titulados',
    'S010': 'Selier by Atisa'
}

# Colectivos permitidos para facturas
COLECTIVOS_PERMITIDOS = ['4300', '4302']

# Tipos de factura excluidos
TIPOS_FACTURA_EXCLUIDOS = ['AA', 'ZZ']

# Estados de consultores
ESTADO_CONSULTOR_ACTIVO = 'activo'
ESTADO_CONSULTOR_INACTIVO = 'inactivo'

# Tipos de acciones
ACCION_TIPO_EMAIL = 'Email'
ACCION_TIPO_LLAMADA = 'Llamada'
ACCION_TIPO_TEAMS = 'Teams'

# Valores por defecto
DEFAULT_PAGINATION_LIMIT = 50
DEFAULT_LIST_LIMIT = 200
