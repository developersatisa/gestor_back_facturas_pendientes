#!/usr/bin/env python3
"""Script CLI para enviar las acciones con fecha de aviso vencida."""

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

from app.config.database import GestionSessionLocal  # noqa: E402
from app.infrastructure.repositorio_registro_facturas import RepositorioRegistroFacturas  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Emite correos para acciones con fecha de aviso vencida o hoy."
    )
    parser.add_argument(
        "--fecha",
        dest="fecha",
        help="Fecha de corte en formato YYYY-MM-DD (opcional).",
    )
    parser.add_argument(
        "--log-level",
        dest="log_level",
        default="INFO",
        help="Nivel de logging (DEBUG, INFO, WARNING, ERROR).",
    )
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    session = GestionSessionLocal()
    try:
        repo = RepositorioRegistroFacturas(session)
        enviados = repo.enviar_pendientes(fecha_iso=args.fecha)
        logging.info("Acciones emitidas: %s", enviados)
        return 0
    except Exception:
        logging.exception("Error enviando acciones pendientes")
        return 1
    finally:
        try:
            session.close()
        except Exception:
            logging.getLogger(__name__).warning("No se pudo cerrar la sesión de BD")


if __name__ == "__main__":
    raise SystemExit(main())


