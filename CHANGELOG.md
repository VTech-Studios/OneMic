# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-09-30

First release.

### Added

- Named virtual mics, listed in call apps as `<name> (OneMic)`, saved and
  switchable, with create, copy, rename and delete.
- Up to eight inputs per mic from microphones, applications, or anything a
  speaker is playing.
- Volume, mute and solo for each input through its own gain stage, plus a
  master volume and mute for the mix.
- Smoothly scrolling waveforms and DAW-style level meters for each visible
  input and for the mix, on a decibel scale, coloured ice blue, yellow when
  hot and red where clipped, with a held peak in dBFS.
  Inputs are metered before going live too, exactly as they will be sent.
- Per-input 100 Hz low-cut and noise gate, with the gate threshold dragged
  on the input's meter. The gate uses lsp-plugins when installed.
- Listen, to hear exactly what the mic sends through the default output,
  or the processed inputs before going live, blocked when it would feed
  back.
- Auto-relink: missing links are restored within a second when a device or
  application appears.
- A small always-on-top window that snaps to screen corners and remembers
  its corner, screen and size.
- A choice on closing while live: keep the mic running for the call, or stop
  it. A mic left live is picked up again on the next start.

[Unreleased]: https://github.com/LukeMcCann/onemic/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/LukeMcCann/onemic/releases/tag/v1.0.0
