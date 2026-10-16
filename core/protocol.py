#!/usr/bin/env python3
"""The Elisp/Python protocol of blink-search, as data.

blink-search is one repository with two runtimes: the Elisp package and this
Python search process.  They talk over EPC, and nothing in either language
stops one half from being renamed without the other, so the names they agree
on live here, in one module.

PROTOCOL_VERSION is the handshake value: the Elisp half declares the same
number as `blink-search-protocol-version' in blink-search-protocol.el, and
scripts/check-protocol.py fails the build when the two ever drift apart.
Bump both whenever a method is added, removed or given a different argument
shape.
"""

from __future__ import annotations

PROTOCOL_VERSION = "1"

#: EPC methods this process calls on the Emacs side.  They are implemented by
#: blink-search-process.el and its callers; the table exists so that a rename
#: on either side shows up as a one line diff.
EMACS_METHODS = (
    "eval-in-emacs",
    "get-emacs-var",
    "get-emacs-vars",
    "blink-search-open-file",
    "blink-search-open-browser",
    "blink-search-browser-function",
    "blink-search-select-start-buffer",
    "blink-search-continue-search",
    "blink-search-update-items",
    "blink-search-imenu-do",
    "blink-search-current-buffer-do",
    "blink-search-current-buffer-preview",
    "blink-search-grep-file-do",
    "blink-search-grep-file-preview",
    "blink-search-grep-file-clean",
    "blink-search-pdf-do",
    "blink-search-pdf-preview",
    "blink-search-pdf-clean",
    "blink-search-grep-pdf-do",
    "blink-search-grep-pdf-preview",
    "blink-search-grep-pdf-clean",
    "kill-new",
    "message",
)

#: Fields of the message a backend puts on the message queue when its
#: candidates changed.
MESSAGE_UPDATE_BACKEND_ITEMS = "update_backend_items"

#: Backend names, in the order the menu shows them in by default.  PDF is
#: inserted into this list at search time when the start buffer is a pdf and
#: rga is installed; see core.navigator.
DEFAULT_BACKENDS = (
    "History",
    "Buffer List",
    "Common Directory",
    "Find File",
    "Recent File",
    "EAF Browser",
    "IMenu",
    "Elisp Symbol",
    "Google Suggest",
    "Key Value",
)

#: The backend that only joins the list when rga is available and the buffer
#: the search started from is a pdf file.
PDF_BACKEND = "PDF"
