"""
cli.py — Entry point para flow-nanobanana.

Uso:
    python cli.py --login --account otra                     # Login manual (crea o renueva una cuenta)
    python cli.py --accounts                                 # Listar cuentas y proxima en rotar
    python cli.py --record                                   # Grabar macro
    python cli.py --record --name mi-flujo                   # Grabar macro con nombre
    python cli.py --replay --image foto.jpg --prompt "..."   # Replay del ultimo macro
    python cli.py --replay mi-flujo --image foto.jpg -p ".." # Replay de macro especifico
    python cli.py --list                                     # Listar macros grabados
    python cli.py --image foto.jpg --prompt "..."            # Generar (modo directo)
    python cli.py --gen-key                                  # Generar clave de encriptacion
    python cli.py --export-creds                             # Exportar credenciales encriptadas

Las generaciones rotan entre cuentas; --account fuerza una sola.
"""

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="flow-nano",
        description="Wrapper ligero para Google Labs Flow — generacion de imagenes con IA",
    )

    # Modos de operacion
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--login", action="store_true", help="Abrir browser para login manual en Google")
    mode.add_argument("--record", action="store_true", help="Grabar macro (abre Playwright Inspector)")
    mode.add_argument("--replay", nargs="?", const="__latest__", metavar="MACRO",
                       help="Ejecutar macro grabado (sin nombre = el mas reciente)")
    mode.add_argument("--list", action="store_true", help="Listar macros grabados")
    mode.add_argument("--accounts", action="store_true", help="Listar cuentas y la proxima en la rotacion")
    mode.add_argument("--import-chrome", nargs="?", const="__list__", metavar="CORREO",
                       help="Clonar la sesion de una cuenta de tu Chrome; sin valor lista las cuentas")
    mode.add_argument("--gen-key", action="store_true", help="Generar clave de encriptacion")
    mode.add_argument("--export-creds", action="store_true", help="Exportar credenciales encriptadas")

    # Parametros de generacion
    parser.add_argument("--image", "-i", type=Path, help="Ruta a la imagen de entrada")
    parser.add_argument("--prompt", "-p", type=str, help="Prompt de texto para la generacion")
    parser.add_argument("--prompt-file", type=Path, help="Leer prompt desde archivo de texto")
    parser.add_argument("--output", "-o", type=Path, default=None,
                        help="Ruta de salida (default: output/flow_result_<ts>.png)")
    parser.add_argument("--name", "-n", type=str, default=None, help="Nombre del macro (para --record)")
    parser.add_argument("--visible", action="store_true", help="Mostrar browser (no headless)")
    parser.add_argument("--account", "-a", type=str, default=None,
                        help="Cuenta a usar (default: rotar entre todas)")

    args = parser.parse_args()

    # --prompt-file tiene prioridad sobre --prompt
    if args.prompt_file:
        if not args.prompt_file.exists():
            parser.error(f"Archivo no encontrado: {args.prompt_file}")
        content = args.prompt_file.read_text(encoding="utf-8").strip()
        if args.prompt_file.suffix == ".json":
            import json
            data = json.loads(content)
            args.prompt = data["prompt"]
        else:
            args.prompt = content

    return args


# ── Comandos ──────────────────────────────────────────────────────


async def cmd_login(account: str | None):
    from core.accounts import resolve_account
    from flow.auth import login

    await login(resolve_account(account))


def cmd_accounts():
    from core.accounts import has_credentials, has_profile, list_accounts, rotation_order

    accounts = list_accounts()
    if not accounts:
        print("No hay cuentas. Crea una con: make login ACCOUNT=<nombre>")
        return

    next_account = rotation_order()[0]
    print(f"\nCuentas ({len(accounts)}):\n")
    for name in accounts:
        sources = [s for s, ok in (("perfil", has_profile(name)), (".enc", has_credentials(name))) if ok]
        marker = "  <- proxima" if name == next_account else ""
        print(f"  {name:<20}  {', '.join(sources)}{marker}")
    print()


async def cmd_import_chrome(email: str, account: str | None):
    from core.chrome_import import import_from_chrome, list_chrome_profiles

    if email == "__list__":
        print("\nCuentas en tu Chrome:\n")
        for prof in list_chrome_profiles():
            print(f"  {prof['dir']:<12}  {', '.join(prof['emails'])}")
        print("\nUso: make importar CHROME=<correo> ACCOUNT=<nombre>\n")
        return

    if not account:
        raise ValueError("Indica el nombre de la cuenta destino con ACCOUNT=<nombre> (o --account)")
    url = await import_from_chrome(email, account)
    print(f"\nCuenta '{account}' lista: {email} en {url}")


