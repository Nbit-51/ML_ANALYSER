# License decision

On October 26, 2026, the owner explicitly approved switching the current release
to **GNU AGPLv3** and continuing the hackathon submission. This supersedes the earlier
October 25 decision to keep permission-required terms for the current release.

The root [LICENSE](../LICENSE) contains the unmodified GNU AGPL version 3 text.
[NOTICE.md](../NOTICE.md) applies AGPL-3.0-only to original ML Analyser code,
documentation and assets, states the copyright notice, and preserves third-party terms.

Because the landing page uses GSAP's separately licensed animation library, NOTICE.md
includes a narrow additional permission under AGPL section 7 to link or combine with
the pinned GSAP 3.13.0 and ScrollTrigger. This does not relicense GSAP or grant rights
that its own terms do not provide. Three.js retains its MIT license.

AGPL permits use, copying, modification, redistribution and commercial use subject to
its conditions. It does not require the author's permission for every modification.
Modified network-accessible versions must offer their corresponding source as required
by section 13. The license does not promise free inference credits, unlimited hosting,
support or perpetual service availability.

The previous custom license remains part of Git history; it no longer describes the
license offered for the current release. No third-party source or license header was
changed as part of this decision.

References: [GNU AGPLv3](https://www.gnu.org/licenses/agpl-3.0.html),
[OSI AGPL-3.0 entry](https://opensource.org/license/agpl-v3), and the
[event rules](https://nebiusglobalaihackathon.devpost.com/rules).
