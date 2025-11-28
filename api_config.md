# Configuración API Facturas Atisa

## URL Base
```
http://127.0.0.1:8000
```

## Endpoints Disponibles

### 1. Health Check
```
GET /health
```
**Respuesta:**
```json
{
  "status": "ok",
  "title": "API Facturas Atisa",
  "version": "1.0.0"
}
```

### 2. Obtener Facturas de un Cliente Específico
```
GET /api/facturas-cliente/{idcliente}
```

**Descripción:** Obtiene todas las facturas de un cliente específico con sus datos completos.

**Parámetros de ruta:**
- `idcliente` (string) - ID del cliente (obligatorio)

**Parámetros de consulta:** Ninguno (sin filtros opcionales)

**Ejemplo de uso:**
```
GET /api/facturas-cliente/00542
```

**Respuesta:**
```json
[
  {
    "tipo": "VEN",
    "asiento": 12345,
    "sociedad": "S005",
    "planta": "PLANTA1",
    "moneda": "EUR",
    "colectivo": "4300",
    "tercero": "00542",
    "vencimiento": "2024-12-31T00:00:00",
    "forma_pago": "TRANSFERENCIA",
    "sentido": 1,
    "importe": 1500.50,
    "pago": 0.0,
    "nivel_reclamacion": 1,
    "fecha_reclamacion": null,
    "check_pago": 1,
    "estado": "verde",
    "datos_cliente": {
      "idcliente": "00542",
      "razsoc": "Empresa Ejemplo S.L.",
      "cif": "B12345678",
      "cif_empresa": "B12345678"
    }
  }
]
```

**Filtros fijos aplicados:**
- `TYP_0 NOT IN ('AA', 'ZZ')` - Excluye tipos AA y ZZ
- `SAC_0 = '4300'` - Solo colectivo 4300
- `FLGCLE_0 = 1` - Solo facturas pendientes

### 3. Obtener Clientes con Resumen
```
GET /api/clientes-con-resumen
```

**Descripción:** Obtiene un resumen agrupado por cliente con número de facturas, montos y datos del cliente.

**Parámetros de consulta (opcionales):**
- `tercero` (string) - Filtrar por BPR_0 (tercero específico)
- `fecha_desde` (date) - Fecha desde (formato: YYYY-MM-DD)
- `fecha_hasta` (date) - Fecha hasta (formato: YYYY-MM-DD)
- `nivel_reclamacion` (integer) - Nivel de reclamación específico

**Ejemplo de uso:**
```
GET /api/clientes-con-resumen?tercero=00542
GET /api/clientes-con-resumen?nivel_reclamacion=2
GET /api/clientes-con-resumen?fecha_desde=2024-01-01&tercero=00542
```

**Respuesta:**
```json
[
  {
    "idcliente": "00542",
    "nombre_cliente": "Empresa Ejemplo S.L.",
    "cif_cliente": "B12345678",
    "numero_facturas": 5,
    "monto_debe": 15000.50,
    "estado": "verde"
  }
]
```

**Filtros fijos aplicados:**
- `TYP_0 NOT IN ('AA', 'ZZ')` - Excluye tipos AA y ZZ
- `SAC_0 = '4300'` - Solo colectivo 4300
- `FLGCLE_0 = 1` - Solo facturas pendientes

### 4. Estadísticas de Facturas
```
GET /api/estadisticas
```

**Descripción:** Primera API que debe llamarse. Obtiene estadísticas resumidas usando consultas SQL directas.

**Parámetros:** Ninguno (sin parámetros de consulta)

**Ejemplo de uso:**
```
GET /api/estadisticas
```

**Respuesta:**
```json
{
  "total_empresas_pendientes": 150,
  "total_facturas_pendientes": 1250,
  "monto_total_adeudado": 125000.50,
  "empresas_con_montos": [
    {
      "idcliente": "17814",
      "nombre": "Empresa Ejemplo S.L.",
      "monto": 25000.50
    },
    {
      "idcliente": "17815",
      "nombre": "Otra Empresa S.A.",
      "monto": 15000.25
    }
  ],
  "filtros_aplicados": {
    "tipo_excluido": ["AA", "ZZ"],
    "colectivo": "4300",
    "check_pago": 1
  }
}
```

**Consultas SQL utilizadas:**
1. **Total de empresas pendientes:** `COUNT(DISTINCT BPR_0)` 
2. **Total de facturas pendientes:** `COUNT(*)`
3. **Monto total adeudado:** `SUM(AMTCUR_0)`
4. **Empresas con montos:** `SELECT BPR_0, SUM(AMTCUR_0) GROUP BY BPR_0 ORDER BY monto_total DESC`

**Filtros aplicados:**
- `TYP_0 NOT IN ('AA', 'ZZ')`
- `SAC_0 = '4300'`
- `FLGCLE_0 = 1`

### 5. Descargar Excel de Empresas por Sociedad
```
GET /api/estadisticas/excel
```

**Descripción:** Genera un archivo Excel con empresas y sus facturas agrupadas por sociedad (S005, S010, S001). Los datos coinciden exactamente con el dashboard.

**Parámetros de consulta:**
- `filtro` (string, opcional) - Filtro de saldo. Valores posibles:
  - `all` (por defecto): Todas las empresas con saldo (positivo o negativo)
  - `cliente_debe_empresa`: Solo empresas con saldo positivo (cobro pendiente)
  - `empresa_debe_cliente`: Solo empresas con saldo negativo (reintegro pendiente)

**Ejemplo de uso:**
```
GET /api/estadisticas/excel
GET /api/estadisticas/excel?filtro=cliente_debe_empresa
GET /api/estadisticas/excel?filtro=empresa_debe_cliente
```

**Respuesta:**
- Content-Type: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- Content-Disposition: `attachment; filename=informe_empresas_por_sociedad_YYYYMMDD_HHMMSS.xlsx`
- Archivo Excel con estructura:
  - Encabezado: Título según filtro, fecha de generación
  - Tres columnas por sociedad (Grupo Atisa, Selier, Asesores Titulados)
  - Para cada empresa: ID, nombre, facturas individuales con montos
  - Totales por sociedad
  - Total general con empresas únicas y total (con repeticiones)

**Características:**
- **Sincronización con dashboard**: Usa la misma consulta base que `/api/estadisticas` para garantizar coincidencia exacta
- **Cálculo de totales**: Suma por empresa (no por sociedad) para evitar duplicados cuando una empresa aparece en múltiples sociedades
- **Filtros**: Aplica el mismo filtro que el dashboard según el parámetro recibido
- **Solo SQL Server**: Requiere conexión MSSQL; devuelve 503 si se usa SQLite

**Filtros aplicados (base):**
- `SAC_0 IN ('4300','4302')`
- `TYP_0 NOT IN ('AA','ZZ')`
- `DUDDAT_0 < GETDATE()` (facturas vencidas)
- `FLGCLE_0 <> 2`
- `CPY_0 IN ('S005','S001','S010')` (solo estas sociedades)

## Documentación Automática
```
http://127.0.0.1:8000/docs
```

## Configuración CORS
La API está configurada para aceptar conexiones desde:
- `http://localhost:5173` (Vite)
- `http://localhost:3000` (React)
- `http://127.0.0.1:3000`
- `http://10.150.22.15:5173`
- Cualquier origen (para desarrollo)

## Estados de Facturas
- **verde**: Nivel de reclamación < 2
- **amarillo**: Nivel de reclamación = 2
- **rojo**: Nivel de reclamación >= 3 