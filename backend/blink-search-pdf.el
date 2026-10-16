;;; blink-search-pdf.el --- Search PDF buffer backend   -*- lexical-binding: t; no-byte-compile: t; -*-

;; Filename: blink-search-pdf.el
;; Description: Search PDF buffer backend
;; Author: Andy Stewart <lazycat.manatee@gmail.com>
;; Maintainer: Andy Stewart <lazycat.manatee@gmail.com>
;; Copyright (C) 2023, Andy Stewart, all rights reserved.
;; Created: 2023-05-31 08:58:03
;; Version: 0.1
;; Last-Updated: 2023-05-31 08:58:03
;;           By: Andy Stewart
;; URL: https://www.github.org/manateelazycat/blink-search-pdf
;; Keywords:
;; Compatibility: GNU Emacs 30.0.50
;;
;; Features that might be required by this library:
;;
;;
;;

;;; This file is NOT part of GNU Emacs

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
;; Search PDF buffer backend
;;

;;; Installation:
;;
;; Put blink-search-pdf.el to your load-path.
;; The load-path is usually ~/elisp/.
;; It's set in your ~/.emacs like this:
;; (add-to-list 'load-path (expand-file-name "~/elisp"))
;;
;; And the following to your ~/.emacs startup file.
;;
;; (require 'blink-search-pdf)
;;
;; No need more.

;;; Customize:
;;
;;
;;
;; All of the above can customize by:
;;      M-x customize-group RET blink-search-pdf RET
;;

;;; Change log:
;;
;; 2023/05/31
;;      * First released.
;;

;;; Acknowledgements:
;;
;;
;;

;;; TODO
;;
;;
;;

;;; Require
(require 'blink-search-grep-file)

;;; Code:

(require 'blink-search-state)
(require 'blink-search-process)
(require 'blink-search-navigate)

(require 'blink-search-grep-file)

(defvar blink-search-pdf-preview-timer nil
  "Timer of the pending preview of a match in the current pdf file.

See `blink-search-grep-pdf-preview-timer' for why the preview is
delayed.")

(defun blink-search-pdf-pdftool-goto (file page submatches)
  "Visit FILE, go to PAGE and highlight SUBMATCHES with pdf-tools."
  (find-file file)
  (pdf-view-goto-page page)
  (let ((matches (pdf-isearch-search-page submatches)))
    (pdf-isearch-hl-matches (nth 0 matches) matches t)))

(defun blink-search-pdf-do (file page submatches)
  "Visit FILE, go to PAGE and highlight SUBMATCHES.

The viewer is chosen by `blink-search-pdf-backend'; an unknown backend
only reports a message."
  ;;highlight the matches
  (cond
   ((and (eq blink-search-pdf-backend 'pdf-tools) (featurep 'pdf-tools))
    (blink-search-pdf-pdftool-goto file page submatches))
   ((and (eq blink-search-pdf-backend 'eaf-pdf-viewer) (featurep 'eaf-pdf-viewer))
    (eaf-pdf-jump-to-page file page))
   ;; TODO support other pdf backends
   (t (message "Unknown backend %s" blink-search-pdf-backend))))

(defun blink-search-pdf-real-preview (file page submatches)
  "Highlight SUBMATCHES at PAGE of FILE and remember the buffer.

The buffer is remembered when the file was not open before, so that
`blink-search-pdf-clean' can close it again."
  (blink-search-select-input-window
   (let ((match-file (blink-search-grep-file-get-match-buffer file)))
     (blink-search-pdf-do file page submatches)
     (unless match-file
       (add-to-list 'blink-search-grep-file-temp-buffers (current-buffer))))))

(defun blink-search-pdf-preview (file page submatches)
  "Preview SUBMATCHES at PAGE of FILE once the selection settles down."
  (if blink-search-pdf-preview-timer (cancel-timer blink-search-pdf-preview-timer))
  (setq blink-search-pdf-preview-timer
        (run-with-idle-timer blink-search-pdf-preview-idle-time nil
                             (lambda ()
                               (blink-search-pdf-real-preview file page submatches)))))


(defun blink-search-pdf-clean ()
  "Drop the preview buffers and cancel the pending preview."
  (blink-search-grep-file-clean)
  (if blink-search-pdf-preview-timer (cancel-timer blink-search-pdf-preview-timer)))

(provide 'blink-search-pdf)

;;; blink-search-pdf.el ends here
