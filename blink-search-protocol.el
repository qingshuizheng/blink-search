;;; blink-search-protocol.el --- The Elisp/Python protocol of blink-search  -*- lexical-binding: t; -*-

;; Filename: blink-search-protocol.el
;; Description: The Elisp/Python protocol of blink-search
;; Author: Andy Stewart <lazycat.manatee@gmail.com>
;; Maintainer: Andy Stewart <lazycat.manatee@gmail.com>
;; Copyright (C) 2022, Andy Stewart, all rights reserved.
;; Version: 0.1
;; URL: https://github.com/manateelazycat/blink-search
;; Keywords: tools
;; Compatibility: emacs-version >= 28
;;
;; This file is NOT part of GNU Emacs

;;; License
;;
;; This program is free software; you can redistribute it and/or modify
;; it under the terms of the GNU General Public License as published by
;; the Free Software Foundation; either version 3, or (at your option)
;; any later version.

;; This program is distributed in the hope that it will be useful,
;; but WITHOUT ANY WARRANTY; without even the implied warranty of
;; MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
;; GNU General Public License for more details.

;; You should have received a copy of the GNU General Public License
;; along with this program; see the file COPYING.  If not, write to
;; the Free Software Foundation, Inc., 51 Franklin Street, Fifth
;; Floor, Boston, MA 02110-1301, USA.

;;; Commentary:
;;
;; blink-search is one repository with two runtimes: this Elisp package and
;; the Python search process it spawns.  They talk over EPC, and nothing in
;; either language stops one half from being renamed without the other, so
;; the names they agree on live here, in one file, as data.
;;
;; `blink-search-protocol-version' is the handshake value: the Python half
;; declares the same number in core/protocol.py, and scripts/check-protocol.py
;; fails the build when the two ever drift apart.  Bump both whenever a
;; method is added, removed or given a different argument shape.
;;
;; The method tables below are what the Python half calls *into* Emacs
;; (`blink-search-protocol-emacs-methods') and what Emacs calls into Python
;; (`blink-search-protocol-python-methods').  They are documentation as much
;; as data -- the code that implements them is in blink-search-process.el
;; (the callbacks) and in the Elisp callers of `blink-search-call-async'
;; (the requests) -- but keeping them in one place is what makes a protocol
;; change reviewable in a single diff.

;;; Code:

(defconst blink-search-protocol-version "1"
  "Version of the protocol spoken between blink-search's two halves.

The Python half declares the same value as PROTOCOL_VERSION in
core/protocol.py, and scripts/check-protocol.py compares the two.")


;;
;; Emacs side: methods the Python process may call.
;;

(defconst blink-search-protocol-emacs-methods
  '((eval-in-emacs . "Evaluate one printed Elisp form, return nil")
    (get-emacs-var . "Return (VALUE IS-BOOLEAN) for one variable name")
    (get-emacs-vars . "Return the above, once per requested variable name")
    (blink-search-open-file . "Open a file or directory at point's origin")
    (blink-search-select-start-buffer . "Return to the buffer blink-search started from")
    (blink-search-continue-search . "Continue searching inside one directory")
    (blink-search-open-browser . "Open a URL in the configured browser")
    (blink-search-browser-function . "Obsolete alias of the above, kept for old configs")
    (blink-search-update-items . "Replace the rendered candidate and backend rows")
    (blink-search-imenu-do . "Jump to an imenu candidate")
    (blink-search-current-buffer-do . "Jump to a line of the current buffer")
    (blink-search-current-buffer-preview . "Preview a line of the current buffer")
    (blink-search-grep-file-do . "Jump to a grep match")
    (blink-search-grep-file-preview . "Preview a grep match")
    (blink-search-grep-file-clean . "Drop the grep preview buffers")
    (blink-search-pdf-do . "Jump to a match inside a PDF")
    (blink-search-pdf-preview . "Preview a match inside a PDF")
    (blink-search-pdf-clean . "Drop the PDF preview buffers")
    (blink-search-grep-pdf-do . "Jump to a match found by rga")
    (blink-search-grep-pdf-preview . "Preview a match found by rga")
    (blink-search-grep-pdf-clean . "Drop the rga preview buffers")
    (kill-new . "Put a string into the kill ring")
    (message . "Report a string in the echo area"))
  "Methods the Python process calls on the Emacs side.

Each element is a cons of the EPC method name and a one line
description.  See the `blink-search--eval-in-emacs-func' callback in
blink-search-process.el for how they are dispatched.")


;;
;; Python side: methods Emacs calls.
;;

(defconst blink-search-protocol-python-methods
  '((search . "Start a search: INPUT ROW-NUMBER BACKEND-LIST")
    (clean . "Drop the candidates of the previous search")
    (cleanup . "Shut the Python process down")
    (search_do . "Run the default action of a candidate")
    (search_copy . "Copy a candidate into the kill ring")
    (search_parent . "Go to the parent of a candidate")
    (search_continue . "Search inside the directory of a candidate")
    (select_candidate_item . "Preview the selected candidate")
    (select_next_candidate_item . "Move the candidate selection down")
    (select_prev_candidate_item . "Move the candidate selection up")
    (select_next_backend_item . "Move the backend selection down")
    (select_prev_backend_item . "Move the backend selection up")
    (select_next_candidate_group . "Jump to the next backend group")
    (select_prev_candidate_group . "Jump to the previous backend group")
    (search_init_current_buffer . "Hand the current buffer to a backend")
    (search_sort_buffer_list_update . "Replace the buffer order a backend sorts by"))
  "Methods Emacs calls on the Python side through `blink-search-call-async'.

Each element is a cons of the EPC method name and a one line
description of its arguments.")

;; The update methods are built from the backend modules at start up: the
;; class Xxx in backend/search_yyy.py is reached as `search_yyy_update'.  They
;; are listed here as data because they are part of the protocol, and
;; scripts/check-protocol.py fails the build when a backend is renamed without
;; its Elisp caller, or the other way around.
(defconst blink-search-protocol-backend-update-methods
  '(search_buffer_list_update
    search_common_directory_update
    search_current_buffer_update
    search_eaf_browser_history_update
    search_elisp_symbol_update
    search_find_file_update
    search_google_suggest_update
    search_grep_file_update
    search_grep_pdf_update
    search_history_update
    search_imenu_update
    search_key_value_store_update
    search_pdf_update
    search_recent_file_update)
  "Update methods of the registered backends, one per backend module.")

(provide 'blink-search-protocol)

;;; blink-search-protocol.el ends here
