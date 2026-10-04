# Sourced by phios-session before Wayfire starts. No real-hardware default.
phios_virtualbox_cursor_compat() {
    local virtualization device vendor product class
    virtualization=$(systemd-detect-virt --vm 2>/dev/null) || return 0
    [[ $virtualization == oracle ]] || return 0
    # VMSVGA shares VMware's PCI ID; that ID alone must not select this fix.
    for device in "${1:-/sys/bus/pci/devices}"/*; do
        [[ -r "$device/vendor" && -r "$device/device" && -r "$device/class" ]] || continue
        read -r vendor < "$device/vendor" || continue
        read -r product < "$device/device" || continue
        read -r class < "$device/class" || continue
        if [[ $vendor == 0x15ad && $product == 0x0405 && $class == 0x03???? ]]; then
            export WLR_NO_HARDWARE_CURSORS=1
            return 0
        fi
    done
    return 0
}
