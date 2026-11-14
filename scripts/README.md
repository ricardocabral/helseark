# Pinned validator acquisition

`acquire_validator.py DESTINATION [--linux-jre]` is an explicit maintainer
download step. Use a new destination on a network-enabled machine. It does not
run during application use. Every artifact must match the existing exact byte
count and SHA-256; a transfer error or mismatch exits nonzero without retries.

The destination's `acquisition.jsonl` journals each attempted artifact, including
its identity, source and final URL, HTTP status, declared Content-Length when
numeric, expected/observed bytes and SHA-256, timestamps and result. URLs omit
credentials, query strings and fragments. No response bodies, arbitrary headers
or exception messages are retained. Successful downloads remain in the directory;
failed temporary binaries are removed. Preserve the journal and job log.

Each transfer reads at most the expected size plus one byte, in bounded chunks.
`digestScope` distinguishes a body read to EOF, a prefix stopped at that limit,
and a partial transfer interrupted by an error. A prefix/partial digest is not
a checksum of the whole remote artifact. HTTP/network exceptions retain their
type; HTTP errors retain their status. These diagnostics do not prove why a
server returned particular bytes.

CI uploads this small journal together with any synthetic corpus reports, even
when acquisition failed before the corpus started. It does not upload the JAR,
JRE or package archives. Missing all evidence remains an upload error, and the
original acquisition/corpus failure remains a job failure.

On mismatch, compare the identified artifact with its official release metadata,
published digest and endpoint, then with the preserved qualified reference.
Do not replace a pin with the observed digest or assume a retry proves a transient
cause. Repeated bounded samples and archive member comparisons may be needed to
distinguish transfer failure from changed packaging. Changed runtime content
requires independently verifiable provenance and real requalification. No
automatic normalization, alternate endpoint or runtime fetch is implemented.
