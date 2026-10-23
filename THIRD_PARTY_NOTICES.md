# Third-party notices

The following modules are derived from the locally provided Pyromind/OpenHands project.
Copyright (c) 2026 OpenHands contributors. Licensed under MIT; see LICENSE.
Only import namespaces were changed in these modules. Source hashes are recorded below.
No platform SDK, credentials, or raw episode dataset is included in the extension package.

The README comparison image includes frames from the copper-plate recording supplied for this demonstration. Check the source owner's terms before redistributing that image; the raw recording and joint files are excluded from Git by `.gitignore`.

- `openhands-embodied-runtime/openhands_embodied_runtime/models.py` — SHA256 `ce5fc8d911669b428d3b5340a3d759dced1773e4f71db72610ee0ded5d61ae70`
- `openhands-embodied-runtime/openhands_embodied_runtime/timestamps.py` — SHA256 `af9252095047ac4d54d04b5a009e5f41aaf2bb17dc6e97fad334ca981d06c68c`
- `openhands-embodied-runtime/openhands_embodied_runtime/adapters.py` — SHA256 `f1c5daa310ddf3d5762b2994a6c134455096a81478be7c6f2838008dd266312d`
- `openhands-embodied-runtime/openhands_embodied_runtime/planning.py` — SHA256 `635c0149d83ff414039ebd3cdddc870a8b2705e7111881f565145240f743d73e`
- `openhands-embodied-runtime/openhands_embodied_runtime/lerobot_v21.py` — SHA256 `d9742c122f33b4d34db8ccbf8ce9bb3be8c7bd8555e5a4c1121d8718f4853e3d`
- `openhands-embodied-runtime/openhands_embodied_runtime/reporting.py` — SHA256 `3e7571c8ca25c87f14baa5a6f95d52a39870f083fc5dd538f55655c569b7852b`

## Adapted domain tests

- `tests/tools/embodied_data/conftest.py` — SHA256 `c99aff73669810b65ffaa6d9e6e3e3f93cbeaffee18aba694ad6aed608083ee9`; imports and harness adapted, platform cases excluded.
- `tests/tools/embodied_data/test_embodied_runtime.py` — SHA256 `4574956460024884530c96e1a83b3161839c4c83b5c2efbffc0a24a2ca46565d`; imports and harness adapted, platform cases excluded.
