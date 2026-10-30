# pobyt-tracker snapshots

Raw datasets from [pobyt-tracker](https://pobyt-tracker.pages.dev/), the source of the imported cases (`cases.source = 'pobytrack'`).

Each file holds the dataset as published on the date in its name, reformatted to one case per line. It has no names or contacts: region, basis, filing method, milestone dates and the Telegram post number that identifies a case.

Re-import a snapshot with `python -m czekachiko.importers.pobytrack --file data/pobytrack/<date>.json [--dry-run]`.
