# Select the intended family member

For archive format 1, use explicit person UUIDs. Start with an initialized vault.
Create each identity separately, retaining the returned personId with your private
workflow notes:

```sh
helseark --vault /absolute/family person add --name 'Alex Synthetic' --json
helseark --vault /absolute/family person add --name 'Alex Synthetic' --json
```

These create distinct Patient histories even though names match. Resolve each ID
with `record --person UUID --resource Patient/UUID --json`, inspect the self-reported
identity, and select the intended UUID before intake. A filename or matching name
cannot assign a report. Use optional `--birth-date` and `--note` only for information
you explicitly supply; they are not mandatory identifiers or proof of identity.

Run `observations --person UUID --json` for that person only. An empty result means
no accepted matching Observations, not a negative clinical result. A resource from
another person's history must fail rather than crossing graphs. PERSON_NOT_FOUND
or RESOURCE_NOT_FOUND requires checking the explicit vault and UUID, never guessing
another person. No roster-search, patient-merge or person-erasure command is
available here. Folder access is controlled by the OS; use separate vaults when
access boundaries differ. See [privacy](../explanation/privacy-and-agent-boundaries.md).
