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
;; This file is the front door of the package.  It puts the Elisp backends on
;; the load path and loads the modules the rest of the code is split into:
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

;; `blink-search-state' defines `blink-search-backend-path' from
;; `load-file-name', so it has to be loaded before the path is used: the
;; upstream order evaluated `eval-and-compile' before the `defvar' and made
;; byte compilation of this file fail with "Symbol's value as variable is
;; void".  State comes first for that reason, not by alphabetical accident.
(require 'blink-search-protocol)
(require 'blink-search-state)

(eval-and-compile
  (add-to-list 'load-path blink-search-backend-path t))

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

(provide 'blink-search)

;;; blink-search.el ends here
