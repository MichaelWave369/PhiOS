#!/usr/bin/python
"""Collect bounded public hardware observations; no qualification or authority."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path


def value(path: Path, maximum: int = 256) -> str | None:
    try:
        with path.open() as handle:
            data = handle.read(maximum + 1).strip()
        return data if len(data) <= maximum and all(ord(c) >= 32 for c in data) else None
    except OSError:
        return None


def observe(iso_sha256: str | None) -> dict[str, object]:
    source = value(Path('/usr/share/phios/source-commit'))
    if not source or not re.fullmatch('[0-9a-f]{40}', source):
        raise ValueError('run this inside the built PhiOS image')
    if iso_sha256 is not None and not re.fullmatch('[0-9a-f]{64}', iso_sha256):
        raise ValueError('supplied ISO identity must be a lowercase SHA-256')
    devices = []
    for device in sorted(Path('/sys/bus/pci/devices').iterdir()):
        if len(devices) >= 1024:
            raise ValueError('PCI observation exceeds its bound')
        devices.append({'pci_address': device.name, 'vendor_id': value(device / 'vendor'),
            'device_id': value(device / 'device'), 'class_id': value(device / 'class'),
            'bound_driver': (device / 'driver').resolve().name if (device / 'driver').exists() else None})
    try:
        detected = subprocess.run(['/usr/bin/systemd-detect-virt'], text=True, capture_output=True, timeout=5)
        virtualization = detected.stdout.strip()[:64] if detected.returncode == 0 else 'not detected; physical hardware unproven'
    except (OSError, subprocess.SubprocessError):
        virtualization = 'unavailable'
    return {'schema_version': 'phios.hardware-observation.v1', 'observed_at': datetime.now(UTC).isoformat(),
        'source_commit': source, 'supplied_iso_sha256': iso_sha256, 'iso_bytes_independently_verified': False,
        'kernel': os.uname().release, 'architecture': os.uname().machine,
        'uefi_observed': Path('/sys/firmware/efi').is_dir(), 'virtualization_observation': virtualization,
        'board_vendor': value(Path('/sys/class/dmi/id/board_vendor')),
        'board_model': value(Path('/sys/class/dmi/id/board_name')),
        'firmware_version': value(Path('/sys/class/dmi/id/bios_version')), 'pci_devices': devices,
        'audio_cards_observed': len(list(Path('/sys/class/sound').glob('card[0-9]*'))),
        'physical_hardware_qualified': False, 'release_ready': False, 'execution_authority': False,
        'manual_tests': {name: 'not tested' for name in ['display_gpu', 'keyboard_mouse', 'wired_network',
            'wifi', 'audio', 'sleep_resume', 'shutdown_restart', 'dedicated_disk_install', 'data_persistence',
            'signed_update', 'interrupted_update', 'matched_recovery']}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iso-sha256', help='Previously verified candidate hash; marked supplied, not independently verified here')
    args = parser.parse_args()
    try:
        print(json.dumps(observe(args.iso_sha256), indent=2, sort_keys=True, allow_nan=False))
    except (OSError, ValueError) as exc:
        parser.exit(1, 'Hardware observation held: ' + str(exc) + '\n')
