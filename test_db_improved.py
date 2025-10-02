#!/usr/bin/env python3
"""
Test mejorado de conexión a las bases de datos con manejo de errores.
"""

import sys
import os
from sqlalchemy import text

# Añadir el directorio app al path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

def test_imports():
    """Verifica que se puedan importar todos los módulos necesarios."""
    print("🔍 Verificando imports...")
    
    try:
        from app.config.database import facturas_engine, clientes_engine, historial_engine
        from app.config.settings import get_db_facturas_url, get_db_clientes_url, get_historial_db_url
        print("   ✅ Imports exitosos")
        return True
    except ImportError as e:
        print(f"   ❌ Error de import: {e}")
        return False

def test_database_connection(engine, db_name, db_url):
    """Prueba la conexión a una base de datos específica."""
    print(f"\n🔍 Probando {db_name}...")
    print(f"   URL: {db_url[:50]}..." if len(db_url) > 50 else f"   URL: {db_url}")
    
    try:
        with engine.connect() as conn:
            # Usar text() para consultas SQL
            result = conn.execute(text("SELECT 1 as test"))
            row = result.fetchone()
            if row and row[0] == 1:
                print(f"   ✅ Conexión exitosa a {db_name}")
                return True
            else:
                print(f"   ❌ Respuesta inesperada de {db_name}")
                return False
    except Exception as e:
        print(f"   ❌ Error en {db_name}: {str(e)[:100]}...")
        return False

def test_sqlite_connection():
    """Prueba específica para SQLite (base de datos local)."""
    print("\n🔍 Probando SQLite local...")
    
    try:
        import sqlite3
        # Probar conexión directa a SQLite
        conn = sqlite3.connect('./facturas_historial.db')
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        conn.close()
        
        if result and result[0] == 1:
            print("   ✅ SQLite funciona correctamente")
            return True
        else:
            print("   ❌ SQLite no responde correctamente")
            return False
    except Exception as e:
        print(f"   ❌ Error con SQLite: {e}")
        return False

def check_dependencies():
    """Verifica las dependencias necesarias."""
    print("\n🔍 Verificando dependencias...")
    
    dependencies = [
        ('sqlalchemy', 'SQLAlchemy'),
        ('pyodbc', 'pyodbc (para SQL Server)'),
        ('sqlite3', 'sqlite3 (incluido en Python)'),
    ]
    
    all_ok = True
    for module, name in dependencies:
        try:
            __import__(module)
            print(f"   ✅ {name} - Disponible")
        except ImportError:
            print(f"   ❌ {name} - NO DISPONIBLE")
            all_ok = False
    
    return all_ok

def main():
    """Función principal."""
    print("🚀 Test de conexión a bases de datos - Versión mejorada")
    print("=" * 60)
    
    # 1. Verificar dependencias
    deps_ok = check_dependencies()
    
    # 2. Verificar imports
    imports_ok = test_imports()
    
    if not imports_ok:
        print("\n❌ No se pueden importar los módulos. Revisa la estructura del proyecto.")
        return 1
    
    # 3. Probar SQLite local
    sqlite_ok = test_sqlite_connection()
    
    # 4. Probar conexiones configuradas
    if deps_ok and imports_ok:
        try:
            from app.config.database import facturas_engine, clientes_engine, historial_engine
            from app.config.settings import get_db_facturas_url, get_db_clientes_url, get_historial_db_url
            
            databases = [
                (facturas_engine, "Base de Datos de Facturas", get_db_facturas_url()),
                (clientes_engine, "Base de Datos de Clientes", get_db_clientes_url()),
                (historial_engine, "Base de Datos de Historial", get_historial_db_url()),
            ]
            
            successful_connections = 0
            total_connections = len(databases)
            
            for engine, db_name, db_url in databases:
                if test_database_connection(engine, db_name, db_url):
                    successful_connections += 1
            
            print(f"\n📊 Resultado: {successful_connections}/{total_connections} conexiones exitosas")
            
            if successful_connections == 0:
                print("\n⚠️  No se pudo conectar a ninguna base de datos.")
                print("   Posibles causas:")
                print("   - El servidor SQL Server no está disponible")
                print("   - Falta el driver ODBC para SQL Server")
                print("   - Credenciales incorrectas")
                print("   - Problemas de red")
            elif successful_connections < total_connections:
                print("\n⚠️  Algunas conexiones fallaron. Revisa la configuración.")
            else:
                print("\n🎉 ¡Todas las conexiones están funcionando!")
                
        except Exception as e:
            print(f"\n❌ Error durante las pruebas: {e}")
            return 1
    else:
        print("\n⚠️  Faltan dependencias necesarias. Instala los paquetes requeridos.")
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
