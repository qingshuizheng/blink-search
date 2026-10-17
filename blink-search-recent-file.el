;;; blink-search-recent-file.el --- Recent file backend for blink-search   -*- lexical-binding: t; -*-

;; Filename: blink-search-recent-file.el
;; Description: Recent file backend for blink-search
;; Author: Andy Stewart <lazycat.manatee@gmail.com>
;; Maintainer: Andy Stewart <lazycat.manatee@gmail.com>
;; Copyright (C) 2022, Andy Stewart, all rights reserved.
;; Created: 2022-11-04 08:50:31
;; Version: 0.1
;; Last-Updated: 2022-11-04 08:50:31
;;           By: Andy Stewart
;; URL: https://www.github.org/manateelazycat/blink-search-recent-file
;; Keywords:
;; Compatibility: GNU Emacs 28.2
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
;; Recent file backend for blink-search
;;

;;; Installation:
;;
;; Put blink-search-recent-file.el to your load-path.
;; The load-path is usually ~/elisp/.
;; It's set in your ~/.emacs like this:
;; (add-to-list 'load-path (expand-file-name "~/elisp"))
;;
;; And the following to your ~/.emacs startup file.
;;
;; (require 'blink-search-recent-file)
;;
;; No need more.

;;; Customize:
;;
;;
;;
;; All of the above can customize by:
;;      M-x customize-group RET blink-search-recent-file RET
;;

;;; Change log:
;;
;; 2022/11/04
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


;;; Code:

(require 'blink-search-state)
(require 'blink-search-process)

;; `recentf-list' belongs to recentf, which this backend is about but does
;; not start; declaring it here keeps the byte compiler from treating the
;; reference as a free variable.
(defvar recentf-list)
(require 'blink-search-navigate)

(defvar blink-search-recent-file-timer nil
  "The idle timer that pushes the recent file list to the Python half.")

(defvar blink-search-recent-file-size 0
  "Number of recent files the Python half was told about last time.")

(defun blink-search-recent-file-update ()
  "Push the recent file list to the Python half when it has changed.

The list is only sent when its length changed, so that the idle timer
stays cheap on a large `recentf-list'.  The names are copied with
`substring-no-properties', because a text property in a file name would
make the Python half see a different string than the one on disk."
  (let* ((files-size (length recentf-list)))
    (unless (equal blink-search-recent-file-size files-size)
      (blink-search-call-async "search_recent_file_update"
                               (mapcar #'substring-no-properties recentf-list))
      (setq blink-search-recent-file-size files-size))))

(defun blink-search-start-recent-file-update ()
  "Push the recent file list once, then keep it up to date while idle."
  (blink-search-recent-file-update)

  (unless blink-search-recent-file-timer
    (setq blink-search-recent-file-timer (run-with-idle-timer blink-search-recent-file-update-idle t #'blink-search-recent-file-update))))

(defun blink-search-stop-recent-file-update ()
  "Stop the idle timer and forget how many files were sent."
  (when blink-search-recent-file-timer
    (cancel-timer blink-search-recent-file-timer)
    (setq blink-search-recent-file-timer nil)
    (setq blink-search-recent-file-size 0)))

(add-to-list 'blink-search-idle-update-list #'blink-search-start-recent-file-update t)

(provide 'blink-search-recent-file)

;;; blink-search-recent-file.el ends here
