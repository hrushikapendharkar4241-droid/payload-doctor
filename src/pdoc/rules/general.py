"""Rules that apply before the format is known."""
from . import define

define("GEN-001", "any", "warning", "Byte-order mark (BOM) at start of file",
       "Many partner parsers treat the 3 invisible BOM bytes as data, so the first segment or tag is not recognised.",
       "File was saved as 'UTF-8 with BOM', usually by Excel, Notepad or a .NET export.",
       "Re-save as UTF-8 without BOM, or strip the first 3 bytes (sed -i '1s/^\\xEF\\xBB\\xBF//' file).")
define("GEN-002", "any", "error", "Unrecognised file format",
       "The receiver cannot route a file it cannot identify, so it is usually parked or rejected silently.",
       "Wrong file sent (e.g. a PDF or a report), a truncated transfer, or an unusual envelope.",
       "Open the file and confirm what it is; ask the partner to resend the intended X12/EDIFACT/XML/CSV payload.")
define("GEN-003", "any", "error", "File is empty",
       "There is nothing to process; downstream systems may report the transaction as received but blank.",
       "Transfer started before the source file was fully written, or the export job produced no data.",
       "Check the partner's export job and file size on the SFTP server; ask for a resend after the write completes.")
define("GEN-004", "any", "error", "File is not valid UTF-8 text",
       "Characters such as accented names or symbols become garbage, and strict parsers stop at the first bad byte.",
       "File exported in a legacy encoding (Windows-1252, ISO-8859-1) or corrupted in transfer (FTP ASCII mode).",
       "Ask the partner to export as UTF-8, or convert with: iconv -f WINDOWS-1252 -t UTF-8 in > out.")
