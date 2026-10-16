;;; blink-search-input.el --- The input buffer of blink-search  -*- lexical-binding: t; -*-

;; Filename: blink-search-input.el
;; Description: The input buffer of blink-search
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
;; The input buffer: what the user types, the mode that owns it, and the
;; translation of a keyword into a search request.
;;
;; `blink-search' is the command that starts a session; it creates the four
;; buffers, lays them out, and starts the Python process.  Every keystroke in
;; the input buffer goes through `blink-search-monitor-input', which decides
;; which backends the keyword is for.

;;; Code:

(require 'cl-lib)
(require 'blink-search-state)
(require 'blink-search-process)
(require 'blink-search-render)
(require 'blink-search-ui)

;; EAF is optional: `blink-search' reads the URL of an EAF buffer when it is
;; called from one, and the names below only have to exist at run time.
(defvar eaf--buffer-url)
(declare-function evil-set-initial-state "evil" (mode state &optional local))

;;;###autoload
(defun blink-search (&optional arg)
  "Start a blink-search session.

With ARG, the search starts from the symbol at point; without it the
search starts empty.  An active region is used as the first keyword
instead, and a keyword that starts with `#', `!', `;' or `:' restricts
the search to the current buffer, the current directory, PDFs under
`blink-search-grep-pdf-search-paths', or the current PDF file."
  (interactive "P")

  (setq blink-search-start-buffer (current-buffer))
  (setq blink-search-start-buffer-name (buffer-name (current-buffer)))
  (setq blink-search-start-path-name
        (if (derived-mode-p 'eaf-mode)
            eaf--buffer-url
          (buffer-file-name (current-buffer))))
  (setq blink-search-start-buffer-directory (with-current-buffer (current-buffer)
                                              (expand-file-name default-directory)))

  (setq blink-search-start-keyword (cond
                                    ((region-active-p)
                                     (buffer-substring-no-properties (region-beginning) (region-end)))
                                    (t
                                     (if arg (or (thing-at-point 'symbol t) "") ""))))

  ;; Save window configuration.
  (unless blink-search-window-configuration
    (setq blink-search-window-configuration (current-window-configuration)))

  ;; Create buffers.
  (with-current-buffer (get-buffer-create blink-search-input-buffer)
    (erase-buffer)

    (blink-search-mode)

    (run-hooks 'blink-search-mode-hook)
    (add-hook 'after-change-functions 'blink-search-monitor-input nil t)

    (blink-search-disable-options nil)

    ;; Set window margin.
    (setq-local left-margin-width 1)
    (setq-local right-margin-width 1))

  (with-current-buffer (get-buffer-create blink-search-tooltip-buffer)
    (erase-buffer)

    (blink-search-disable-options t)

    ;; Avoid background around input string.
    (face-remap-add-relative 'hl-line :background (face-background 'default))

    ;; Set window margin.
    (setq-local left-margin-width 1)
    (setq-local right-margin-width 1))

  (with-current-buffer (get-buffer-create blink-search-candidate-buffer)
    (erase-buffer)
    (blink-search-disable-options t)
    (setq-local truncate-lines t))

  (with-current-buffer (get-buffer-create blink-search-backend-buffer)
    (erase-buffer)
    (blink-search-disable-options t)
    (setq-local truncate-lines t))

  ;; Init color.
  (blink-search-init-colors)

  (if blink-search-enable-posframe
      (blink-search-init-popup-layout)
    (blink-search-init-bottom-layout))

  (dolist (update-func blink-search-start-update-list)
    (funcall update-func))

  ;; Start process.
  (unless blink-search-is-starting
    (blink-search-start-process)))

(defvar blink-search-mode-map
  (let ((map (make-sparse-keymap)))
    (define-key map (kbd "C-g") 'blink-search-quit)
    (define-key map (kbd "ESC ESC ESC") 'blink-search-quit)
    (define-key map (kbd "C-n") 'blink-search-candidate-select-next)
    (define-key map (kbd "C-p") 'blink-search-candidate-select-prev)
    (define-key map (kbd "M-n") 'blink-search-backend-select-next)
    (define-key map (kbd "M-p") 'blink-search-backend-select-prev)
    (define-key map (kbd "M-j") 'blink-search-candidate-group-select-next)
    (define-key map (kbd "M-k") 'blink-search-candidate-group-select-prev)
    (define-key map (kbd "C-m") 'blink-search-do)
    (define-key map (kbd "C-M-m") 'blink-search-preview)
    (define-key map (kbd "C-M-n") 'blink-search-preview-next)
    (define-key map (kbd "C-M-p") 'blink-search-preview-prev)
    (define-key map (kbd "C-j") 'blink-search-parent)
    (define-key map (kbd "C-l") 'blink-search-continue)
    (define-key map (kbd "M-w") 'blink-search-copy)

    (dolist (key blink-search-quick-keys)
      (define-key map (kbd (format "M-%s" key)) 'blink-search-quick-do))
    map)
  "Keymap used by `blink-search-mode'.")

(define-derived-mode blink-search-mode text-mode "blink-search"
  "Major mode of the blink-search input buffer.

It is a plain `text-mode' with the blink-search keymap: the buffer is a
line of search input, never a file, so nothing else is turned on."
  ;; Kill all local variables.
  (kill-all-local-variables)
  ;; Switch new mode.
  (setq major-mode 'blink-search-mode)
  (setq mode-name "blink-search")
  ;; Injection keymap.
  (use-local-map blink-search-mode-map)
  (when (featurep 'evil)
    (evil-set-initial-state 'blink-search-mode 'emacs))
  )

(defun blink-search-monitor-input (_begin _end _length)
  "Send the input buffer to the backends it is meant for.

This is the `after-change-functions' callback of the input buffer.  A
keyword that starts with `#' searches the current buffer, `!' the
current directory, `;' the PDFs under
`blink-search-grep-pdf-search-paths' and `:' the current PDF file;
anything else searches `blink-search-search-backends'."
  ;; Send new input to all backends when user change input.
  (when (string-equal (buffer-name) blink-search-input-buffer)
    (let* ((input (string-trim
                   (with-current-buffer blink-search-input-buffer
                     (buffer-substring-no-properties (point-min) (point-max))))))
      (cond ((string-prefix-p "#" input)
             (blink-search-call-async "search" (substring input 1) (blink-search-get-row-number) (list "Current Buffer")))
            ((or (string-prefix-p "!" input)
                 (string-prefix-p "！" input))
             (blink-search-call-async "search" (substring input 1) (blink-search-get-row-number) (list "Grep File")))
            ((or (string-prefix-p ";" input)
                 (string-prefix-p "；" input))
             (blink-search-call-async "search" (substring input 1) (blink-search-get-row-number) (list "Grep PDF")))
            ((or (string-prefix-p ":" input)
                 (string-prefix-p "：" input))
             (blink-search-call-async "search" (substring input 1) (blink-search-get-row-number) (list "PDF")))
            (t
             (blink-search-call-async "search" input (blink-search-get-row-number) blink-search-search-backends))))))

(defun blink-search-start ()
  "Run the search `blink-search' was called with.

It is registered in `blink-search-start-update-list', so it runs once
the Python process is up."
  (when (blink-search-epc-live-p blink-search-epc-process)
    (unless (string-empty-p blink-search-start-keyword)
      (message "[blink-search] Search symbol '%s'" blink-search-start-keyword))
    (blink-search-call-async "search" blink-search-start-keyword (blink-search-get-row-number) blink-search-search-backends)))

(add-to-list 'blink-search-start-update-list #'blink-search-start t)

(provide 'blink-search-input)

;;; blink-search-input.el ends here
