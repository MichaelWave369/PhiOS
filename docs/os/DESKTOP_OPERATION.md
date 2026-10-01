# Experimental desktop operation

The candidate adds NetworkManager, a user PipeWire/WirePlumber audio stack,
Wayfire session locking and a non-root graphical PolicyKit authentication agent.
These are ordinary Linux desktop/administration paths. They do not create PhiOS
operator decisions, bindings or leases and do not authorize an agent or browser
to perform a general desktop effect. The restricted installed proof broker and
its UID separation remain described in LINUX_PROOF_WORKFLOW.md.

## Open, lock and end the session

| Action | Current path |
| --- | --- |
| PhiOS terminal | Super+Enter |
| Ordinary Linux terminal | Super+Alt+Enter |
| Application launcher | Super+Space |
| PhiShell window | Super+P |
| Lock current Wayfire session | Super+L or the `Lock PhiOS session` launcher entry |
| Network settings | Super+N or the `Network settings` launcher entry |
| Logout | From the ordinary desktop terminal, `loginctl terminate-session "$XDG_SESSION_ID"`; the supervised session target stops |
| Restart / shutdown | `systemctl reboot` / `systemctl poweroff`, under ordinary logind/PolicyKit permission |

`phios-lock` runs the packaged swaylock under the current non-root Wayfire
session. Wayfire's session-lock plugin supplies the protocol; swaylock waits for
the compositor's locked acknowledgement before its daemonizing caller returns.
Unlock uses the current account's ordinary PAM password. The volatile live
password is public `phios`; installed users keep the fresh password they chose.
Root/headless invocation is refused. Automatic idle/suspend locking is not
enabled by this candidate; lock explicitly before a suspend test with
`phios-lock && systemctl suspend`, then observe the actual resume/unlock.
Suspend remains a physical hardware gate. No protection
against arbitrary root or malicious same-UID administrator code is inferred.

For deliberate ordinary administration, use the terminal's normal
password-authenticated sudo account on an installed system. The live account
retains only its narrow maintenance sudo commands. The graphical PolicyKit agent
uses the distribution's existing policies and PAM; it changes no policy to make
the live user an administrator or to bypass an authentication request. Its startup
is tested separately from any future specific graphical administration operation.

## Wired and wireless configuration

NetworkManager owns wired and Wi-Fi address/DNS configuration; systemd-resolved
provides the resolver. A second networkd/iwd configuration owner is not enabled.
NetworkManager's HTTP connectivity URL polling is explicitly disabled. Connect
a wired cable and inspect `nmcli device status`. The terminal interface is
`nmtui`; account or system-wide changes may require normal administrator
authentication. A driver/radio must actually exist before Wi-Fi can work.

For a user-private Wi-Fi connection from the real desktop terminal:

```sh
nmcli device wifi list
nmcli --ask device wifi connect 'YOUR_SSID' private yes
```

Replace the SSID. `--ask` prompts for credentials instead of placing a password
in arguments/history. Connection files belong to NetworkManager's protected
system store with their selected user permissions; they are outside PhiOS's
data-only backup. The live overlay is volatile. Matched root checkpoints include
installed system configuration, so a deliberate root restore also restores its
network profiles. Record hardware/DHCP/DNS results without publishing personal
SSID, passwords, MAC/IP details or private connection files.

## User audio

`phios-audio.target` starts PipeWire, its PulseAudio compatibility server,
WirePlumber and their sockets as the desktop user. The session stops these units
on logout and starts them again on reauthentication. No root audio daemon or
automatic microphone recording is added. Inspect actual devices/streams with
`wpctl status`; adjust the observed default output with `wpctl`, for example:

```sh
wpctl set-volume @DEFAULT_AUDIO_SINK@ 50%
wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle
```

An unavailable output/microphone remains unavailable. Actual playback/capture,
device choice, mute/volume, HDMI/USB and suspend/resume on the named physical
machine are separate hardware tests.

## Candidate qualification scope

The new exact normal live gate attaches only a restricted QEMU user-network
Ethernet device on the documentation range `192.0.2.0/24`, without port forwarding,
and an emulated HDA device with a null audio backend. It checks the actual DHCP
address/server and the absence of an IPv4 gateway/DNS advertisement in this
restricted network, non-root service/process ownership and actual
PCM playback through the emulated ALSA sink. This does not test Internet DNS,
Wi-Fi association, physical speakers/microphones or a GPU driver.

The external QMP test invokes the actual Super+L binding, observes the lock,
tries a wrong password, then unlocks with the real public disposable PAM
credential. The installed lane repeats with the installer-created account's
fresh test password. Tests preserve lock/refusal/unlock screenshots, exact
source/ISO and serial evidence. The installed/update/recovery VM retains no NIC,
host disk, host audio device or shared folders.

The first normal attempt rejected the probe's incorrect expectation of gateway
and DNS DHCP options. libslirp deliberately omits both in restricted mode; the
corrected probe requires their absence and the actual lease/server. The failed
image/source, serial log and screenshot hashes are retained in
`evidence/desktop-attempts.json`. The installed signed QA lane passed its added
audio and PAM lock checks, but that does not qualify the failed normal image.

The complete added qualification is pending actual CI. Earlier passed ISO hashes remain
valid only for their recorded earlier scope; do not claim these new features
qualified until their actual new artifact receipt passes. Physical hardware,
final signed transition and distribution delivery remain open.

Upstream references: [Wayfire configuration](https://github.com/WayfireWM/wayfire/blob/master/wayfire.ini),
[swaylock](https://github.com/swaywm/swaylock),
[NetworkManager/nmcli](https://www.networkmanager.dev/docs/api/latest/nmcli.html),
[WirePlumber](https://pipewire.pages.freedesktop.org/wireplumber/daemon/running.html),
[libslirp DHCP implementation](https://qemu.googlesource.com/libslirp/+/refs/heads/master/src/bootp.c).
