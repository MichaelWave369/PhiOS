"""External ordinary-user desktop probe; never installed into the ISO."""
from __future__ import annotations

import json
import os
import struct
import subprocess
import tempfile
import time
import wave
from pathlib import Path


def desktop_services(source: str, *, wired: bool = False) -> dict:
    assert os.getuid() == 1000 and os.geteuid() == 1000
    assert Path('/usr/share/phios/source-commit').read_text().strip() == source
    units = ['phios-audio.target', 'pipewire.service', 'pipewire-pulse.service', 'wireplumber.service', 'phios-policykit.service']
    for _ in range(60):
        active = subprocess.run(['systemctl', '--user', 'is-active', '--quiet', *units]).returncode == 0
        graph = json.loads(subprocess.check_output(['pw-dump'], text=True, timeout=10)) if active else []
        devices = [item for item in graph if item.get('type') == 'PipeWire:Interface:Device' and
                   item.get('info', {}).get('props', {}).get('device.api') == 'alsa']
        sinks = [item for item in graph if item.get('type') == 'PipeWire:Interface:Node' and
                 item.get('info', {}).get('props', {}).get('media.class') == 'Audio/Sink' and
                 item.get('info', {}).get('props', {}).get('factory.name') == 'api.alsa.pcm.sink']
        if active and devices and sinks:
            break
        time.sleep(1)
    else:
        subprocess.run(['journalctl', '--user', '--no-pager', '-n', '60', '-u', 'pipewire', '-u', 'wireplumber'])
        raise RuntimeError('user audio session did not expose the actual emulated ALSA device/sink')
    for name in ['pipewire', 'pipewire-pulse', 'wireplumber']:
        subprocess.run(['pgrep', '-u', '1000', '-x', name], check=True, stdout=subprocess.DEVNULL)
    agent_pid = subprocess.check_output(['systemctl', '--user', 'show', 'phios-policykit.service',
                                        '--property=MainPID', '--value'], text=True).strip()
    assert agent_pid.isdigit() and int(agent_pid) > 0
    status = (Path('/proc') / agent_pid / 'status').read_text().splitlines()
    assert next(line for line in status if line.startswith('Uid:')).split()[1:] == ['1000'] * 4
    # The VM has a synthetic HDA device with a QEMU null backend, not host audio.
    # Play actual PCM frames through the selected ALSA sink; hearing/capture is
    # a separate physical test and is never inferred from this return code.
    with tempfile.TemporaryDirectory(prefix='phios-audio-probe-') as temporary:
        path = Path(temporary) / 'probe.wav'
        with wave.open(str(path), 'wb') as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(48000)
            stream.writeframes(b''.join(struct.pack('<h', 1000 if (i // 40) % 2 else -1000) for i in range(9600)))
        subprocess.run(['pw-play', '--target', str(sinks[0]['id']), str(path)], check=True, timeout=30)
    subprocess.run(['systemctl', 'is-active', '--quiet', 'NetworkManager.service', 'systemd-resolved.service'], check=True)
    observed = {'source_commit': source, 'uid': os.getuid(), 'user_audio_services': True, 'nonroot_graphical_policykit_agent': True,
                'emulated_alsa_device_observed': True, 'virtual_pcm_playback_completed': True,
                'host_audio_attached': False, 'wired_dhcp_observed': False,
                'wifi_radio_qualified': False, 'physical_audio_qualified': False, 'release_ready': False}
    if wired:
        for _ in range(60):
            rows = subprocess.check_output(['nmcli', '-t', '-f', 'DEVICE,TYPE,STATE', 'device'], text=True).splitlines()
            ethernet = [row.split(':')[0] for row in rows if ':ethernet:connected' in row]
            if len(ethernet) == 1:
                values = subprocess.check_output(['nmcli', '-g', 'IP4.ADDRESS,IP4.GATEWAY,IP4.DNS',
                                                 'device', 'show', ethernet[0]], text=True).splitlines()
                if values == ['192.0.2.15/24', '192.0.2.2', '192.0.2.3']:
                    break
            time.sleep(1)
        else:
            raise RuntimeError('restricted virtual Ethernet did not receive exact DHCP address/gateway/DNS configuration')
        observed['wired_dhcp_observed'] = True
        observed['virtual_network_scope'] = 'QEMU restricted user network 192.0.2.0/24; no forwarding'
    print('PHIOS_DESKTOP_SERVICES_OK:' + json.dumps(observed), flush=True)
    return observed
