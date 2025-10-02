#!/usr/bin/env python3
"""
Test de conexión a las bases de datos del sistema de gestión de facturas pendientes.

Este script verifica que todas las conexiones a las bases de datos estén funcionando correctamente.
"""

import sys
import os
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

# Añadir el directorio app al path para importar módulos
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.config.database import (
    facturas_engine,
    clientes_engine, 
    historial_engine,
    gestion_engine,
    FACTURAS_DATABASE_URL,
    CLIENTES_DATABASE_URL,
    HISTORIAL_DATABASE_URL
)
from app.config.settings import (
    get_db_facturas_url,
    get_db_clientes_url,
    get_historial_db_url,
    get_gestion_db_url
)

def test_database_connection(engine, db_name, db_url):
    """
    Prueba la conexión a una base de datos específica.
    
    Args:
        engine: Motor de SQLAlchemy
        db_name: Nombre descriptivo de la base de datos
        db_url: URL de conexión (para mostrar en logs)
    
    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        print(f"\n🔍 Probando conexión a {db_name}...")
        print(f"   URL: {db_url}")
        
        # Intentar conectar y ejecutar una consulta simple
        with engine.connect() as conn:
            # Ejecutar consulta básica según el tipo de BD
            if 'sqlite' in db_url.lower():
                result = conn.execute(text("SELECT 1 as test"))
            else:
                result = conn.execute(text("SELECT 1 as test"))
            
            row = result.fetchone()
            if row and row[0] == 1:
                print(f"   ✅ Conexión exitosa a {db_name}")
                return True, f"Conexión exitosa a {db_name}"
            else:
                print(f"   ❌ Respuesta inesperada de {db_name}")
                return False, f"Respuesta inesperada de {db_name}"
                
    except SQLAlchemyError as e:
        print(f"   ❌ Error de SQLAlchemy en {db_name}: {str(e)}")
        return False, f"Error de SQLAlchemy en {db_name}: {str(e)}"
    except Exception as e:
        print(f"   ❌ Error general en {db_name}: {str(e)}")
        return False, f"Error general en {db_name}: {str(e)}"

def test_database_tables(engine, db_name):
    """
    Prueba si se pueden listar las tablas de una base de datos.
    
    Args:
        engine: Motor de SQLAlchemy
        db_name: Nombre descriptivo de la base de datos
    
    Returns:
        tuple: (success: bool, tables: list)
    """
    try:
        print(f"\n📋 Listando tablas en {db_name}...")
        
        with engine.connect() as conn:
            # Consulta para obtener tablas según el tipo de BD
            if 'sqlite' in str(engine.url).lower():
                query = text("SELECT name FROM sqlite_master WHERE type='table'")
            else:
                query = text("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE'")
            
            result = conn.execute(query)
            tables = [row[0] for row in result.fetchall()]
            
            if tables:
                print(f"   📊 Tablas encontradas ({len(tables)}):")
                for table in tables[:10]:  # Mostrar máximo 10 tablas
                    print(f"      - {table}")
                if len(tables) > 10:
                    print(f"      ... y {len(tables) - 10} más")
            else:
                print(f"   ⚠️  No se encontraron tablas en {db_name}")
            
            return True, tables
            
    except Exception as e:
        print(f"   ❌ Error listando tablas en {db_name}: {str(e)}")
        return False, []

def main():
    """Función principal que ejecuta todos los tests de conexión."""
    print("🚀 Iniciando tests de conexión a bases de datos...")
    print("=" * 60)
    
    # Mostrar configuración actual
    print("\n📋 Configuración actual:")
    print(f"   Facturas: {get_db_facturas_url()}")
    print(f"   Clientes: {get_db_clientes_url()}")
    print(f"   Historial: {get_historial_db_url()}")
    print(f"   Gestión: {get_gestion_db_url()}")
    
    # Lista de bases de datos a probar
    databases = [
        (facturas_engine, "Base de Datos de Facturas", FACTURAS_DATABASE_URL),
        (clientes_engine, "Base de Datos de Clientes", CLIENTES_DATABASE_URL),
        (historial_engine, "Base de Datos de Historial", HISTORIAL_DATABASE_URL),
        (gestion_engine, "Base de Datos de Gestión", CLIENTES_DATABASE_URL),  # Gestión usa la misma BD que clientes
    ]
    
    results = []
    
    # Probar cada base de datos
    for engine, db_name, db_url in databases:
        # Test de conexión básica
        success, message = test_database_connection(engine, db_name, db_url)
        results.append((db_name, success, message))
        
        # Si la conexión fue exitosa, listar tablas
        if success:
            test_database_tables(engine, db_name)
    
    # Resumen de resultados
    print("\n" + "=" * 60)
    print("📊 RESUMEN DE RESULTADOS:")
    print("=" * 60)
    
    successful_connections = 0
    total_connections = len(results)
    
    for db_name, success, message in results:
        status = "✅ EXITOSO" if success else "❌ FALLIDO"
        print(f"{status} - {db_name}")
        if not success:
            print(f"         Error: {message}")
        else:
            successful_connections += 1
    
    print(f"\n🎯 Resultado final: {successful_connections}/{total_connections} conexiones exitosas")
    
    if successful_connections == total_connections:
        print("🎉 ¡Todas las conexiones a las bases de datos están funcionando correctamente!")
        return 0
    else:
        print("⚠️  Algunas conexiones fallaron. Revisa la configuración de las bases de datos.")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
