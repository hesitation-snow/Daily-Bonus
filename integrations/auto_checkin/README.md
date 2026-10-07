# Auto_Checkin integration

Source: https://github.com/hesitation-snow/Auto_Checkin

Imported revision: `ee679fab00f3c17d7386ff0616b26211de0c5422`.

`glados_checkin.py` is adapted from the source's script and remains under
GPL-3.0 (see LICENSE). Modified on 2026-09-07 to report to stdout instead of
sending Telegram messages, make the display email optional, validate API
responses, avoid exposing response bodies or exception details, and treat
an already-completed check-in as such.

Daily-Bonus invokes this as a standalone process and includes the resulting
plain text in its existing notification. It requires only GLADOS_COOKIE;
GLADOS_EMAIL is optional. Set GLADOS_USER_AGENT to the exact browser identity
used to obtain the current Cookie when device verification is required.
The existing requests dependency is sufficient.

Modified on 2026-10-07 to stop randomizing browser identity, pass the configured
User-Agent, report actionable authentication errors, and recognize current
successful check-in messages. Updated Cookie/UA configuration is still needed;
the program cannot refresh the user's browser login.
