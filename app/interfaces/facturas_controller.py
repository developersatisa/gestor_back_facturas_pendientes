from fastapi import APIRouter, Depends, Query, HTTPException, status
from typing import List, Optional
from datetime import date
from sqlalchemy.orm import Session
from app.application.obtener_facturas_filtradas import ObtenerFacturasFiltradas
from app.application.obtener_estadisticas_facturas import ObtenerEstadisticasFacturas
from app.application.obtener_facturas_agrupadas_por_cliente import ObtenerFacturasAgrupadasPorCliente
from app.infrastructure.repositorio_facturas_simple import RepositorioFacturas, RepositorioClientes
from app.infrastructure.repositorio_gestion import RepositorioGestion
from app.domain.models.Factura import Factura
from app.config.database import get_facturas_db, get_clientes_db, get_gestion_db
import logging

router = APIRouter()

# Configuración de logging
logger = logging.getLogger("facturas")

# Dependency para el repositorio
def get_repo_facturas(db: Session = Depends(get_facturas_db)):
    return RepositorioFacturas(db)

def get_repo_clientes(db: Session = Depends(get_clientes_db)):
    return RepositorioClientes(db)
 
def get_repo_gestion(db: Session = Depends(get_gestion_db)):
    return RepositorioGestion(db)

@router.get("/api/facturas-cliente/{idcliente}", response_model=List[dict], tags=["Facturas"])
def obtener_facturas_cliente(
    idcliente: str,
    sociedad: Optional[str] = Query(None, description="Filtro por código de sociedad (CPY_0)"),
    repo_facturas: RepositorioFacturas = Depends(get_repo_facturas),
    repo_clientes: RepositorioClientes = Depends(get_repo_clientes),
    repo_gestion: RepositorioGestion = Depends(get_repo_gestion),
):
    try:
        # Obtener facturas del cliente específico
        use_case = ObtenerFacturasFiltradas(repo_facturas)
        facturas = use_case.execute(
            sociedad=sociedad,
            tercero=idcliente,  # Usar el idcliente como tercero
        )
        
        # Obtener datos del cliente
        datos_cliente = repo_clientes.obtener_cliente(idcliente)
        
        # Agregar datos del cliente a cada factura
        facturas_con_cliente = []
        for factura in facturas:
            factura_dict = factura.copy()
            factura_dict['datos_cliente'] = datos_cliente if datos_cliente else None
            facturas_con_cliente.append(factura_dict)
        
        logger.info(f"Facturas encontradas para cliente {idcliente}: {len(facturas_con_cliente)}")
        return facturas_con_cliente
    except Exception as e:
        logger.error(f"Error al obtener facturas del cliente {idcliente}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno del servidor")

@router.get("/api/clientes-con-resumen", response_model=List[dict], tags=["Clientes"])
def obtener_clientes_con_resumen(
    sociedad: Optional[str] = Query(None, description="Filtro por código de sociedad (CPY_0)"),
    tercero: Optional[str] = Query(None),
    fecha_desde: Optional[date] = Query(None),
    fecha_hasta: Optional[date] = Query(None),
    nivel_reclamacion: Optional[int] = Query(None),
    repo_facturas: RepositorioFacturas = Depends(get_repo_facturas),
    repo_clientes: RepositorioClientes = Depends(get_repo_clientes),
    repo_gestion: RepositorioGestion = Depends(get_repo_gestion),
):
    try:
        # Obtener facturas agrupadas por cliente
        use_case = ObtenerFacturasAgrupadasPorCliente(repo_facturas, repo_clientes, repo_gestion)
        try:
            clientes_con_facturas = use_case.execute(
                sociedad=sociedad,
                tercero=tercero,
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
                nivel_reclamacion=nivel_reclamacion,
            )
            print(clientes_con_facturas)
        except Exception as inner_err:
            # No tumbar el endpoint: devolver lista vacía y loguear el detalle
            logger.error(f"Error en use_case clientes-con-resumen: {inner_err}")
            clientes_con_facturas = []
        
        logger.info(f"Clientes con resumen encontrados: {len(clientes_con_facturas)}")
        return clientes_con_facturas
    except Exception as e:
        logger.error(f"Error al obtener clientes con resumen: {e}")
        # Fallback final seguro: no romper el cliente si algo inesperado sucede
        return []

