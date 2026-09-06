# Security policy

Please do not open public issues for suspected vulnerabilities that could put users at risk. Report security issues privately to the Zyvor AI Labs security contact listed on https://zyvor.dev and include affected version, reproduction steps and impact.

Supported line: `0.1.x` receives security fixes while it is the current minor release.

KubeFlight's bundled service account never requires Secret read access. If your deployment adds broader permissions, that is outside the default security model and should be reviewed separately.
