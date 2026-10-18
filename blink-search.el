;;; blink-search.el --- Blink search  -*- lexical-binding: t; -*-

;; Filename: blink-search.el
;; Description: Blink search
;; Author: Andy Stewart <lazycat.manatee@gmail.com>
;; Maintainer: Andy Stewart <lazycat.manatee@gmail.com>
;; Copyright (C) 2022, Andy Stewart, all rights reserved.
;; Created: 2022-10-23 15:23:53 +0800
;; Version: 0.1
;; Last-Updated: 2022-10-23 15:23:53 +0800
;;           By: Andy Stewart
;; URL: https://github.com/manateelazycat/blink-search
;; Keywords:
;; Compatibility: emacs-version >= 28
;; Package-Requires: ((emacs "28") (posframe "1.1.7") (markdown-mode "2.6"))
;;
;; Features that might be required by this library:
;;
;; Please check README
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
;; Blink-Search: search many sources in the blink of an eye.
;;
;; This file is the front door of the package.  It loads the modules the rest
;; of the code is split into:
;;
;;   blink-search-protocol.el  the Elisp/Python protocol, as data
;;   blink-search-state.el     every option and every piece of session state
;;   blink-search-process.el   the Python process and the EPC callbacks
;;   blink-search-ui.el        window layout, colours, icons
;;   blink-search-render.el    drawing the menu
;;   blink-search-input.el     the input buffer, its mode and its keymap
;;   blink-search-navigate.el  moving the selection and running an action
;;
;; The commands a user binds are in blink-search-input.el (`blink-search') and
;; blink-search-navigate.el (`blink-search-quit' and the movement commands);
;; this file only wires the modules together, so requiring 'blink-search is
;; still all a configuration has to do.

;;; Installation:
;;
;; Please check README

;;; Code:
(require 'cl-lib)
(require 'json)
(require 'map)
(require 'seq)
(require 'subr-x)

(require 'recentf)
(require 'imenu)
(require 'pulse)

;; `blink-search-state' defines `blink-search-directory' from
;; `load-file-name', and every other module builds its paths from it, so it
;; has to be loaded first.  The upstream order evaluated `eval-and-compile'
;; before the `defvar' and made byte compilation of this file fail with
;; "Symbol's value as variable is void"; there is nothing to compile at load
;; time any more.
;;
;; The Elisp backends used to live in backend/ with the Python ones, which
;; meant the Nix build (and melpa-build in general) compiled and installed
;; this file but not them: `require' then failed with "Cannot open load file,
;; blink-search-elisp-symbol".  They sit next to this file now, which is also
;; where the rest of the package is, and backend/ holds the Python half only.
(require 'blink-search-protocol)
(require 'blink-search-state)

(require 'blink-search-process)
(require 'blink-search-ui)
(require 'blink-search-render)
(require 'blink-search-input)
(require 'blink-search-navigate)

(require 'blink-search-elisp-symbol)
(require 'blink-search-imenu)
(require 'blink-search-grep-file)
(require 'blink-search-current-buffer)
(require 'blink-search-recent-file)
(require 'blink-search-buffer-list)
(require 'blink-search-grep-pdf)
(require 'blink-search-pdf)

;;;###autoload

;; EAF is optional: the command reads the URL of the buffer it is called
;; from when that buffer is one, and the name only has to exist at run time.
(defvar eaf--buffer-url)

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

  (unless blink-search-window-configuration
    (setq blink-search-window-configuration (current-window-configuration)))

  (with-current-buffer (get-buffer-create blink-search-input-buffer)
    (erase-buffer)

    (blink-search-mode)

    (run-hooks 'blink-search-mode-hook)
    (add-hook 'after-change-functions 'blink-search-monitor-input nil t)

    (blink-search-disable-options nil)

    (setq-local left-margin-width 1)
    (setq-local right-margin-width 1))

  (with-current-buffer (get-buffer-create blink-search-tooltip-buffer)
    (erase-buffer)

    (blink-search-disable-options t)

    ;; Avoid background around input string.
    (face-remap-add-relative 'hl-line :background (face-background 'default))

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

  ;; `C-g' has to leave the search from every pane of the menu, not only from
  ;; the input buffer: a preview can leave the focus in one of the others.
  ;; `q' does the same there -- but not in the input buffer, where it is a
  ;; letter of the keyword.
  (dolist (buffer (list blink-search-tooltip-buffer
                        blink-search-candidate-buffer
                        blink-search-backend-buffer))
    (blink-search-bind-quit-keys buffer t))

  (blink-search-init-colors)

  (if blink-search-enable-posframe
      (blink-search-init-popup-layout)
    (blink-search-init-bottom-layout))

  (dolist (update-func blink-search-start-update-list)
    (funcall update-func))

  (unless blink-search-is-starting
    (blink-search-start-process)))

(provide 'blink-search)
;;; blink-search.el ends here
