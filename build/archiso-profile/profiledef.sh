#!/usr/bin/env bash
iso_name="phios"
iso_label="PHIOS_$(date +%Y%m)"
iso_publisher="PHI369 Labs / Parallax"
iso_application="PhiOS Sovereign Desktop"
iso_version="0.7.0"
install_dir="arch"
bootstrap_tarball_compression=(zstd -c -T0 --long -)
file_permissions=(
  ["/etc/skel/.bashrc"]="0:0:644"
)
