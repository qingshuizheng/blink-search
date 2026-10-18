;;; blink-search-state.el --- Options and state of blink-search  -*- lexical-binding: t; -*-

;; Filename: blink-search-state.el
;; Description: Options and state of blink-search
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
;; Every option and every piece of session state of blink-search lives in this
;; file, so that the modules which read them do not have to guess where a
;; variable comes from, and so that a byte compiled file can never see a
;; variable that is defined in a file it loads after itself (the bug that made
;; the upstream `eval-and-compile' call fail).
;;
;; Nothing here is behaviour: the process, the rendering and the navigation all
;; live in their own file and only read these variables.

;;; Code:

(declare-function eaf-open-browser "eaf" (url &optional arg))

(defgroup blink-search nil
  "Blink-Search: search many sources in the blink of an eye."
  :group 'applications)

;;
;; Options.
;;

(defcustom blink-search-enable-posframe nil
  "Render the search results in a popup window instead of a split window.
The popup needs posframe, see `blink-search-posframe-width-ratio' and
`blink-search-posframe-height-ratio' for its size."
  :type 'boolean
  :group 'blink-search)

(defcustom blink-search-posframe-width-ratio 0.6
  "Width of the posframe, as a ratio of the width of the Emacs frame."
  :type 'number
  :group 'blink-search)

(defcustom blink-search-posframe-height-ratio 0.6
  "Height of the posframe, as a ratio of the height of the Emacs frame."
  :type 'number
  :group 'blink-search)

(defcustom blink-search-posframe-standalone nil
  "If non-nil, display the posframe as a standalone frame.
A standalone frame has no parent frame, so it can be moved outside of
the Emacs window by the window manager."
  :type 'boolean
  :group 'blink-search)

(defcustom blink-search-enable-icon t
  "Show an icon in front of every candidate."
  :type 'boolean
  :group 'blink-search)

(defcustom blink-search-common-directory '(("HOME" "~/"))
  "Common directory to search and open.
Each element is a list of the name shown in the menu and the path it
stands for."
  :type '(repeat (list string string))
  :group 'blink-search)

(defcustom blink-search-history-path
  (expand-file-name (concat user-emacs-directory (file-name-as-directory "blink-search") "history.txt"))
  "The path to store search history."
  :type 'string
  :group 'blink-search)

(defcustom blink-search-db-path (expand-file-name "blink-search.db" user-emacs-directory)
  "Key Value store database path."
  :type 'string
  :group 'blink-search)

(defcustom blink-search-db-table "kvstore"
  "Key Value store table."
  :type 'string
  :group 'blink-search)

(defcustom blink-search-name "*blink-search*"
  "Name of the Blink-Search buffer that holds the Python process output."
  :type 'string
  :group 'blink-search)

(defcustom blink-search-python-command
  (if (memq system-type '(cygwin windows-nt ms-dos)) "python.exe" "python3")
  "The Python interpreter used to run blink_search.py."
  :type 'string
  :group 'blink-search)

(defcustom blink-search-enable-debug nil
  "Start the Python process under gdb and print its backtrace.
Turn this on when blink-search makes Emacs crash: the `*blink-search*'
buffer then holds the backtrace to attach to the bug report."
  :type 'boolean
  :group 'blink-search)

(defcustom blink-search-enable-log nil
  "Print every log message of the Python half in `*blink-search*'.
The buffer always shows the message headers; this option turns on the
verbose logging behind them."
  :type 'boolean
  :group 'blink-search)

(defcustom blink-search-flash-line-delay .3
  "How many seconds to flash `blink-search-font-lock-flash' after navigation.
Setting this to nil or 0 will turn off the indicator."
  :type 'number
  :group 'blink-search)

(defcustom blink-search-search-backends nil
  "Default backends for blink-search.
A list of backend names as the Python half spells them, or nil for all
backends defined in Python.  For example, set this option to
`(\"Buffer List\" \"Find File\")' to search only those two."
  :type '(repeat string)
  :group 'blink-search)

(defcustom blink-search-browser-function #'eaf-open-browser
  "The function used to open a web page for a google suggestion.
It is called with the URL as its only argument, through
`blink-search-open-browser'."
  :type 'function
  :group 'blink-search)

(defcustom blink-search-file-manager 'eaf-file-manager
  "File-manager to open file or directory."
  :type 'symbol
  :options '(eaf-file-manager dired)
  :group 'blink-search)

(defcustom blink-search-elisp-symbol-update-idle 5
  "The idle seconds to update elisp symbols."
  :type 'float
  :group 'blink-search)

(defcustom blink-search-recent-file-update-idle 4
  "The idle seconds to update recent files."
  :type 'float
  :group 'blink-search)

(defcustom blink-search-grep-pdf-search-paths nil
  "Paths to search for pdf files."
  :type '(repeat string)
  :group 'blink-search)

(defcustom blink-search-grep-pdf-backend 'pdf-tools
  "Backend to use for pdf files."
  :type 'symbol
  :options '(pdf-tools eaf-pdf-viewer)
  :group 'blink-search)

(defcustom blink-search-grep-pdf-preview-idle-time 0.5
  "Time to wait before previewing pdf."
  :type 'number
  :group 'blink-search)

(defcustom blink-search-pdf-search-paths nil
  "Paths to search for the pdf file of the current buffer."
  :type '(repeat string)
  :group 'blink-search)

(defcustom blink-search-pdf-backend 'pdf-tools
  "Backend to use for the pdf file of the current buffer."
  :type 'symbol
  :options '(pdf-tools eaf-pdf-viewer)
  :group 'blink-search)

(defcustom blink-search-pdf-preview-idle-time 0.5
  "Time to wait before previewing the pdf file of the current buffer."
  :type 'number
  :group 'blink-search)

(defcustom blink-search-quick-keys
  '("h" "l" "u" "i" "y"
    "," "." ";" "/" "'"
    "r" "v" "g" "t" "c"
    "7" "8" "9" "0"
    "H" "L" "U" "I" "Y"
    "s" "a" "e" "q"
    "1" "2" "3" "4"
    "[" "]")
  "Keys that select a candidate quickly, each prefixed with the Meta key.

The N-th entry selects the N-th visible candidate, so the list also
decides how many quick keys the menu shows.  Customize it when one of
the `M + KEY' bindings conflicts with a command of your own."
  :type '(repeat string)
  :group 'blink-search)

;;
;; Faces.
;;

(defface blink-search-select-face
  '()
  "Face used to highlight the currently selected candidate."
  :group 'blink-search)

(defface blink-search-font-lock-flash
  '((t (:inherit highlight)))
  "Face to flash the current line."
  :group 'blink-search)

;;
;; Buffers.
;;

(defvar blink-search-input-buffer " *blink search input*"
  "Name of the buffer the user types the search keyword into.")

(defvar blink-search-tooltip-buffer " *blink search tooltip*"
  "Name of the buffer that shows the search prefix help line.")

(defvar blink-search-candidate-buffer " *blink search candidate*"
  "Name of the buffer that shows the candidates.")

(defvar blink-search-backend-buffer " *blink search backend*"
  "Name of the buffer that shows the other candidates of one backend.")

;;
;; Where the search started.
;;

(defvar blink-search-window-configuration nil
  "Window configuration saved by `blink-search', restored by `blink-search-quit'.")

(defvar blink-search-start-buffer nil
  "The buffer `blink-search' was called from.")

(defvar blink-search-start-path-name nil
  "The file or URL shown by `blink-search-start-buffer', or nil for a plain buffer.")

(defvar blink-search-start-buffer-name nil
  "Name of the buffer `blink-search' was called from.")

(defvar blink-search-start-buffer-directory nil
  "Directory of the buffer `blink-search' was called from.")

(defvar blink-search-continue-directory nil
  "Directory the next search is restricted to, set by `blink-search-continue'.")

(defvar blink-search-start-keyword nil
  "Keyword `blink-search' starts with.
It comes from the active region, or from the symbol at point when
`blink-search' is called with a prefix argument.")

;;
;; The answer of the last search, as the Python half rendered it.
;;

(defvar blink-search-candidate-items nil
  "Candidate rows currently shown, each a plist of :backend and :candidate.")

(defvar blink-search-candidate-select-index nil
  "Index inside `blink-search-candidate-items' of the selected candidate.")

(defvar blink-search-backend-items nil
  "Every candidate of the backend the selection is in.")

(defvar blink-search-backend-select-index nil
  "Index inside `blink-search-backend-items' of the selected candidate.")

(defvar blink-search-backend-name nil
  "Name of the backend the selected candidate belongs to.")

(defvar blink-search-item-index nil
  "One based index of the selected candidate, shown in the tooltip line.")

(defvar blink-search-items-number nil
  "Number of candidates the last search found.")

(defvar blink-search-backend-number nil
  "Number of backends that returned a candidate.")

;;
;; The posframe popup, when `blink-search-enable-posframe' is non-nil.
;;

(defvar blink-search-posframe-preview-window nil
  "Window inside the posframe that previews the selected candidate.")

(defvar blink-search-posframe-emacs-frame nil
  "The Emacs frame the posframe popup was opened from.")

(defvar blink-search-posframe-frame nil
  "The posframe popup frame itself.")

;;
;; The Python process.
;;

(defvar blink-search-directory
  (if load-file-name
      (file-name-directory load-file-name)
    default-directory)
  "Directory blink-search was loaded from.

It is the directory that holds blink_search.py, the Python backends
under backend/ and the icons under icons/.  The value is computed from
`load-file-name', which means it is only correct when this file is
loaded from its own directory; every path blink-search builds is
derived from it.")

(defvar blink-search-python-file (expand-file-name "blink_search.py" blink-search-directory)
  "Path of the Python entry point of blink-search.")

(defvar blink-search-server nil
  "The EPC server Emacs listens on for the Python process.")

(defvar blink-search-server-port nil
  "Port `blink-search-server' listens on.")

(defvar blink-search-epc-process nil
  "The EPC manager that talks to the Python process.")

(defvar blink-search-internal-process nil
  "The Python process itself, as a process object.")

(defvar blink-search-internal-process-prog nil
  "Program the Python process was started with, `gdb' in debug mode.")

(defvar blink-search-internal-process-args nil
  "Arguments the Python process was started with.")

(defvar blink-search-is-starting nil
  "Non-nil while `blink-search-start-process' is waiting for the first start.")

(defvar blink-search-stop-process-hook nil
  "Hook run before the Python process is killed.")

(defvar blink-search-idle-update-list nil
  "Functions run after the Python process answered the first handshake.
Every function here is expected to be cheap; the backends that need to
push a list to Python only on the first start register here.")

(defvar blink-search-start-update-list nil
  "Functions run when a search session starts.
Every Elisp backend that has to push state to Python before the first
search registers here.")

(provide 'blink-search-state)
;;; blink-search-state.el ends here
