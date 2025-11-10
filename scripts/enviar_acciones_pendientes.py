#!/usr/bin/env python3
"""Script CLI para enviar las acciones con fecha de aviso vencida o hoy."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv


def _configure_paths() -> None:
    """Añade la raíz del backend al `sys.path` para importar `app.*`."""
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


_configure_paths()

from app.config.database import GestionSessionLocal, FacturasSessionLocal  # noqa: E402
from app.infrastructure.repositorio_registro_facturas import RepositorioRegistroFacturas  # noqa: E402
from app.infrastructure.repositorio_facturas_simple import RepositorioFacturas  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Emite correos para acciones con fecha de aviso vencida o hoy."
    )
    parser.add_argument(
        "--fecha",
        dest="fecha",
        help="Fecha de corte en formato YYYY-MM-DD (opcional, por defecto usa hoy).",
    )
    parser.add_argument(
        "--log-level",
        dest="log_level",
        default="INFO",
        help="Nivel de logging (DEBUG, INFO, WARNING, ERROR).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simular envío sin mandar correos (muestra qué acciones se enviarían).",
    )
    parser.add_argument(
        "--solo-filtrar",
        action="store_true",
        help="Solo listar las acciones pendientes después de filtrar las facturas pagadas (no envía nada).",
    )
    parser.add_argument(
        "--mostrar-omitidas",
        action="store_true",
        help="Mostrar también las acciones omitidas por factura pagada en los logs.",
    )
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    gestion_session = GestionSessionLocal()
    facturas_session = FacturasSessionLocal()
    try:
        repo = RepositorioRegistroFacturas(gestion_session)
        repo_facturas = RepositorioFacturas(facturas_session)
        
        pendientes = repo.listar_pendientes_envio(fecha_iso=args.fecha)
        logging.info("Acciones pendientes encontradas: %s", len(pendientes))
        
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            for accion in pendientes:
                logging.debug(
                    "Accion pendiente -> id=%s | idcliente=%s | tercero=%s | factura=%s-%s | aviso=%s | estado=%s",
                    accion.id,
                    accion.idcliente,
                    accion.tercero,
                    accion.tipo,
                    accion.asiento,
                    accion.aviso.isoformat() if accion.aviso else "sin fecha",
                    accion.envio_estado,
                )

        resultado = repo.enviar_pendientes(
            fecha_iso=args.fecha,
            repo_facturas=repo_facturas,
            simular=args.dry_run,
            solo_filtrar=args.solo_filtrar,
            mostrar_omitidas=args.mostrar_omitidas,
        )
        
        if args.solo_filtrar:
            # Cuando solo_filtrar=True, resultado puede ser una lista o 0 si no hay acciones
            if isinstance(resultado, list):
                logging.info("Acciones tras filtrar (sin envío): %s", len(resultado))
                for info in resultado:
                    logging.info(
                        "ACCIÓN LISTA -> id=%s | idcliente=%s | tercero=%s | factura=%s | aviso=%s",
                        info["id"],
                        info["idcliente"],
                        info["tercero"],
                        info["factura_nombre"],
                        info["aviso"],
                    )
            else:
                logging.info("Acciones tras filtrar (sin envío): 0")
            return 0

        if args.dry_run:
            logging.info("Simulación completada. Acciones pendientes: %s", resultado)
        else:
            logging.info("Acciones emitidas: %s", resultado)
        return 0
    except Exception:
        logging.exception("Error enviando acciones pendientes")
        return 1
    finally:
        try:
            gestion_session.close()
        except Exception:
            logging.getLogger(__name__).warning("No se pudo cerrar la sesión de BD")
        try:
            facturas_session.close()
        except Exception:
            logging.getLogger(__name__).warning("No se pudo cerrar la sesión de facturas")


if __name__ == "__main__":
    raise SystemExit(main())