def cmd_record(name: str | None, account: str | None):
    from flow.recorder import record

    output = record(name=name, account=account)
    print(f"\nMacro guardado en: {output}")


def cmd_list():
    from flow.recorder import list_recordings

    recordings = list_recordings()
    if not recordings:
        print("No hay macros grabados. Usa --record para crear uno.")
        return

    print(f"\nMacros disponibles ({len(recordings)}):\n")
    for r in recordings:
        print(f"  {r['name']:<30}  {r['modified'][:19]}  ({r['size']} bytes)")
    print(f"\nUso: flow-nano --replay {recordings[-1]['name']} --image foto.jpg --prompt '...'")


async def cmd_replay(
    macro_name: str, image: Path | None, prompt: str | None, output: Path | None, visible: bool, account: str | None
):
    from flow.replayer import replay, replay_latest

    if output is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = Path("output") / f"flow_result_{ts}.png"

    headless = not visible

    if macro_name == "__latest__":
        result = await replay_latest(image, prompt, output, headless, account)
    else:
        result = await replay(macro_name, image, prompt, output, headless, account)

    if result:
        print(f"\nResultado guardado en: {result}")


def cmd_gen_key():
    from core.credentials import generate_key

    key = generate_key()
    print(f"\nClave generada:\n\n  {key}\n")
    print("Guardala en tu .env o exportala:")
    print(f"  export FLOW_CREDENTIALS_KEY={key}\n")


async def cmd_export_creds(output: Path | None, account: str | None):
    from core.accounts import resolve_account
    from core.credentials import export_credentials

    result = await export_credentials(resolve_account(account), output)
    print(f"\nCredenciales exportadas a: {result}")
    print("Para usar en otro entorno copia ese archivo a la misma ruta y define:")
    print("  export FLOW_CREDENTIALS_KEY=<tu-clave>\n")


async def cmd_generate(image: Path, prompt: str, output: Path | None, visible: bool, account: str | None):
    from core.accounts import rotation_order
    from flow.client import FlowClient

    headless = not visible
    async with FlowClient(rotation_order(account)[0], headless=headless) as client:
        result = await client.generate(image, prompt, output)
        print(f"\nResultado guardado en: {result}")


# ── Main ──────────────────────────────────────────────────────────


def main():
    args = parse_args()

    if args.login:
        asyncio.run(cmd_login(args.account))
        return

    if args.record:
        cmd_record(args.name, args.account)
        return

    if args.gen_key:
        cmd_gen_key()
        return

    if args.export_creds:
        asyncio.run(cmd_export_creds(args.output, args.account))
        return

    if args.list:
        cmd_list()
        return

    if args.accounts:
        cmd_accounts()
        return

    if args.import_chrome is not None:
        try:
            asyncio.run(cmd_import_chrome(args.import_chrome, args.account))
        except (RuntimeError, FileNotFoundError, ValueError) as e:
            print(f"\nError: {e}", file=sys.stderr)
            sys.exit(1)
        return

    if args.replay is not None:
        try:
            asyncio.run(cmd_replay(args.replay, args.image, args.prompt, args.output, args.visible, args.account))
        except (RuntimeError, FileNotFoundError, ValueError) as e:
            print(f"\nError: {e}", file=sys.stderr)
            sys.exit(1)
        return

    # Modo directo (sin macro)
    if not args.image or not args.prompt:
        print("Error: --image y --prompt son requeridos para generar.", file=sys.stderr)
        print("", file=sys.stderr)
        print("Modos disponibles:", file=sys.stderr)
        print("  flow-nano --login [--account x]                      # Login (crea/renueva cuenta)", file=sys.stderr)
        print("  flow-nano --accounts                                 # Listar cuentas", file=sys.stderr)
        print("  flow-nano --record                                   # Grabar macro", file=sys.stderr)
        print("  flow-nano --replay --image foto.jpg --prompt '...'   # Replay macro", file=sys.stderr)
        print("  flow-nano --list                                     # Listar macros", file=sys.stderr)
        print("  flow-nano --image foto.jpg --prompt '...'            # Modo directo", file=sys.stderr)
        print("  flow-nano --gen-key                                  # Generar clave", file=sys.stderr)
        print("  flow-nano --export-creds                             # Exportar credenciales", file=sys.stderr)
        sys.exit(1)

    asyncio.run(cmd_generate(args.image, args.prompt, args.output, args.visible, args.account))


if __name__ == "__main__":
    main()
