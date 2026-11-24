"""Rules for AS2 certificates and MDN (receipt) messages."""
from . import define

define("AS2-001", "as2", "error", "Certificate has expired",
       "AS2 messages signed or encrypted with an expired certificate are rejected, and MDNs stop arriving.",
       "Certificate renewal was not exchanged with the trading partner before the expiry date.",
       "Generate or obtain a new certificate, exchange it with the partner, update both AS2 profiles, then resend failed messages.")
define("AS2-002", "as2", "warning", "Certificate expires within 30 days",
       "Partners often need weeks to schedule a certificate change; an expiry mid-week stops all traffic.",
       "Renewal not yet planned.",
       "Plan the certificate exchange now and agree a switch-over date with the partner.")
define("AS2-003", "as2", "warning", "Weak key size",
       "RSA keys under 2048 bits are rejected by many current AS2 gateways.",
       "Old certificate generated with a 1024-bit key.",
       "Issue a new certificate with an RSA key of at least 2048 bits.")
define("AS2-004", "as2", "warning", "Certificate signed with SHA-1",
       "SHA-1 is deprecated; some partners refuse it.",
       "Legacy certificate authority or old tooling.",
       "Reissue the certificate with SHA-256.")
define("AS2-005", "as2", "info", "Self-signed certificate",
       "Common for AS2, but the partner must install this exact certificate; a renewal needs a new exchange.",
       "Certificate generated locally rather than by a certificate authority.",
       "No action needed if the partner has the certificate installed; track its expiry.")
define("AS2-006", "as2", "error", "Certificate not yet valid",
       "Messages are rejected until the start date, often because of a time zone or clock issue.",
       "Certificate installed before its validity start, or the server clock is wrong.",
       "Check the server clock and the certificate's notBefore date.")
define("AS2-007", "as2", "error", "MDN reports the message failed",
       "The partner received the message but did not process it; from their side it does not exist.",
       "Decryption or signature failure (certificate mismatch), or the payload failed their checks.",
       "Read the disposition modifier: 'decryption-failed' or 'authentication-failed' means a certificate mismatch; fix and resend.")
define("AS2-008", "as2", "warning", "MDN could not be read",
       "Without a readable receipt there is no proof of delivery.",
       "Partner sent an unsigned or non-standard MDN, or the file is not an MDN.",
       "Ask the partner to check their MDN settings (signed, synchronous or asynchronous as agreed).")
