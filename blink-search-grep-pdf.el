;;; blink-search-grep-pdf.el --- Description -*- lexical-binding: t; no-byte-compile: t; -*-
;;
;; Copyright (C) 2022 royokong
;;
;; Author: royokong <j614023177@icloud.com>
;; Maintainer: royokong <j614023177@icloud.com>
;; Created: November 21, 2022
;; Modified: November 21, 2022
;; Version: 0.0.1
;; Keywords: abbrev bib c calendar comm convenience data docs emulations extensions faces files frames games hardware help hypermedia i18n internal languages lisp local maint mail matching mouse multimedia news outlines processes terminals tex tools unix vc wp
;; Homepage: https://github.com/royokong/blink-search-grep-pdf
;; Package-Requires: ((emacs "24.3"))
;;
;; This file is not part of GNU Emacs.
;;
;;; Commentary:
;;
;;  Description
;;
;;; Code:

(require 'blink-search-state)
(require 'blink-search-process)
(require 'blink-search-navigate)

(require 'blink-search-grep-file)

(defvar blink-search-grep-pdf-preview-timer nil
  "Timer of the pending preview of a pdf match.

Previewing a pdf means opening a viewer and scrolling it, which is far
too expensive to do for every candidate the cursor passes over, so the
real preview runs `blink-search-grep-pdf-preview-idle-time' after the
selection stopped moving.")

(defun blink-search-grep-pdf-pdftool-goto (file page submatches)
  "Visit FILE, go to PAGE and highlight SUBMATCHES with pdf-tools.

SUBMATCHES are byte offsets into the text of the page, as ripgrep
reports them."
  (find-file file)
  (pdf-view-goto-page page)
  (let ((matches (pdf-isearch-search-page submatches)))
    (pdf-isearch-hl-matches (nth 0 matches) matches t)))

(defun blink-search-grep-pdf-do (file page submatches)
  "Visit FILE, go to PAGE and highlight SUBMATCHES.

The viewer is chosen by `blink-search-grep-pdf-backend'; an unknown
backend only reports a message, so that the search keeps working when
neither pdf-tools nor the EAF pdf viewer is installed."
  ;;highlight the matches
  (cond
   ((and (eq blink-search-grep-pdf-backend 'pdf-tools) (featurep 'pdf-tools))
    (blink-search-grep-pdf-pdftool-goto file page submatches))
   ((and (eq blink-search-grep-pdf-backend 'eaf-pdf-viewer) (featurep 'eaf-pdf-viewer))
    (eaf-pdf-jump-to-page file page))
   ;; TODO support other pdf backends
   (t (message "Unknown backend %s" blink-search-grep-pdf-backend))))

(defun blink-search-grep-pdf-real-preview (file page submatches)
  "Highlight SUBMATCHES at PAGE of FILE and remember the buffer.

This is what the idle timer in `blink-search-grep-pdf-preview' calls:
the buffer is remembered when the file was not open before, so that
`blink-search-grep-pdf-clean' can close it again."
  (blink-search-select-input-window
   (let ((match-file (blink-search-grep-file-get-match-buffer file)))
     (blink-search-grep-pdf-do file page submatches)
     (unless match-file
       (add-to-list 'blink-search-grep-file-temp-buffers (current-buffer))))))

(defun blink-search-grep-pdf-preview (file page submatches)
  "Preview SUBMATCHES at PAGE of FILE once the selection settles down.

A preview that is still pending is replaced, so that a quick
`C-M-n C-M-n C-M-n' only opens the last candidate."
  (if blink-search-grep-pdf-preview-timer (cancel-timer blink-search-grep-pdf-preview-timer))
  (setq blink-search-grep-pdf-preview-timer
        (run-with-idle-timer blink-search-grep-pdf-preview-idle-time nil
                             (lambda ()
                               (blink-search-grep-pdf-real-preview file page submatches)))))


(defun blink-search-grep-pdf-clean ()
  "Drop the preview buffers and cancel the pending preview."
  (blink-search-grep-file-clean)
  (when blink-search-grep-pdf-preview-timer
    (cancel-timer blink-search-grep-pdf-preview-timer)
    (setq blink-search-grep-pdf-preview-timer nil)))

(provide 'blink-search-grep-pdf)

;;; blink-search-grep-pdf.el ends here
