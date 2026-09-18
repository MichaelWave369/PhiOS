# PhiOS Spine v0.4 - Bounded File Acquisition

Spine v0.4 lets SOMA acquire bounded local text files through an explicit source-root contract.

Local file -> bounded acquisition -> native evidence -> PerceptionReceipt

The adapter blocks traversal, absolute paths, symlink sources, unsupported file types, and oversized inputs. Invalid UTF-8 is preserved as native evidence and quarantined rather than guessed.

See docs/PHIOS_SPINE_V0.4_FILE_ACQUISITION.md.
