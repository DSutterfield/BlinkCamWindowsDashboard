# Local Modifications

## 2026-07-29

### Added

- `capability_probe.py`
  - Inspects discovered Blink systems and devices.
  - Produces read-only JSON and text capability reports.

- `capability_matrix.py`
  - Converts a capability-probe JSON report into compact CSV and text matrices.
  - Does not contact Blink or issue device commands.

### Modified

- `first_login.py`
  - Added validation for missing credentials and 2FA codes.
  - Completes any required 2FA before continuing setup.
  - Verifies Blink availability and camera discovery.
  - Saves credentials only after successful setup.

- `.gitignore`
  - Ignores virtual environments, Visual Studio local files, Python caches,
    Blink credential files, generated reports, and `*.pyproj.user` files.

### Documentation

- Added developer architecture notes and project change history.