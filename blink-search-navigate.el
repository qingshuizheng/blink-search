;;; blink-search-navigate.el --- Selection and actions of blink-search  -*- lexical-binding: t; -*-

;; Filename: blink-search-navigate.el
;; Description: Selection and actions of blink-search
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
;; What the keys in the input buffer do: move the selection, pick a candidate
;; with a quick key, and run the action of the selected candidate.
;;
;; The movement is deliberately kept as thin as possible: the Python half owns
;; the selection indices and the Elisp half only says which way to move
;; (`blink-search-candidate-select-next' and friends).  The exception is
;; `blink-search-quick-do', which the user can run with a number of quick keys
;; at once, so it resolves the candidate locally before telling Python.

;;; Code:

(require 'cl-lib)
(require 'pulse)
(require 'blink-search-state)
(require 'blink-search-process)
(require 'blink-search-render)
(require 'blink-search-ui)

;; The EAF integration is reached through `featurep', so these names only have
;; to exist at run time.
(declare-function eaf-emacs-not-use-reparent-technology "eaf" ())
(defvar eaf--mac-safe-focus-change)

(defun blink-search-quit ()
  "Leave the search, restoring the window configuration it started with.
The Python half is told to drop its candidates, the posframe popup is
hidden, and everything `blink-search' recorded about the buffer it was
called from is cleared."
  (interactive)
  (blink-search-call-async "clean")

  ;; Close the popup first, and unconditionally.  This is the part the user
  ;; sees, and it used to sit inside the `when' below: with no window
  ;; configuration stored -- after a second `C-g', say -- nothing was hidden,
  ;; and a popup that stays on screen reads as "C-g does nothing".
  ;;
  ;; The closing goes through `posframe-hide' when posframe is loaded: a bare
  ;; `make-frame-invisible' followed by selecting the parent frame brought
  ;; the child back on macOS, so the menu looked like it ignored the key.
  (when (and blink-search-enable-posframe
             (frame-live-p blink-search-posframe-frame))
    (let ((buffer (get-buffer blink-search-input-buffer)))
      (if (and buffer (fboundp 'posframe-hide))
          (posframe-hide buffer)
        (make-frame-invisible blink-search-posframe-frame))))
  ;; A hidden frame may already be gone -- on macOS the child frame does not
  ;; always survive the parent taking the focus back.  Forgotten, so the next
  ;; menu opens a fresh one.
  (setq blink-search-posframe-frame nil)

  (let ((parent (and (framep blink-search-posframe-emacs-frame)
                     (frame-live-p blink-search-posframe-emacs-frame)
                     blink-search-posframe-emacs-frame)))
    (when parent
      (select-frame-set-input-focus parent)

      ;; popup will call 'eaf--mac-focus-change'
      ;; which causes switched buffer
      ;; switch back with (set-window-configuration (frame-parameter (selected-frame) 'eaf--mac-frame))
      (when (and (eq system-type 'darwin) (featurep 'eaf)
                 (eaf-emacs-not-use-reparent-technology)
                 eaf--mac-safe-focus-change)
        (set-frame-parameter parent 'eaf--mac-frame nil))))

  (when blink-search-window-configuration
    (set-window-configuration blink-search-window-configuration)
    (setq blink-search-window-configuration nil))

  ;; Forget the session itself whether or not there was a window
  ;; configuration to restore: the menu erases its buffers when it opens, but
  ;; these variables outlive it, and a `C-m' pressed after reopening -- before
  ;; the first new candidate arrives -- would act on a candidate of the search
  ;; that just ended.  A second `C-g' has to be harmless, so this is outside
  ;; the `when' above.
  (setq blink-search-start-buffer nil)
  (setq blink-search-start-buffer-name nil)
  (setq blink-search-start-path-name nil)
  (setq blink-search-start-buffer-directory nil)
  (setq blink-search-continue-directory nil)
  (setq blink-search-candidate-items nil)
  (setq blink-search-candidate-select-index nil)
  (setq blink-search-backend-items nil)
  (setq blink-search-backend-select-index nil)
  (setq blink-search-backend-name nil)
  (setq blink-search-item-index nil)
  (setq blink-search-items-number nil)
  (setq blink-search-backend-number nil))

(defun blink-search-quick-do ()
  "Run the action of the candidate the pressed quick key stands for.
The key is read from `last-command-event', so this command is bound
once per entry of `blink-search-quick-keys' by `blink-search-mode-map'."
  (interactive)
  (let* ((event-type (event-basic-type last-command-event))
         (event-string (if (characterp event-type)
                           (string event-type)
                         (error "Unexpected input")))
         (candidate-index (cl-position event-string blink-search-quick-keys :test 'equal)))
    (when (< candidate-index (length blink-search-candidate-items))
      (let* ((backend-name (plist-get (nth candidate-index blink-search-candidate-items) :backend))
             (candidate-info (plist-get (nth candidate-index blink-search-candidate-items) :candidate))
             (candidate (blink-search-get-candidate-text candidate-info)))
        (blink-search-quit)
        (blink-search-call-async "search_do" backend-name candidate)))))

(defun blink-search-goto-column (column)
  "Move point forward to byte COLUMN of the current line.
This is the replacement for `move-to-column' when the line mixes
Chinese and English characters, which is what ripgrep reports the
position of a match in."
  (let ((scan-column 0)
        (first-char-point (point)))

    (while (> column scan-column)
      (forward-char 1)
      (setq scan-column (string-bytes (buffer-substring first-char-point (point)))))))

(defun blink-search-flash-locate ()
  "Flash the line the cursor landed on, for `blink-search-flash-line-delay'."
  (ignore-errors
    (recenter)
    (let ((pulse-delay blink-search-flash-line-delay))
      ;; `pulse-delay' is read by pulse.el as a dynamic variable, which the
      ;; byte compiler cannot see, hence the `ignore'.
      (ignore pulse-delay)
      ;; Flash match line.
      (pulse-momentary-highlight-one-line (point) 'blink-search-font-lock-flash))))

(defun blink-search-candidate-select-next ()
  "Ask the Python half to select the next candidate."
  (interactive)
  (blink-search-call-async "select_next_candidate_item"))

(defun blink-search-candidate-select-prev ()
  "Ask the Python half to select the previous candidate."
  (interactive)
  (blink-search-call-async "select_prev_candidate_item"))

(defun blink-search-backend-select-next ()
  "Ask the Python half to select the next candidate of the same backend."
  (interactive)
  (blink-search-call-async "select_next_backend_item"))

(defun blink-search-backend-select-prev ()
  "Ask the Python half to select the previous candidate of the same backend."
  (interactive)
  (blink-search-call-async "select_prev_backend_item"))

(defun blink-search-candidate-group-select-next ()
  "Ask the Python half to jump to the next backend group."
  (interactive)
  (blink-search-call-async "select_next_candidate_group"))

(defun blink-search-candidate-group-select-prev ()
  "Ask the Python half to jump to the previous backend group."
  (interactive)
  (blink-search-call-async "select_prev_candidate_group"))

(defun blink-search-get-select-backend-name ()
  "Return the name of the backend the selected candidate belongs to."
  (plist-get (nth blink-search-candidate-select-index blink-search-candidate-items) :backend))

(defun blink-search-get-select-candidate ()
  "Return the text of the selected candidate.
The candidate is taken from the backend buffer when that buffer is
visible, because the user is then choosing inside the other candidates
of one backend."
  (let* ((candidate-info
          (if (get-buffer-window blink-search-backend-buffer)
              (nth blink-search-backend-select-index blink-search-backend-items)
            (plist-get (nth blink-search-candidate-select-index blink-search-candidate-items) :candidate)))
         (candidate (blink-search-get-candidate-text candidate-info)))
    candidate))

(defun blink-search-action (action)
  "Run the Python ACTION on the selected candidate and leave the search.
ACTION is an EPC method name, for example \"search_do\"; the backend
name and the candidate text are passed as its two arguments."
  (interactive)
  (when (> (length blink-search-candidate-items) 0)
    (let* ((backend-name (blink-search-get-select-backend-name))
           (candidate (blink-search-get-select-candidate)))
      (blink-search-quit)

      (blink-search-call-async action backend-name candidate))))

(defun blink-search-do ()
  "Run the default action of the selected candidate."
  (interactive)
  (blink-search-action "search_do"))

(defun blink-search-parent ()
  "Go to the parent directory of the selected candidate."
  (interactive)
  (blink-search-action "search_parent"))

(defun blink-search-preview ()
  "Preview the selected candidate in the preview window."
  (interactive)
  (blink-search-call-async "select_candidate_item"))

(defun blink-search-preview-next ()
  "Select the next candidate and preview it."
  (interactive)
  (blink-search-candidate-select-next)
  (blink-search-call-async "select_candidate_item"))

(defun blink-search-preview-prev ()
  "Select the previous candidate and preview it."
  (interactive)
  (blink-search-candidate-select-prev)
  (blink-search-call-async "select_candidate_item"))

(defun blink-search-continue ()
  "Search again inside the directory of the selected candidate."
  (interactive)
  (when (> (length blink-search-candidate-items) 0)
    (let* ((backend-name (blink-search-get-select-backend-name))
           (candidate (blink-search-get-select-candidate)))

      (blink-search-call-async "search_continue" backend-name candidate))))

(defun blink-search-copy ()
  "Copy the selected candidate into the kill ring."
  (interactive)
  (blink-search-action "search_copy"))

(provide 'blink-search-navigate)
;;; blink-search-navigate.el ends here
