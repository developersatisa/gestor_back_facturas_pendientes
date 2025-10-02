#!/usr/bin/env python3
"""
Test simple de conexión a las bases de datos.
"""

import sys
import os
from sqlalchemy import text

# Añadir el directorio app al path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

try:
    from app.config.database import facturas_engine, clientes_engine, historial_engine
    from app.config.settings import get_db_facturas_url, get_db_clientes_url, get_historial_db_url
    
    print("🔍 Probando conexiones a las bases de datos...")
    print("=" * 50)
    
    # Test 1: Base de datos de facturas
    print("\n1. Base de datos de facturas:")
    print(f"   URL: {get_db_facturas_url()}")
    try:
        with facturas_engine.connect() as conn:
            result = conn.execute(text("SELECT 1 as test"))
            print("   ✅ Conexión exitosa")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 2: Base de datos de clientes
    print("\n2. Base de datos de clientes:")
    print(f"   URL: {get_db_clientes_url()}")
    try:
        with clientes_engine.connect() as conn:
            result = conn.execute(text("SELECT 1 as test"))
            print("   ✅ Conexión exitosa")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 3: Base de datos de historial
    print("\n3. Base de datos de historial:")
    print(f"   URL: {get_historial_db_url()}")
    try:
        with historial_engine.connect() as conn:
            result = conn.execute(text("SELECT 1 as test"))
            print("   ✅ Conexión exitosa")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    print("\n🎉 Test completado!")
    
except ImportError as e:
    print(f"❌ Error importando módulos: {e}")
    print("Asegúrate de estar en el directorio correcto y tener las dependencias instaladas.")
except Exception as e:
    print(f"❌ Error inesperado: {e}")
