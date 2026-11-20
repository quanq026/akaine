"""Send commands to an installed Akaine 7.3.1 client."""
from .bridge import main as run_cli
from .contracts import PRODUCTION


def main(argv=None):
    return run_cli(argv, target=PRODUCTION)


if __name__ == '__main__':
    raise SystemExit(main())
