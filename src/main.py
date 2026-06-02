from __future__ import annotations

import sys
from pathlib import Path


SRC_ROOT = Path(__file__).resolve().parent
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from app.gui import ElectrochemistryApp


def main() -> None:
    app = ElectrochemistryApp(config_path=SRC_ROOT.parent / "config" / "default_config.json")
    app.run()


if __name__ == "__main__":
    main()