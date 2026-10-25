from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
TILE=ROOT/'phishell/src/components/XiCommonsSourceTile.tsx'
SHELL=ROOT/'phishell/src/components/EcosystemCatalog.tsx'

class XiCommonsPublicTileTests(unittest.TestCase):
    def test_tile_is_source_only_and_offline_snapshot_only(self):
        text=TILE.read_text()
        for fragment in (
            'https://github.com/MichaelWave369/xi-vessel-bridge',
            'status: "SOURCE_ONLY"',
            'localSnapshotAvailableOffline: true',
            'externalSiteVerified: false',
            'installed: false',
            'bundledWebApp: false',
            'launchAuthorized: false',
            'repoWriteAuthorized: false',
            'liveXiConnected: false',
            'r17ExternalPilot: "BLOCKED"',
            'r18TwoHostTest: "NOT_RUN"',
            'NOT INSTALLED',
            'no gateway web app or Xi data is cached'
        ):
            self.assertIn(fragment,text)
        self.assertNotIn('fetch(',text)
        self.assertNotIn('WebSocket(',text)
        self.assertNotIn('installManifest',text)
    def test_tile_is_in_actual_ecosystem_screen_not_app_pipeline(self):
        shell=SHELL.read_text()
        self.assertIn('import { XiCommonsSourceTile } from "./XiCommonsSourceTile";',shell)
        self.assertIn('<XiCommonsSourceTile />',shell)
        self.assertIn('SOURCE_ONLY',TILE.read_text())
        self.assertNotIn('xi-phi-commons', (ROOT/'phishell/src/ecosystem/app-candidates.json').read_text().lower())
if __name__=='__main__':unittest.main()
