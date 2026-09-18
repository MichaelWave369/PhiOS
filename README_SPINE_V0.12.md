# PhiOS Spine v0.12 - Local TCP Listener World Verifier

Spine v0.12 lets the Reality Gate verify whether one exact local TCP port is currently in LISTEN state without sending network traffic.

It requires:

`reality.verify`

and:

`reality.local_socket.read`

The point-in-time result becomes content-addressed JSON evidence.

See `docs/PHIOS_SPINE_V0.12_LOCAL_TCP_VERIFIER.md`.