@router.get("/api/estadisticas", response_model=dict, tags=["Estadísticas"])
def obtener_estadisticas(
    repo_facturas: RepositorioFacturas = Depends(get_repo_facturas),
    repo_clientes: RepositorioClientes = Depends(get_repo_clientes),
):
    try:
        use_case = ObtenerEstadisticasFacturas(repo_facturas, repo_clientes)
        estadisticas = use_case.execute()
        logger.info(f"Estadísticas calculadas: {estadisticas}")
        return estadisticas
    except Exception as e:
        logger.error(f"Error al obtener estadísticas: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"{e}")


@router.get("/api/facturas/historial-pago", response_model=dict | None, tags=["Facturas"])
def obtener_historial_pago(
    factura_id: Optional[str] = Query(None, description="Identificador de factura, p.ej. 'TYP-ASIENTO'"),
    tipo: Optional[str] = Query(None, description="Tipo de la factura (TYP_0)"),
    asiento: Optional[str] = Query(None, description="Asiento contable (ACCNUM_0)"),
    tercero: Optional[str] = Query(None, description="Código de cliente (BPR_0)"),
    sociedad: Optional[str] = Query(None, description="Código de sociedad (CPY_0)"),
    repo_facturas: RepositorioFacturas = Depends(get_repo_facturas),
):
    try:
        # Resolver factura_id
        fid = factura_id or (f"{tipo}-{asiento}" if (tipo and asiento) else None)
        if not fid:
            return None

        # Leer pago desde la tabla de SAGE X3 (x3v12.ATISAINT.facturas_cambio_pago)
        from sqlalchemy import text as sqltext
        try:
            q_pago = sqltext(
                """
                SELECT TOP 1 factura_id, fecha_cambio, monto_pagado, BPR_0
                FROM ATISAINT.facturas_cambio_pago
                WHERE factura_id = :fid
                ORDER BY fecha_cambio DESC
                """
            )
            row_pago = repo_facturas.db.execute(q_pago, {"fid": fid}).mappings().first()
        except Exception:
            row_pago = None
        if not row_pago:
            return None

        # Intentar enriquecer con vencimiento desde la BD de facturas reales
        try:
            partes = str(fid).split('-')
            if len(partes) >= 2:
                q = sqltext("""
                    SELECT TOP 1 DUDDAT_0 AS venc
                    FROM x3v12.ATISAINT.GACCDUDATE
                    WHERE TYP_0 = :tipo AND ACCNUM_0 = :asiento
                """)
                row = repo_facturas.db.execute(q, {"tipo": partes[0], "asiento": partes[1]}).first()
                if row and hasattr(row, 'venc'):
                    venc = row.venc
                else:
                    venc = None
            else:
                venc = None
        except Exception:
            venc = None

        # Calcular días de retraso si es posible
        dias = None
        try:
            if venc is not None and row_pago.get('fecha_cambio') is not None:
                from datetime import date
                v = row_pago['fecha_cambio']
                # v y venc pueden ser datetime/date; convertir a date
                fp = v.date() if hasattr(v, 'date') else v
                vc = venc.date() if hasattr(venc, 'date') else venc
                dias = (fp - vc).days
                if dias < 0:
                    dias = 0
        except Exception:
            dias = None

        return {
            "factura_id": fid,
            "fecha_pago": row_pago.get('fecha_cambio'),
            "vencimiento": venc,
            "dias_retraso": dias,
            "monto_pagado": row_pago.get('monto_pagado'),
        }
    except Exception as e:
        logger.error(f"Error al obtener historial de pago: {e}")
        # Preferimos no romper el frontend: devolver None
        return None


@router.get("/api/facturas/historial-pagadas", response_model=List[dict], tags=["Facturas"])
def listar_historial_pagadas(
    tercero: Optional[str] = Query(None, description="Código de cliente (BPR_0) para filtrar"),
    factura_id: Optional[str] = Query(None, description="ID específico de factura (ROWID) para filtrar"),
    limit: int = Query(200, ge=1, le=1000),
    repo_gestion: RepositorioGestion = Depends(get_repo_gestion),
    repo_facturas: RepositorioFacturas = Depends(get_repo_facturas),
):
    """Lista facturas pagadas (vencidas) a partir de la tabla externa `facturas_cambio_pago`.

    Nota: `facturas_cambio_pago` no guarda el tercero; se resuelve por `tipo` y `asiento`
    consultando la tabla real de facturas. Si `tercero` se proporciona, se filtra por él.
    """
    try:
        logger.info(f"🔍 Listando historial pagadas - tercero: {tercero}, limit: {limit}")
        from sqlalchemy import text as sqltext
        
        # Verificar si la tabla existe primero
        try:
            check_table_sql = "SELECT COUNT(*) as count FROM ATISAINT.facturas_cambio_pago"
            result = repo_facturas.db.execute(sqltext(check_table_sql)).first()
            logger.info(f"🔍 Tabla facturas_cambio_pago tiene {result[0] if result else 0} registros")
        except Exception as e:
            logger.error(f"❌ Error verificando tabla facturas_cambio_pago: {e}")
            return []
        
        # Si no hay datos, devolver array vacío
        if not result or result[0] == 0:
            logger.info("📊 No hay datos en la tabla facturas_cambio_pago")
            return []
        
        # Construir SQL según dialecto
        try:
            dialect = repo_facturas.db.bind.dialect.name if hasattr(repo_facturas.db, 'bind') else 'mssql'
        except Exception:
            dialect = 'mssql'

        # Leer desde la BD de facturas (SAGE X3): esquema ATISAINT
        table_name = 'ATISAINT.facturas_cambio_pago'
        # MSSQL: TOP, otros: LIMIT
      
        base_sql = f"SELECT factura_id, fecha_cambio, monto_pagado, idcliente FROM {table_name}"

        filtros = []
        params = {}
        if tercero:
            filtros.append("idcliente = :tercero")
            params["tercero"] = str(tercero)
        if factura_id:
            filtros.append("factura_id = :factura_id")
            params["factura_id"] = str(factura_id)

        where_sql = (" WHERE " + " AND ".join(filtros)) if filtros else ""
        order_sql = " ORDER BY fecha_cambio DESC"
        tail_sql = "" if dialect == 'mssql' else f" LIMIT {int(limit)}"

        q = sqltext(base_sql + where_sql + order_sql + tail_sql)
        logger.info(f"🔍 SQL ejecutado: {base_sql + where_sql + order_sql + tail_sql}")
        logger.info(f"🔍 Parámetros: {params}")
        rows = repo_facturas.db.execute(q, params).mappings().all()
        logger.info(f"📊 Filas encontradas: {len(rows)}")

        def _norm(v: Optional[str]) -> Optional[str]:
            if v is None:
                return None
            s = str(v).strip()
            if s == "":
                return s
            # Normalizar ceros a la izquierda si es numérico
            try:
                # Mantener no numéricos tal cual
                if s.isdigit():
                    return str(int(s))
            except Exception:
                pass
            return s

        tercero_norm = _norm(tercero) if tercero else None

        # Agrupar pagos por factura
        facturas_pagos = {}
        for r in rows:
            factura_id = str(r.get('factura_id'))
            if not factura_id:
                continue
                
            if factura_id not in facturas_pagos:
                facturas_pagos[factura_id] = {
                    'pagos': [],
                    'total_pagado': 0,
                    'datos_factura': None
                }
            
            # Agregar pago a la factura (puede haber múltiples pagos para la misma factura)
            monto_pagado = r.get('monto_pagado') or 0
            fecha_pago = r.get('fecha_cambio')
            
            # Verificar si ya existe un pago con la misma fecha para evitar duplicados
            pago_existente = False
            for pago in facturas_pagos[factura_id]['pagos']:
                if pago['fecha_pago'] == fecha_pago and pago['monto_pagado'] == monto_pagado:
                    pago_existente = True
                    break
            
            if not pago_existente:
                facturas_pagos[factura_id]['pagos'].append({
                    'fecha_pago': fecha_pago,
                    'monto_pagado': monto_pagado
                })
                facturas_pagos[factura_id]['total_pagado'] += monto_pagado
                
                # Ordenar pagos por fecha (más reciente primero)
                facturas_pagos[factura_id]['pagos'].sort(
                    key=lambda x: x['fecha_pago'] if x['fecha_pago'] else '', 
                    reverse=True
                )
            
            # Buscar datos de la factura solo una vez
            if facturas_pagos[factura_id]['datos_factura'] is None:
                try:
                    gaccdudate_sql = """
                        SELECT TOP 1 BPR_0 AS tercero, DUDDAT_0 AS vencimiento, CPY_0 AS sociedad, 
                               TYP_0 AS tipo, ACCNUM_0 AS asiento, ROWID, AMTCUR_0 AS importe_total
                        FROM x3v12.ATISAINT.GACCDUDATE
                        WHERE ROWID = :factura_id
                    """
                    gaccdudate_result = repo_facturas.db.execute(sqltext(gaccdudate_sql), {"factura_id": factura_id}).mappings().first()
                    
                    if gaccdudate_result:
                        facturas_pagos[factura_id]['datos_factura'] = gaccdudate_result
                    else:
                        # Datos básicos si no se encuentra en GACCDUDATE
                        facturas_pagos[factura_id]['datos_factura'] = {
                            'tercero': r.get('idcliente'),
                            'vencimiento': None,
                            'sociedad': None,
                            'tipo': None,
                            'asiento': None,
                            'importe_total': None
                        }
                except Exception as e:
                    logger.warning(f"Error consultando GACCDUDATE para factura {factura_id}: {e}")
                    facturas_pagos[factura_id]['datos_factura'] = {
                        'tercero': r.get('idcliente'),
                        'vencimiento': None,
                        'sociedad': None,
                        'tipo': None,
                        'asiento': None,
                        'importe_total': None
                    }
        
        # Convertir a formato de salida
        out: List[dict] = []
        for factura_id, datos in facturas_pagos.items():
            datos_factura = datos['datos_factura']
            
            # Aplicar filtro por tercero si se especifica
            tercero_factura = datos_factura.get('tercero')
            if tercero and tercero_norm and _norm(tercero_factura) != tercero_norm:
                continue
            
            # Calcular días de retraso (usar el primer pago - el más temprano)
            dias_retraso = None
            if datos['pagos'] and datos_factura.get('vencimiento'):
                try:
                    venc = datos_factura['vencimiento']
                    # Usar el último pago de la lista ordenada (el más temprano)
                    primer_pago = datos['pagos'][-1]['fecha_pago']
                    
                    # Convertir fechas a objetos date
                    if hasattr(venc, 'date'):
                        vc = venc.date()
                    elif isinstance(venc, str):
                        from datetime import datetime
                        vc = datetime.fromisoformat(venc.replace('Z', '+00:00')).date()
                    else:
                        vc = venc
                    
                    if hasattr(primer_pago, 'date'):
                        fp = primer_pago.date()
                    elif isinstance(primer_pago, str):
                        from datetime import datetime
                        fp = datetime.fromisoformat(primer_pago.replace('Z', '+00:00')).date()
                    else:
                        fp = primer_pago
                    
                    dias_retraso = (fp - vc).days
                    if dias_retraso < 0:
                        dias_retraso = 0
                except Exception as e:
                    logger.warning(f"Error calculando días de retraso: {e}")
                    dias_retraso = None
            
            # Calcular importe pendiente
            importe_total = datos_factura.get('importe_total') or 0
            importe_pendiente = max(0, importe_total - datos['total_pagado'])
            
            out.append({
                "factura_id": factura_id,
                "tipo": datos_factura.get('tipo'),
                "asiento": datos_factura.get('asiento'),
                "tercero": tercero_factura,
                "sociedad": datos_factura.get('sociedad'),
                "vencimiento": datos_factura.get('vencimiento'),
                "importe_total": importe_total,
                "total_pagado": datos['total_pagado'],
                "importe_pendiente": importe_pendiente,
                "dias_retraso": dias_retraso,
                "pagos": datos['pagos']
            })

        logger.info(f"📊 Resultado final: {len(out)} facturas pagadas")
        return out
    except Exception as e:
        logger.error(f"Error al listar historial pagadas: {e}")
        return []


@router.get("/api/facturas/historial-pagadas/debug", tags=["Facturas"])
def debug_historial_pagadas(
    repo_facturas: RepositorioFacturas = Depends(get_repo_facturas),
):
    """Endpoint de diagnóstico para ver la estructura de la tabla facturas_cambio_pago."""
    try:
        from sqlalchemy import text as sqltext
        
        # Verificar estructura de la tabla
        try:
            # Intentar leer las primeras filas para ver qué columnas existen
            debug_sql = "SELECT TOP 1 * FROM ATISAINT.facturas_cambio_pago"
            result = repo_facturas.db.execute(sqltext(debug_sql)).mappings().first()
            
            if result:
                return {
                    "message": "Estructura de tabla encontrada",
                    "columns": list(result.keys()),
                    "sample_data": dict(result)
                }
            else:
                return {"message": "Tabla vacía o no existe"}
                
        except Exception as e:
            return {"error": f"Error consultando tabla: {str(e)}"}
            
    except Exception as e:
        return {"error": str(e)}



