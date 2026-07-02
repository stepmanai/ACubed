# plugins/etterna/config.py

from __future__ import annotations

import os
from dataclasses import dataclass

from acubed.domain.game.protocols import GameConfig


@dataclass(frozen=True)
class EtternaConfig(GameConfig):
    base_api_url: str = "https://api.etternaonline.com/api"
    google_drive_folder_id: str = os.getenv(
        "ETTERNA_GOOGLE_DRIVE_FOLDER_ID",
        "14l_PXmYsahLm3DQRgQMu5gprdc1LJNXS",
    )
    google_credentials_path: str | None = (
        os.getenv("ETTERNA_GOOGLE_CREDENTIALS_PATH")
        or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        # or r"C:\Users\wcheu\OneDrive\Desktop\New folder\credentials.json"
        or r"/home/wirrywoo/ACubed/credentials.json"
    )
