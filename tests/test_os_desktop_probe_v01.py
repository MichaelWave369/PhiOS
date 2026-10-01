from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location('desktop_probe', REPO / 'packaging/linux/tests/desktop_probe.py')
assert SPEC is not None and SPEC.loader is not None
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def captured_network() -> dict:
    return json.loads((REPO / 'tests/fixtures/os_desktop/restricted-nmcli.json').read_text())


def test_actual_restricted_nmcli_capture_is_a_dhcp_lease():
    assert probe.restricted_dhcp_lease(captured_network())


def test_line_separated_options_retain_the_same_lease():
    network = captured_network()
    network['DHCP4.OPTION'] = network['DHCP4.OPTION'][0].split(' | ')
    assert probe.restricted_dhcp_lease(network)


@pytest.mark.parametrize('change', ['wrong_address', 'default_gateway', 'dns_advertised',
                                   'wrong_server', 'duplicate_server', 'no_dhcp'])
def test_static_ambiguous_or_forwarding_configuration_never_qualifies(change):
    network = copy.deepcopy(captured_network())
    if change == 'wrong_address':
        network['IP4.ADDRESS'] = ['192.0.2.16/24']
    elif change == 'default_gateway':
        network['IP4.GATEWAY'] = ['192.0.2.2']
    elif change == 'dns_advertised':
        network['IP4.DNS'] = ['192.0.2.3']
    elif change == 'wrong_server':
        network['DHCP4.OPTION'][0] = network['DHCP4.OPTION'][0].replace(
            'dhcp_server_identifier = 192.0.2.2', 'dhcp_server_identifier = 192.0.2.9')
    elif change == 'duplicate_server':
        network['DHCP4.OPTION'][0] += ' | dhcp_server_identifier = 192.0.2.2'
    else:
        network['DHCP4.OPTION'] = []
    assert not probe.restricted_dhcp_lease(network)


def test_manager_display_observation_parses_quoted_values_and_drops_unrelated_keys():
    wire = "WAYLAND_DISPLAY=wayland-1\nXDG_RUNTIME_DIR='/run/user/1000'\nXDG_CURRENT_DESKTOP=Wayfire\nDISPLAY=\nPRIVATE_UNRELATED_VALUE=discarded\n"
    assert probe.session_display_environment(wire) == {
        'WAYLAND_DISPLAY': 'wayland-1', 'XDG_RUNTIME_DIR': '/run/user/1000',
        'XDG_CURRENT_DESKTOP': 'Wayfire', 'DISPLAY': '',
    }


@pytest.mark.parametrize('change', ['absent_display', 'absent_runtime', 'empty_runtime', 'duplicate_display', 'split_value'])
def test_incomplete_or_ambiguous_manager_display_environment_never_qualifies(change):
    wire = "WAYLAND_DISPLAY=wayland-1\nXDG_RUNTIME_DIR=/run/user/1000\nXDG_CURRENT_DESKTOP=Wayfire\nDISPLAY=\n"
    if change == 'absent_display':
        wire = wire.replace('WAYLAND_DISPLAY=wayland-1\n', '')
    elif change == 'absent_runtime':
        wire = wire.replace('XDG_RUNTIME_DIR=/run/user/1000\n', '')
    elif change == 'empty_runtime':
        wire = wire.replace('XDG_RUNTIME_DIR=/run/user/1000', 'XDG_RUNTIME_DIR=')
    elif change == 'duplicate_display':
        wire += 'WAYLAND_DISPLAY=wayland-2\n'
    else:
        wire = wire.replace('WAYLAND_DISPLAY=wayland-1', 'WAYLAND_DISPLAY=wayland-1 unexpected')
    with pytest.raises(ValueError):
        probe.session_display_environment(wire)
