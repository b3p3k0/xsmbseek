# Probe Ransomware Indicator Reference

xsmbseek’s probe runner now surfaces “bad” hosts when cached directory listings contain ransom-note filenames that are widely associated with known ransomware families. This page is the public hand‑off for defenders who want to understand **why these patterns matter, how the GUI interprets them, and how to extend the list safely**.

## Why we match ransom-note filenames

* **Scenario**: An analyst runs a lightweight probe against an anonymous SMB share. Even without downloading files, we can see top-level filenames (e.g., `!want_to_cry.txt`). Those names often uniquely identify ransomware incidents that already compromised the host.
* **Goal**: Flag the server as a “lost cause” (✖) so analysts don’t waste time, and capture an audit trail explaining which threat family was observed.
* **Persistence**: Matches are written to `SettingsManager.probe.status_by_ip` and cached under `~/.smbseek/probes/<ip>.json`, so the server list stays red across sessions.

## Using and extending the indicator list

1. Indicators live in the backend config (`smbseek/conf/config.json → security.ransomware_indicators`). Editing that array immediately updates future probe runs—no code changes required.
2. Keep entries short (wildcards `*` and `?` are supported) and document any new additions in this file or internal runbooks.
3. Treat each entry as a high-signal ransom note; avoid generic names like `readme.txt` that will generate noise.
4. If you need to disable matching temporarily, remove the entry from the config and clear cached probes with `xsmbseek --clear-probes`.

## Indicator catalogue

| Indicator pattern | Associated family / behavior | CVE or reference |
| --- | --- | --- |
| `!want_to_cry.txt` | WannaCry / WantToCry ransomware leaves this note after encrypting files and appending `.want_to_cry`. | EternalBlue exploit (CVE-2017-0144) was reused by WannaCry to spread over SMBv1. citeturn1search0turn14search0 |
| `!0XXX_DECRYPTION_README.TXT` | 0xxx ransomware (Hunt family) encrypts NAS shares, appends `.0xxx`, and drops this ransom note. | Public analyses describe the note contents and $300 BTC demand. citeturn6search0turn6search4 |
| `HOW_TO_DECRYPT_FILES.txt` | Hive RaaS (and its Hunters International successor) leaves this file, often alongside `README_HIVE.html`, targeting healthcare and leveraging Fortinet/Microsoft Exchange CVEs. | Hive crews have exploited CVE-2020-12812 (FortiOS SSL-VPN) and CVE-2021-31207/34473/34523 (Exchange). citeturn13search1 |
| `DECRYPT_INSTRUCTIONS.txt` | Vanguard, Wizard, and Play ransomware variants all ship ransom notes with this exact name, generally asking for Bitcoin via email. | Observed in Vanguard (`DECRYPT_INSTRUCTIONS.txt` on disk) and Wizard ($100 demand). citeturn8search1turn8search7 |
| `_DECRYPT_INFO_.txt` | Maktub Locker drops HTML ransom notes named `_DECRYPT_INFO_<random>.html` in every folder following widespread email phishing. | Detailed removal write-ups confirm the filename convention. citeturn3search0 |
| `README_FOR_DECRYPT.txt` | Muhstik/QNAPCrypt ransomware families focus on NAS devices and leave this note with Tor/Bitcoin instructions. | NAS-focused threat described in multiple incident reports. citeturn10view0 |
| `+readme-warning+.txt` | STOP/Djvu ransomware standard note; shows up with countless extensions (.djvu, .nasoh, etc.) on consumer endpoints. | Threat intel trackers list this filename as the primary STOP/Djvu indicator. citeturn1search1turn1search10 |
| `cAcTuS.readme.txt` | CACTUS ransomware double-extortion crew names both the malware and the ransom note after the cactus motif and commonly breaches VPN appliances. | Campaigns frequently exploit appliances such as Ivanti/Qlik; reports mention CVE-2023-38035 in Fortinet VPNs. citeturn2search0turn2search8 |
| `README-ID-*.txt` | Whole / Keylock (Keylocker) enterprise ransomware variants append `.whole`/`.keylock` and leave ID-tagged readme files threatening leaks. | Desktop wallpaper + `README-ID-[victim].txt` instructions documented by responders. citeturn4search0turn9view0 |
| `README_*.txt` | Keylock/Keylocker also uses generic `README_id-<user>.txt` notes; matching the wildcard catches older builds. | Same family as above, but some samples omit the hyphen. citeturn9view0 |
| `Readme.*.txt` | macOS KeRanger ransomware creates `readme_to_decrypt.txt` (and similar capitalization variants) in every folder after encrypting files via RSA/AES. | KeRanger analysis confirms the filename. citeturn11view0 |
| `HOW_TO_DECYPHER_FILES.txt` | Rastar, Thanos, Energy, and other builders reuse this note for `.rastar`, `.locked`, and `.energy` extensions. | Multiple reverse-engineering write-ups show the shared filename and Telegram/email contact workflow. citeturn5search0turn5search6 |

### Reading the table

* **Indicator pattern**: Exact string or wildcard we search for in probe output.
* **Associated family**: The best-known ransomware family that drops the file. Not exclusive—copycats reuse notes.
* **CVE/reference**: Either a documented CVE exploited by that family or a public report confirming the filename. If no CVE is listed, the reference explains the behavior.

## Analyst workflow tips

1. **Before triage**: Run probes against suspicious SMB hosts. If a ✖ appears, open the Server Details dialog to review the “Indicators Detected” block and record the evidence in your case notes.
2. **Remediation guidance**: Hosts already showing these ransom notes should be isolated and reimaged; the presence of the note implies a prior compromise, not just exposure.
3. **Updating indicators**: When you encounter a new ransom note filename:
   * Validate it (screenshot/log from the affected share).
   * Add it to `security.ransomware_indicators`, keeping the naming concise.
   * Submit a short PR updating this doc with the family name and public reference (CVE or article).

By keeping this list curated and cited, we help downstream defenders understand *why* xsmbseek paints a host red instead of treating it as a false positive.
