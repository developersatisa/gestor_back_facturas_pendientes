#!/bin/bash

# Script de instalación del servicio Gestor de Facturas Pendientes
# Ejecutar como root o con sudo

set -e

echo "🚀 Instalando servicio Gestor de Facturas Pendientes..."

# Variables
SERVICE_NAME="gestor-facturas"
SERVICE_FILE="gestor-facturas.service"
APP_DIR="/var/www/gestor_facturas_pendientes"
SERVICE_DIR="/etc/systemd/system"

# Verificar que se ejecuta como root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Este script debe ejecutarse como root o con sudo"
    exit 1
fi

# Crear directorio de la aplicación
echo "📁 Creando directorio de la aplicación..."
mkdir -p $APP_DIR

# Copiar archivos de la aplicación
echo "📋 Copiando archivos de la aplicación..."
cp -r . $APP_DIR/

# Crear entorno virtual
echo "🐍 Creando entorno virtual..."
cd $APP_DIR
python3 -m venv venv
source venv/bin/activate

# Instalar dependencias
echo "📦 Instalando dependencias..."
pip install --upgrade pip
pip install -r requirements.txt

# Configurar permisos
echo "🔐 Configurando permisos..."
chown -R www-data:www-data $APP_DIR
chmod -R 755 $APP_DIR

# Copiar archivo de servicio
echo "⚙️ Instalando archivo de servicio..."
cp $SERVICE_FILE $SERVICE_DIR/

# Recargar systemd
echo "🔄 Recargando systemd..."
systemctl daemon-reload

# Habilitar servicio
echo "✅ Habilitando servicio..."
systemctl enable $SERVICE_NAME

# Iniciar servicio
echo "🚀 Iniciando servicio..."
systemctl start $SERVICE_NAME

# Verificar estado
echo "📊 Estado del servicio:"
systemctl status $SERVICE_NAME --no-pager

echo ""
echo "✅ Instalación completada!"
echo ""
echo "Comandos útiles:"
echo "  - Ver estado: systemctl status $SERVICE_NAME"
echo "  - Ver logs: journalctl -u $SERVICE_NAME -f"
echo "  - Reiniciar: systemctl restart $SERVICE_NAME"
echo "  - Parar: systemctl stop $SERVICE_NAME"
echo "  - Iniciar: systemctl start $SERVICE_NAME"
echo ""
echo "⚠️  IMPORTANTE: Edita las variables de entorno en $SERVICE_DIR/$SERVICE_FILE"
echo "   especialmente las credenciales de Azure AD y JWT_SECRET"
