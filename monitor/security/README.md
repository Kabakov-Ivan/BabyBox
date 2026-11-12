# PIN storage

The runtime PIN file is created on the BabyBox at:
`/home/admin/BabyBox/monitor/security/pin.jsonl`.

Only a PBKDF2-SHA256 hash and a random salt are written. The PIN itself is
never stored in this repository. Keep this directory free of runtime secrets.

Owner profile images and JSONL records are stored under
`/home/admin/Save_BabyBox/profile`. The selected lullaby record is stored under
`/home/admin/Save_BabyBox/sounds`.

The web panel lock is a local screen lock for the dashboard UI. It does not
replace network authentication for the existing device API.
